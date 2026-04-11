"""
Voice Alert Pipeline Orchestrator — Steps 1-5

Coordinates the full pipeline for a single voice alert session:
  Step 1: Source composition (officer writes EN text → saved as DRAFT)
  Step 2: AI translation   (Claude API → HA/YO/IG/PG, confidence scored)
  Step 3: Audio synthesis  (Google Cloud TTS / Coqui / phrase bank)
  Step 4: Officer review   (governance gate — play >50%, dual-auth for RED)
  Step 5: Queue dispatch   (RabbitMQ → Africa's Talking Voice + Radio + IVR)

End-to-end latency target: <30s from "Generate" to "Ready for Review"
"""
import asyncio
import logging
import time
from uuid import UUID

from .translation_service import translate_alert, persist_translations
from .tts_service import synthesise_all_clips
from .governance import (
    approve_session, reject_session, record_playback,
    check_approve_eligibility, emergency_override,
)

log = logging.getLogger(__name__)


class VoicePipeline:
    def __init__(self, db, redis):
        self.db = db
        self.redis = redis

    # ── Step 1: Create Draft ──────────────────────────────────

    async def create_draft(
        self,
        alert_id: str,
        source_text_en: str,
        composed_by: str,
    ) -> str:
        """
        Create a voice alert session in DRAFT state.
        Returns session_id.
        Character limit: 280 (ensures translations fit 160-char SMS).
        """
        if len(source_text_en) > 280:
            raise ValueError(f"Source text too long: {len(source_text_en)}/280 chars")

        async with self.db.acquire() as conn:
            session_id = await conn.fetchval(
                """
                INSERT INTO voice_alert_sessions
                    (alert_id, source_text_en, source_composed_by, source_composed_at, status)
                VALUES ($1, $2, $3, NOW(), 'DRAFT')
                RETURNING id::text
                """,
                alert_id, source_text_en, composed_by,
            )
        log.info(f"Voice draft created: session={session_id}, alert={alert_id}")
        return session_id

    # ── Steps 2 + 3: Generate (translation → synthesis) ───────

    async def generate(self, session_id: str) -> dict:
        """
        Atomic execution of Steps 2 (translation) and 3 (synthesis).
        Triggers both serially (synthesis depends on translation output).
        Target total latency: <30 seconds.

        Returns pipeline_status dict:
          {session_id, status, clips: [{lang, confidence, flagged, duration_s, audio_url}],
           translation_ms, synthesis_ms, total_ms, ready_for_review: bool}
        """
        t0 = time.monotonic()

        async with self.db.acquire() as conn:
            session = await conn.fetchrow(
                "SELECT source_text_en, status, alert_id FROM voice_alert_sessions WHERE id = $1",
                session_id,
            )
            if not session:
                raise ValueError(f"Session not found: {session_id}")
            if session["status"] not in ("DRAFT", "REJECTED"):
                raise ValueError(f"Cannot generate from status={session['status']}")

            # Mark as translating
            await conn.execute(
                "UPDATE voice_alert_sessions SET status = 'TRANSLATING' WHERE id = $1",
                session_id,
            )

        # Step 2: Translate
        log.info(f"Step 2 — Translating: session={session_id}")
        translation_result = await translate_alert(session["source_text_en"], session_id)
        await persist_translations(session_id, translation_result, self.db)
        translation_ms = translation_result.latency_ms

        # Step 3: Synthesise all clips concurrently
        log.info(f"Step 3 — Synthesising audio: session={session_id}")
        synthesis_results = await synthesise_all_clips(
            session_id, session["alert_id"], self.db
        )
        synthesis_ms = int((time.monotonic() - t0) * 1000) - translation_ms
        total_ms = int((time.monotonic() - t0) * 1000)

        # Build response
        clips = []
        for lang in ("en", "ha", "yo", "ig", "pg"):
            tr = translation_result.translations.get(lang)
            synth = synthesis_results.get(lang)
            clips.append({
                "lang": lang,
                "script_text": tr.text if tr else "",
                "confidence": tr.confidence if tr else 0.0,
                "flagged": tr.flagged if tr else True,
                "requires_manual_review": tr.requires_manual_review if tr else True,
                "audio_url": synth.audio_url if synth else None,
                "waveform_data": synth.waveform_data if synth else [],
                "duration_s": synth.duration_s if synth else 0,
                "tts_engine": synth.tts_engine if synth else None,
                "disclaimer": synth.disclaimer if synth else None,
                "played_once": False,
            })

        ready = all(
            c["audio_url"] or c["flagged"]
            for c in clips
        )

        log.info(
            f"Pipeline generate complete: session={session_id}, "
            f"total={total_ms}ms (trans={translation_ms}ms, synth={synthesis_ms}ms), "
            f"ready={ready}"
        )

        return {
            "session_id": session_id,
            "status": "PENDING_REVIEW",
            "clips": clips,
            "translation_ms": translation_ms,
            "synthesis_ms": synthesis_ms,
            "total_ms": total_ms,
            "ready_for_review": ready,
            "used_cached_translation": translation_result.used_cached,
        }

    # ── Step 4: Review progress ───────────────────────────────

    async def track_playback(
        self,
        session_id: str,
        lang: str,
        officer_id: str,
        playback_duration_s: float,
    ) -> dict:
        """Called from frontend as officer plays clips. Returns approve-eligibility."""
        played_once = await record_playback(
            session_id, lang, officer_id, playback_duration_s, self.db, self.redis
        )
        eligibility = await check_approve_eligibility(session_id, officer_id, self.db, self.redis)
        return {**eligibility, "lang": lang, "played_once": played_once}

    # ── Step 4: Approve ───────────────────────────────────────

    async def approve(self, session_id: str, officer_id: str) -> dict:
        return await approve_session(session_id, officer_id, self.db, self.redis)

    async def reject(self, session_id: str, officer_id: str, reason: str) -> None:
        await reject_session(session_id, officer_id, reason, self.db)

    async def override(self, session_id: str, officer_id: str, totp_code: str) -> dict:
        return await emergency_override(session_id, officer_id, totp_code, self.db, self.redis)

    # ── Status ────────────────────────────────────────────────

    async def get_status(self, session_id: str) -> dict:
        """Full pipeline status for the review UI."""
        async with self.db.acquire() as conn:
            session = await conn.fetchrow(
                """
                SELECT s.id, s.status, s.source_text_en, s.translation_ms,
                       s.primary_approver_id, s.secondary_approver_id,
                       s.is_emergency_override, s.queued_at, s.rabbitmq_message_id,
                       a.severity AS alert_severity, a.alert_type
                FROM voice_alert_sessions s
                JOIN alerts a ON a.id = s.alert_id
                WHERE s.id = $1
                """,
                session_id,
            )
            clips = await conn.fetch(
                """
                SELECT lang, script_text, translation_confidence, translation_flagged,
                       forbidden_words_found, audio_url, waveform_data, audio_duration_s,
                       tts_engine, played_once, playback_duration_s, review_complete,
                       waived, tts_disabled, synthesis_error
                FROM voice_clips WHERE session_id = $1
                ORDER BY CASE lang WHEN 'en' THEN 1 WHEN 'ha' THEN 2 WHEN 'yo' THEN 3
                                   WHEN 'ig' THEN 4 WHEN 'pg' THEN 5 END
                """,
                session_id,
            )

        return {
            "session_id": str(session["id"]),
            "status": session["status"],
            "alert_severity": session["alert_severity"],
            "alert_type": session["alert_type"],
            "source_text_en": session["source_text_en"],
            "is_red_alert": session["alert_severity"] == "RED",
            "dual_auth_required": session["alert_severity"] == "RED",
            "primary_approved": session["primary_approver_id"] is not None,
            "secondary_approved": session["secondary_approver_id"] is not None,
            "is_override": session["is_emergency_override"],
            "queued": session["queued_at"] is not None,
            "rabbitmq_message_id": session["rabbitmq_message_id"],
            "clips": [dict(c) for c in clips],
        }
