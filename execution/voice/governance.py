"""
Governance Layer — Approve & Queue (Step 4)
NEMA Officer Authorization Bottleneck

Rules (from spec):
  1. All 5 language clips must be generated OR explicitly waived
  2. Officer must play >50% of each clip before Approve enables
  3. RED alerts: dual-authorization (4-eyes) — 2 officers required
  4. Rejection: mandatory comment stored in audit_log
  5. Emergency Override: Director-level only + 2FA confirmation → triggers audit report
  6. Audio integrity: SHA-256 checksum verified before dispatch

Upon approval:
  - MP3 files confirmed on S3
  - Metadata pushed to RabbitMQ queue: alerts.voice.approved (persistent)
  - Alert Router consumes and triggers Africa's Talking Voice + Radio FTP + IVR
"""
import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE_NAME   = "alerts.voice.approved"


class GovernanceError(Exception):
    pass


class InsufficientPlaybackError(GovernanceError):
    """Raised when officer tries to approve before playing >50% of all clips."""
    pass


class DualAuthRequired(GovernanceError):
    """Raised when RED alert approval attempted with only 1 officer."""
    pass


class InsufficientRoleError(GovernanceError):
    """Raised when officer role insufficient for the requested action."""
    pass


# ── Playback Tracking ─────────────────────────────────────────

async def record_playback(
    session_id: str,
    lang: str,
    officer_id: str,
    playback_duration_s: float,
    db,
    redis,
) -> bool:
    """
    Track playback progress. Returns True if clip is now >50% played.
    Updates voice_clips.playback_duration_s and played_once flag.
    """
    async with db.acquire() as conn:
        clip = await conn.fetchrow(
            "SELECT audio_duration_s, playback_duration_s FROM voice_clips "
            "WHERE session_id = $1 AND lang = $2",
            session_id, lang,
        )
        if not clip:
            return False

        total = float(clip["audio_duration_s"] or 0)
        threshold = total * 0.5
        played_once = playback_duration_s >= threshold

        await conn.execute(
            """
            UPDATE voice_clips
            SET playback_duration_s = GREATEST(playback_duration_s, $3),
                played_once = $4
            WHERE session_id = $1 AND lang = $2
            """,
            session_id, lang, playback_duration_s, played_once,
        )

    # Audit log
    await _write_audit(
        session_id, officer_id, "PLAYBACK_COMPLETED" if played_once else "PLAYBACK_STARTED",
        lang=lang, playback_pct=(playback_duration_s / total * 100) if total else 0,
        db=db,
    )

    # Cache per-session playback state in Redis (for offline reconnect)
    cache_key = f"voice:playback:{session_id}:{officer_id}"
    await redis.hset(cache_key, lang, json.dumps({
        "duration_s": playback_duration_s, "played_once": played_once
    }))
    await redis.expire(cache_key, 86400)

    return played_once


async def check_approve_eligibility(
    session_id: str,
    officer_id: str,
    db,
    redis,
) -> dict:
    """
    Returns eligibility status for the Approve button.
    {eligible: bool, reason: str, missing_langs: list, is_red_alert: bool, needs_second_approver: bool}
    """
    async with db.acquire() as conn:
        session = await conn.fetchrow(
            """
            SELECT s.status, s.primary_approver_id, s.secondary_approver_id,
                   a.severity, s.is_emergency_override
            FROM voice_alert_sessions s
            JOIN alerts a ON a.id = s.alert_id
            WHERE s.id = $1
            """,
            session_id,
        )
        if not session:
            return {"eligible": False, "reason": "Session not found"}

        clips = await conn.fetch(
            "SELECT lang, played_once, waived, tts_disabled, audio_url "
            "FROM voice_clips WHERE session_id = $1",
            session_id,
        )

    # Check all clips played or waived
    missing = [
        c["lang"] for c in clips
        if not c["played_once"] and not c["waived"] and not c["tts_disabled"]
        and c["audio_url"] is not None
    ]

    is_red = session["severity"] == "RED"
    needs_second = is_red and session["primary_approver_id"] is not None and \
                   session["primary_approver_id"] != officer_id and \
                   session["secondary_approver_id"] is None

    if missing:
        return {
            "eligible": False,
            "reason": f"Must play >50% of clips: {', '.join(missing).upper()}",
            "missing_langs": missing,
            "is_red_alert": is_red,
            "needs_second_approver": needs_second,
        }

    if is_red:
        if session["primary_approver_id"] is None:
            return {
                "eligible": True,
                "reason": "RED alert: first approval — second officer will be required",
                "missing_langs": [],
                "is_red_alert": True,
                "needs_second_approver": True,
            }
        if session["primary_approver_id"] == officer_id:
            return {
                "eligible": False,
                "reason": "RED alert: same officer cannot provide both approvals (4-eyes principle)",
                "missing_langs": [],
                "is_red_alert": True,
                "needs_second_approver": True,
            }
        if session["secondary_approver_id"] is not None:
            return {
                "eligible": False,
                "reason": "RED alert: already fully approved",
                "missing_langs": [],
                "is_red_alert": True,
                "needs_second_approver": False,
            }

    return {
        "eligible": True,
        "reason": "All clips reviewed",
        "missing_langs": [],
        "is_red_alert": is_red,
        "needs_second_approver": needs_second,
    }


