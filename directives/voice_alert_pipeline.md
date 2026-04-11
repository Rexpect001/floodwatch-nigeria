# Voice Alert Production & Governance Pipeline

## Purpose
Human-in-the-loop critical path that sits BEFORE any RED/ORANGE alert enters the
SMS/Voice dispatch queue. Alerts MUST NOT enter `alerts.voice.approved` RabbitMQ queue
until passing this governance layer.

## 5-Step Pipeline

```
Step 1: Source Composition     → English alert draft (max 280 chars)
              ↓  officer clicks "Generate"
Step 2: AI Translation [atomic] → Claude API batch → HA/YO/IG/PG JSON
              ↓  (no save available; auto-proceeds to Step 3)
Step 3: Audio Synthesis [atomic] → Google Cloud TTS / Coqui / Phrase Bank
              ↓  status → PENDING_REVIEW
Step 4: Officer Review          → play >50% each clip → Approve / Reject
              ↓  RED: dual-auth (4-eyes); non-RED: single officer
Step 5: Queue for Dispatch      → RabbitMQ alerts.voice.approved → AT Voice + Radio + IVR
```

**Total target latency: <30s Steps 1→3; <2 min officer review all 5 clips**

---

## Files

| File | Purpose |
|------|---------|
| `execution/db/schema_voice.sql` | voice_alert_sessions, voice_clips, voice_approval_audit, nema_officers, phrase_bank, whatsapp_reviewers |
| `execution/voice/translation_service.py` | Claude API batch translation (opus-4-6); confidence scoring; forbidden word check |
| `execution/voice/tts_service.py` | Tiered TTS: Google Cloud → Coqui → Phrase Bank; ffmpeg -16 LUFS normalization; S3 upload |
| `execution/voice/governance.py` | Playback tracking (>50%), approve/reject, dual-auth, emergency override (DIRECTOR+TOTP) |
| `execution/voice/pipeline.py` | Orchestrates Steps 1-5; VoicePipeline class |
| `execution/api/routers/voice_alerts.py` | REST API for all pipeline actions |
| `frontend/src/components/VoicePipeline/` | React wizard: StepTracker, SourceComposer, ClipCardGrid, ReviewPanel, DispatchConfirmation |

---

## TTS Tier Decision Tree

```
Language  →  Tier 1 (Now)             Tier 2 (Q2 2026)       Tier 3 (Future)
en        →  en-NG Neural2            (same)                  —
yo        →  yo-NG Chirp HD / Neural2 (same)                  CV community model
ha        →  ha-NG Standard → Coqui   Coqui VITS fine-tuned   CV auto-retrain >100h
ig        →  Phrase Bank (50 phrases) Google ig + disclaimer  CV auto-retrain
pg        →  en-NG Neural2 (0.85x)    (same)                  —
fu        →  DISABLED (SMS only)      —                       —
```

Coqui deployment: `docker run -p 5002:5002 ghcr.io/coqui-ai/tts --model_name tts_models/ha/...`
Health check: `GET http://coqui-service:5002/health`

---

## Governance Rules

| Rule | Detail |
|------|--------|
| Playback gate | Officer must play >50% of each clip; Approve button disabled until all met |
| RED dual-auth | 2 different officers must both play + approve (4-eyes principle) |
| Rejection | Mandatory reason ≥10 chars, stored permanently in voice_approval_audit |
| Emergency override | DIRECTOR role + valid TOTP code; triggers 24h post-incident audit |
| Audio integrity | SHA-256 checksum verified against S3 before dispatch |
| Offline resilience | Audio cached in IndexedDB; offline approval syncs on reconnect |

---

## Audio Specifications

| Spec | Value |
|------|-------|
| Format (storage) | MP3 VBR quality 4, 44.1kHz |
| Format (broadcast) | WAV PCM 16-bit |
| Max duration | 60 seconds (IVR limit) |
| Loudness | -16 LUFS (ffmpeg loudnorm filter) |
| Filename | `{alert_id}_{lang}_{timestamp}.mp3` |
| S3 class | Standard-IA (30-day lifecycle) |
| CDN | CloudFront distribution |

---

## Translation Rules (Claude API)

System prompt enforces:
- `ambaliya` (Hausa for flood), `ikun omi / iṣan omi` (Yoruba), `mmiri ịda / ịdá adá` (Igbo)
- `ficewa/tashi` (HA evacuate), `kúrò` (YO), `pụọ` (IG), `waka comot` (PG)
- Confidence threshold: 0.85 — below flags clip, disables auto-TTS for that language
- Forbidden loanwords: "flood" in HA/YO/IG; "evacuate" in HA/YO/IG
- Accepted exceptions: "dam", "radar", "meter"

---

## RabbitMQ Integration

Queue: `alerts.voice.approved` (persistent/durable)
Message payload:
```json
{
  "session_id": "uuid",
  "alert_id": "uuid",
  "queued_at": "ISO8601",
  "clips": [
    {"lang": "ha", "s3_key": "voice/{id}/ha_20260410T114500Z.mp3", "checksum": "sha256"}
  ]
}
```
Consumed by Alert Router → triggers:
1. Africa's Talking Voice API (automated phone calls)
2. Radio station FTP drop (if endpoint configured)
3. IVR system update

---

## WhatsApp Community Validator (Phase 2 — YELLOW/GREEN alerts)

- 3 reviewers per language per alert (verified community volunteers)
- Sent via WhatsApp Business API with audio + text
- Reply "APPROVED" or "CORRECT: [text]"
- 2/3 consensus = auto-approve; disagreement → NiMet linguist queue
- Rewards: Africa's Talking Airtime API credit for validated reviewers
- Auto-block reviewers with >20% rejection rate

---

## Error Handling

| Scenario | Fallback |
|----------|---------|
| Claude API timeout | Cached templates with `[TRANSLATION_PENDING]` watermark |
| Google Cloud TTS quota | Exponential backoff retry queue; officer notified |
| Audio generation failure | "Text Only" mode with radio-read instruction |
| Officer offline mid-review | IndexedDB cache; sync on reconnect (server timestamp wins) |
| Coqui service unhealthy | Falls back to Google Cloud TTS automatically |

---

## Acceptance Criteria

| Metric | Target |
|--------|--------|
| Generate latency (Steps 2+3) | <30s for 5 languages |
| Officer review time | <2 minutes to approve all 5 clips |
| Audio MOS score | >3.5 for Yoruba/Hausa (native speaker testing) |
| Checksum verification | 100% before dispatch |
| Audit log completeness | Every action recorded (immutable) |
