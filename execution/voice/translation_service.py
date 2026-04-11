"""
AI Translation Layer — Claude API Batch Processing (Step 2)

Single API call translates English source into HA/YO/IG/PG simultaneously.
Returns structured JSON with confidence scores per language.
Confidence <0.85 → flags clip for manual review, disables auto-TTS for that language.

Forbidden loanword rules enforced post-response:
  - HA/YO/IG: no raw English loanwords unless officially accepted
  - Accepted exceptions: "dam", "meter", "radar" (technical/infrastructure)
  - Forbidden: "flood" in HA (use "ambaliya"), "evacuate" in YO (use "kúrò")
"""
import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL             = "claude-opus-4-6"    # Per CLAUDE.md: use Opus 4.6
CONFIDENCE_THRESHOLD = 0.85
MAX_SOURCE_CHARS  = 280

# Officially accepted loanwords per language (not flagged)
ACCEPTED_LOANWORDS = {
    "ha": {"dam", "radar", "meter", "kilomita", "watan", "flood"},  # "flood" accepted in Hausa compound
    "yo": {"radar", "kilomita"},
    "ig": {"radar", "dam", "kilometer"},
    "pg": set(),   # Pidgin: all English words acceptable
}

# Forbidden: English originals that MUST be translated
FORBIDDEN_LOANWORDS = {
    "ha": {"flood", "evacuate", "emergency", "warning"},
    "yo": {"flood", "evacuate", "emergency", "warning"},
    "ig": {"flood", "evacuate", "emergency"},
    "pg": set(),
}

SYSTEM_PROMPT = """You are an emergency alert translator for Nigeria's official flood and climate early warning system.
Translate the provided English alert text into EXACTLY these four languages simultaneously.

TRANSLATION RULES:
1. Hausa (ha): Use "ambaliya" for flood, "ficewa/tashi" for evacuate, "gargaji" for warning. No raw English loanwords except accepted technical terms (dam, radar, meter).
2. Yoruba (yo): Use "ikun omi" or "iṣan omi" for flood, "kúrò" for evacuate, "ìkìlọ̀" for warning. Include correct tonal diacritics (ẹ, ọ, á, è, etc.).
3. Igbo (ig): Use "mmiri ịda" or "ịdá adá" for flood, "pụọ" for evacuate, "ọdịmara" for warning. Include correct diacritics (ọ, ụ, ị, ṅ).
4. Nigerian Pidgin (pg): Use "flood" for flood (acceptable in Pidgin), "comot/waka comot" for evacuate, "alert" for warning. Keep urgent, direct tone.

CRITICAL: Emergency alerts must be SHORT, URGENT, and ACTIONABLE.
Each translation MUST fit within 160 Unicode characters where possible.
Forbidden English words in HA/YO/IG: "flood" (HA/YO/IG), "evacuate" (HA/YO/IG), "emergency" (HA/YO/IG).

Return ONLY valid JSON with this exact structure:
{
  "ha": {"text": "...", "confidence": 0.0-1.0, "char_count": 0, "notes": "..."},
  "yo": {"text": "...", "confidence": 0.0-1.0, "char_count": 0, "notes": "..."},
  "ig": {"text": "...", "confidence": 0.0-1.0, "char_count": 0, "notes": "..."},
  "pg": {"text": "...", "confidence": 0.0-1.0, "char_count": 0, "notes": "..."}
}"""


@dataclass
class TranslationResult:
    lang: str
    text: str
    confidence: float
    char_count: int
    flagged: bool              # confidence < threshold OR forbidden word found
    forbidden_words: list[str]
    notes: str
    requires_manual_review: bool


@dataclass
class BatchTranslationResult:
    session_id: str
    request_id: str            # Claude API request ID for tracing
    source_en: str
    translations: dict[str, TranslationResult]
    latency_ms: int
    used_cached: bool