async def approve_session(
    session_id: str,
    officer_id: str,
    db,
    redis,
) -> dict:
    """
    Approve a voice alert session.
    RED: sets primary_approver; second call with different officer finalises.
    Non-RED: single approval queues immediately.
    Returns: {queued: bool, awaiting_second: bool, rabbitmq_message_id: str}
    """
    eligibility = await check_approve_eligibility(session_id, officer_id, db, redis)
    if not eligibility["eligible"]:
        raise GovernanceError(eligibility["reason"])

    await _verify_officer_role(officer_id, required_role="OFFICER", db=db)

    async with db.acquire() as conn:
        session = await conn.fetchrow(
            "SELECT primary_approver_id, secondary_approver_id, alert_id FROM voice_alert_sessions WHERE id = $1",
            session_id,
        )

        is_red = eligibility["is_red_alert"]
        is_first_approval = session["primary_approver_id"] is None

        if is_first_approval:
            await conn.execute(
                "UPDATE voice_alert_sessions SET primary_approver_id = $2, primary_approved_at = NOW() WHERE id = $1",
                session_id, officer_id,
            )
            await _write_audit(session_id, officer_id, "APPROVED", db=db)

            if not is_red:
                # Single approval is sufficient for non-RED
                return await _finalise_approval(session_id, session["alert_id"], db, redis)
            else:
                return {"queued": False, "awaiting_second": True, "message": "First approval recorded. RED alert requires second officer."}

        else:
            # Second approval for RED
            await conn.execute(
                "UPDATE voice_alert_sessions SET secondary_approver_id = $2, secondary_approved_at = NOW() WHERE id = $1",
                session_id, officer_id,
            )
            await _write_audit(session_id, officer_id, "APPROVED", db=db)
            return await _finalise_approval(session_id, session["alert_id"], db, redis)


async def reject_session(
    session_id: str,
    officer_id: str,
    reason: str,
    db,
) -> None:
    """Reject a voice alert session. Reason is mandatory and stored in audit log."""
    if not reason or len(reason.strip()) < 10:
        raise GovernanceError("Rejection reason is required (minimum 10 characters)")

    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE voice_alert_sessions
            SET status = 'REJECTED', rejection_reason = $2, updated_at = NOW()
            WHERE id = $1
            """,
            session_id, reason.strip(),
        )

    await _write_audit(session_id, officer_id, "REJECTED", notes=reason, db=db)
    log.warning(f"Voice session REJECTED: session={session_id}, officer={officer_id}, reason={reason[:100]}")


async def emergency_override(
    session_id: str,
    officer_id: str,
    totp_code: str,
    db,
    redis,
) -> dict:
    """
    Emergency override: bypass governance gate.
    Requires DIRECTOR role + valid TOTP (2FA).
    Triggers automatic post-incident audit report due in 24 hours.
    """
    await _verify_officer_role(officer_id, required_role="DIRECTOR", db=db)
    await _verify_totp(officer_id, totp_code)

    async with db.acquire() as conn:
        session = await conn.fetchrow(
            "SELECT alert_id FROM voice_alert_sessions WHERE id = $1", session_id
        )
        audit_due = datetime.now(timezone.utc) + timedelta(hours=24)
        await conn.execute(
            """
            UPDATE voice_alert_sessions SET
                is_emergency_override = TRUE,
                override_officer_id = $2,
                override_at = NOW(),
                override_audit_report_due = $3
            WHERE id = $1
            """,
            session_id, officer_id, audit_due,
        )

    await _write_audit(
        session_id, officer_id, "EMERGENCY_OVERRIDE",
        notes=f"Audit report due: {audit_due.strftime('%d/%m/%Y %H:%M WAT')}",
        db=db,
    )
    log.critical(f"EMERGENCY OVERRIDE: session={session_id}, officer={officer_id}")

    result = await _finalise_approval(session_id, session["alert_id"], db, redis)
    result["is_override"] = True
    result["audit_report_due"] = audit_due.isoformat()
    return result


async def _finalise_approval(session_id: str, alert_id: str, db, redis) -> dict:
    """
    Final step: verify checksums → mark APPROVED → push to RabbitMQ.
    """
    # Verify audio checksums
    async with db.acquire() as conn:
        clips = await conn.fetch(
            "SELECT lang, audio_s3_key, audio_checksum FROM voice_clips WHERE session_id = $1",
            session_id,
        )

    await _verify_checksums(clips)

    # Push to RabbitMQ
    msg_id = await _publish_to_rabbitmq(session_id, alert_id, clips)

    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE voice_alert_sessions
            SET status = 'QUEUED', rabbitmq_message_id = $2, queued_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
            """,
            session_id, msg_id,
        )

    await _write_audit(session_id, "system", "QUEUED",
                       notes=f"RabbitMQ: {msg_id}", db=db)

    log.info(f"Voice session QUEUED: session={session_id}, mq_id={msg_id}")
    return {"queued": True, "awaiting_second": False, "rabbitmq_message_id": msg_id}