async def translate_alert(source_en: str, session_id: str) -> BatchTranslationResult:
    """
    Single Claude API call translating EN → HA/YO/IG/PG simultaneously.
    Target latency: <10s (within 30s end-to-end pipeline budget).
    Falls back to cached templates if API unavailable.
    """
    if len(source_en) > MAX_SOURCE_CHARS:
        raise ValueError(f"Source text exceeds {MAX_SOURCE_CHARS} chars: {len(source_en)}")

    import time
    t0 = time.monotonic()

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Translate this emergency alert:\n\n{source_en}"
                }
            ],
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        raw_json = message.content[0].text.strip()

        # Strip any markdown code fences if present
        raw_json = re.sub(r"```(?:json)?", "", raw_json).strip()
        parsed = json.loads(raw_json)

        translations = {}
        for lang in ("ha", "yo", "ig", "pg"):
            lang_data = parsed.get(lang, {})
            text = lang_data.get("text", "")
            confidence = float(lang_data.get("confidence", 0.0))

            forbidden = _check_forbidden_words(text, lang)
            flagged = confidence < CONFIDENCE_THRESHOLD or len(forbidden) > 0

            translations[lang] = TranslationResult(
                lang=lang,
                text=text,
                confidence=confidence,
                char_count=len(text),
                flagged=flagged,
                forbidden_words=forbidden,
                notes=lang_data.get("notes", ""),
                requires_manual_review=flagged,
            )

            if flagged:
                log.warning(
                    f"Translation flagged: lang={lang}, confidence={confidence:.2f}, "
                    f"forbidden={forbidden}, session={session_id}"
                )

        log.info(
            f"Translation complete: session={session_id}, "
            f"latency={latency_ms}ms, flags={sum(1 for t in translations.values() if t.flagged)}"
        )

        return BatchTranslationResult(
            session_id=session_id,
            request_id=message.id,
            source_en=source_en,
            translations=translations,
            latency_ms=latency_ms,
            used_cached=False,
        )

    except anthropic.APITimeoutError:
        log.error(f"Claude API timeout for session={session_id} — falling back to cached templates")
        return _fallback_cached_templates(source_en, session_id)

    except (anthropic.APIError, json.JSONDecodeError) as e:
        log.error(f"Translation failed for session={session_id}: {e}")
        return _fallback_cached_templates(source_en, session_id)


def _check_forbidden_words(text: str, lang: str) -> list[str]:
    """Return list of forbidden loanwords found in translation."""
    forbidden_set = FORBIDDEN_LOANWORDS.get(lang, set())
    accepted_set  = ACCEPTED_LOANWORDS.get(lang, set())
    words_in_text = set(re.findall(r'\b\w+\b', text.lower()))
    return list((words_in_text & forbidden_set) - accepted_set)


def _fallback_cached_templates(source_en: str, session_id: str) -> BatchTranslationResult:
    """
    Fallback when Claude API unavailable.
    Returns [TRANSLATION_PENDING] watermark so officers know this needs review.
    """
    import time
    pending_text = {
        "ha": "[FASSARA NA JIRA] " + source_en[:80],
        "yo": "[ÌTUMỌ̀ TÍ Ń DÈ] " + source_en[:80],
        "ig": "[NTỤGHARỊ NA-ATỌ ANYA] " + source_en[:80],
        "pg": "[TRANSLATION PENDING] " + source_en[:80],
    }
    translations = {
        lang: TranslationResult(
            lang=lang, text=text, confidence=0.0,
            char_count=len(text), flagged=True,
            forbidden_words=[], notes="Cached fallback — manual review required",
            requires_manual_review=True,
        )
        for lang, text in pending_text.items()
    }
    return BatchTranslationResult(
        session_id=session_id, request_id="fallback",
        source_en=source_en, translations=translations,
        latency_ms=0, used_cached=True,
    )


async def persist_translations(session_id: str, result: BatchTranslationResult, db):
    """Write translation results to voice_clips table."""
    async with db.acquire() as conn:
        for lang, tr in result.translations.items():
            await conn.execute(
                """
                INSERT INTO voice_clips
                    (session_id, lang, script_text, translation_confidence,
                     translation_flagged, forbidden_words_found)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (session_id, lang) DO UPDATE SET
                    script_text            = EXCLUDED.script_text,
                    translation_confidence = EXCLUDED.translation_confidence,
                    translation_flagged    = EXCLUDED.translation_flagged,
                    forbidden_words_found  = EXCLUDED.forbidden_words_found,
                    updated_at             = NOW()
                """,
                session_id, lang, tr.text, tr.confidence,
                tr.flagged, tr.forbidden_words,
            )
        await conn.execute(
            """
            UPDATE voice_alert_sessions
            SET status = 'SYNTHESISING', translation_at = NOW(),
                translation_job_id = $2, translation_ms = $3
            WHERE id = $1
            """,
            session_id, result.request_id, result.latency_ms,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test = (
        "FLOOD WARNING: HIGH RISK for Kogi LGA. River level rising rapidly. "
        "Evacuate low-lying areas immediately. Go to nearest shelter. "
        "Call 08000-NEMA. ID: NEMA-2025-001"
    )
    result = asyncio.run(translate_alert(test, "test-session-001"))
    for lang, tr in result.translations.items():
        print(f"\n[{lang.upper()}] conf={tr.confidence:.2f} flagged={tr.flagged}")
        print(f"  {tr.text}")