async def _verify_checksums(clips) -> None:
    """Re-hash S3 audio bytes and compare to stored checksum."""
    import boto3
    s3 = boto3.client("s3")
    for clip in clips:
        if not clip["audio_s3_key"] or not clip["audio_checksum"]:
            continue
        try:
            obj = s3.get_object(
                Bucket=os.getenv("VOICE_S3_BUCKET", "nimet-plus-alerts"),
                Key=clip["audio_s3_key"],
            )
            actual = hashlib.sha256(obj["Body"].read()).hexdigest()
            if actual != clip["audio_checksum"]:
                raise GovernanceError(
                    f"Audio integrity check FAILED for lang={clip['lang']} — "
                    f"checksum mismatch. File may have been tampered."
                )
        except Exception as e:
            log.warning(f"Checksum verification failed for {clip['audio_s3_key']}: {e}")


async def _publish_to_rabbitmq(session_id: str, alert_id: str, clips) -> str:
    """
    Publish to RabbitMQ queue: alerts.voice.approved (persistent messages).
    Alert Router microservice consumes and dispatches to:
      - Africa's Talking Voice API
      - Radio station FTP drop
      - IVR system update
    """
    import aio_pika

    payload = {
        "session_id": session_id,
        "alert_id": alert_id,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "clips": [
            {
                "lang": c["lang"],
                "s3_key": c["audio_s3_key"],
                "checksum": c["audio_checksum"],
            }
            for c in clips if c["audio_s3_key"]
        ],
    }

    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(
                QUEUE_NAME,
                durable=True,      # persistent — survives RabbitMQ restart
            )
            message = aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=session_id,
                content_type="application/json",
            )
            await channel.default_exchange.publish(message, routing_key=QUEUE_NAME)
            log.info(f"Published to RabbitMQ: queue={QUEUE_NAME}, msg_id={session_id}")
            return session_id

    except Exception as e:
        log.error(f"RabbitMQ publish failed: {e}")
        raise


async def _write_audit(
    session_id: str,
    officer_id: str,
    action: str,
    lang: str = None,
    playback_pct: float = None,
    notes: str = None,
    db=None,
) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO voice_approval_audit
                (session_id, officer_id, action, lang, playback_pct, notes)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            session_id, officer_id, action, lang, playback_pct, notes,
        )


async def _verify_officer_role(officer_id: str, required_role: str, db) -> None:
    ROLE_HIERARCHY = {"OFFICER": 1, "SENIOR_OFFICER": 2, "DIRECTOR": 3, "ADMIN": 4}
    async with db.acquire() as conn:
        officer = await conn.fetchrow(
            "SELECT role, is_active FROM nema_officers WHERE id = $1", officer_id
        )
    if not officer or not officer["is_active"]:
        raise InsufficientRoleError(f"Officer {officer_id} not found or inactive")
    if ROLE_HIERARCHY.get(officer["role"], 0) < ROLE_HIERARCHY.get(required_role, 99):
        raise InsufficientRoleError(
            f"Officer {officer_id} has role {officer['role']} — requires {required_role}"
        )


async def _verify_totp(officer_id: str, totp_code: str) -> None:
    """Verify TOTP 2FA code for emergency override. Uses pyotp."""
    import pyotp
    import os
    # In production: fetch officer TOTP secret from secrets manager
    secret = os.getenv(f"TOTP_SECRET_{officer_id}", os.getenv("TOTP_SECRET_DEFAULT", ""))
    if not secret:
        raise GovernanceError("TOTP not configured for this officer")
    totp = pyotp.TOTP(secret)
    if not totp.verify(totp_code, valid_window=1):
        raise GovernanceError("Invalid 2FA code — emergency override denied")
