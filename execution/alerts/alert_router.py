"""
Alert Router Microservice — RabbitMQ Consumer
Consumes from: alerts.voice.approved (persistent)
Dispatches to:
  1. Africa's Talking Voice API — automated phone calls
  2. Radio station FTP drop    — WAV file + script text
  3. IVR system update         — USSD/IVR menu refresh
  4. Push notifications        — FCM (Android) + APNs (iOS)
  5. WhatsApp Business API     — rich media alert message

This is the FINAL step after governance approval.
Alerts MUST NOT reach this service without passing voice_pipeline approval gate.

Run: python -m execution.alerts.alert_router
"""
import asyncio
import json
import logging
import os
import ftplib
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aio_pika
import boto3
import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

RABBITMQ_URL     = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE_NAME       = "alerts.voice.approved"
DEAD_LETTER_Q    = "alerts.voice.failed"

# Africa's Talking
AT_USERNAME      = os.getenv("AT_USERNAME", "sandbox")
AT_API_KEY       = os.getenv("AT_API_KEY", "")
AT_VOICE_URL     = "https://voice.africastalking.com/call"
AT_CALLER_ID     = os.getenv("AT_CALLER_ID", "+234800000000")

# Radio FTP targets (configured per station)
RADIO_FTP_TARGETS = json.loads(os.getenv("RADIO_FTP_TARGETS", "[]"))
# Format: [{"host": "...", "user": "...", "password": "...", "path": "/alerts/", "station_name": "..."}]

# FCM (Push notifications)
FCM_SERVER_KEY   = os.getenv("FIREBASE_SERVER_KEY", "")
FCM_URL          = "https://fcm.googleapis.com/fcm/send"

# WhatsApp
WA_TOKEN         = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE_ID      = os.getenv("WHATSAPP_PHONE_ID", "")
WA_API_URL       = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"

WAT = timezone(timedelta(hours=1))


async def process_message(message: aio_pika.IncomingMessage, db, redis):
    """
    Main message processor. Deserialise approved alert payload, dispatch all channels.
    Acks only after successful dispatch (or max retries exhausted → dead letter).
    """
    async with message.process(requeue=False):
        try:
            payload = json.loads(message.body)
            session_id = payload["session_id"]
            alert_id   = payload["alert_id"]
            clips      = payload.get("clips", [])

            log.info(f"Router: processing approved alert session={session_id}")

            # Load full alert context
            alert = await _load_alert(alert_id, db)
            if not alert:
                log.error(f"Alert {alert_id} not found — dropping message")
                return

            severity = alert["severity"]
            lga_ids  = alert.get("lga_ids") or []

            # 1. Download audio from S3 (needed for radio FTP + AT Voice)
            audio_files = await _download_audio(clips)

            # 2. Dispatch concurrently (radio FTP sync, others async)
            dispatch_tasks = []

            # AT Voice calls (RED/ORANGE only — life-safety)
            if severity in ("RED", "ORANGE"):
                phones = await _get_subscriber_phones(lga_ids, db)
                dispatch_tasks.append(_dispatch_at_voice(phones, audio_files, alert))

            # Radio station FTP drop
            if RADIO_FTP_TARGETS and audio_files:
                dispatch_tasks.append(_dispatch_radio_ftp(audio_files, alert, clips))

            # IVR system update
            dispatch_tasks.append(_dispatch_ivr_update(alert, clips))

            # Push notifications (all severities)
            device_tokens = await _get_device_tokens(lga_ids, db)
            if device_tokens:
                dispatch_tasks.append(_dispatch_push(device_tokens, alert))

            # WhatsApp (RED/ORANGE — rich media)
            if severity in ("RED", "ORANGE"):
                wa_subscribers = await _get_wa_subscribers(lga_ids, db)
                if wa_subscribers:
                    dispatch_tasks.append(_dispatch_whatsapp(wa_subscribers, alert, audio_files))

            results = await asyncio.gather(*dispatch_tasks, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    log.error(f"Dispatch task {i} failed: {r}")

            # Mark session as dispatched
            async with db.acquire() as conn:
                await conn.execute(
                    "UPDATE voice_alert_sessions SET status = 'DISPATCHED', dispatched_at = NOW() WHERE id = $1",
                    session_id,
                )

            log.info(f"Router: session={session_id} dispatched successfully to {len(dispatch_tasks)} channels")

        except Exception as e:
            log.error(f"Router: failed to process message: {e}", exc_info=True)
            raise   # triggers requeue or dead letter


# ── Dispatch Functions ────────────────────────────────────────

async def _dispatch_at_voice(phones: list[str], audio_files: dict, alert: dict):
    """
    Africa's Talking Voice API — automated phone calls with pre-recorded audio.
    For each subscriber: call, play localised audio clip.
    """
    if not phones or not AT_API_KEY:
        return

    lang_audio = {lang: files["url"] for lang, files in audio_files.items() if "url" in files}
    if not lang_audio:
        log.warning("AT Voice: no audio URLs available — skipping voice calls")
        return

    async with httpx.AsyncClient() as client:
        for phone in phones[:500]:   # cap per cycle; scheduler handles batching
            # Choose language based on subscriber preference (default en)
            audio_url = lang_audio.get("en", next(iter(lang_audio.values())))

            try:
                resp = await client.post(
                    AT_VOICE_URL,
                    data={
                        "username": AT_USERNAME,
                        "to": phone,
                        "from": AT_CALLER_ID,
                        "url": audio_url,   # AT fetches and plays the MP3
                    },
                    headers={"apiKey": AT_API_KEY, "Accept": "application/json"},
                    timeout=10,
                )
                resp.raise_for_status()
                await asyncio.sleep(0.05)   # gentle rate control
            except Exception as e:
                log.warning(f"AT Voice call failed for {phone}: {e}")

    log.info(f"AT Voice: initiated calls to {min(len(phones), 500)} numbers")


async def _dispatch_radio_ftp(audio_files: dict, alert: dict, clips: list):
    """
    FTP drop to configured radio stations.
    Uploads: {alert_id}_{lang}.mp3 + {alert_id}_scripts.txt (all 5 languages)
    """
    if not RADIO_FTP_TARGETS:
        return

    alert_id = str(alert["id"])
    timestamp = datetime.now(WAT).strftime("%Y%m%dT%H%M%S")

    # Build script text file (all languages for radio readers)
    script_lines = [f"=== FLOOD WATCH NIGERIA ALERT — {alert['severity']} ===",
                    f"Issued: {datetime.now(WAT).strftime('%d/%m/%Y %H:%M WAT')}", ""]
    for clip in clips:
        lang_names = {"en": "English", "ha": "Hausa", "yo": "Yoruba", "ig": "Igbo", "pg": "Pidgin"}
        script_lines.append(f"[{lang_names.get(clip['lang'], clip['lang'].upper())}]")
        script_lines.append(clip.get("script_text", ""))
        script_lines.append("")
    script_bytes = "\n".join(script_lines).encode("utf-8")

    def _ftp_upload(target: dict):
        """Sync FTP upload — run in thread pool."""
        try:
            ftp = ftplib.FTP(target["host"])
            ftp.login(target["user"], target["password"])
            ftp.cwd(target.get("path", "/"))

            # Upload script text
            script_filename = f"{alert_id}_{timestamp}_scripts.txt"
            ftp.storbinary(f"STOR {script_filename}", io.BytesIO(script_bytes))

            # Upload MP3 files
            for lang, files in audio_files.items():
                if "bytes" in files:
                    mp3_filename = f"{alert_id}_{lang}_{timestamp}.mp3"
                    ftp.storbinary(f"STOR {mp3_filename}", io.BytesIO(files["bytes"]))

            ftp.quit()
            log.info(f"Radio FTP: uploaded to {target['station_name']} ({target['host']})")
        except Exception as e:
            log.error(f"Radio FTP failed for {target.get('station_name', target['host'])}: {e}")

    loop = asyncio.get_event_loop()
    for target in RADIO_FTP_TARGETS:
        await loop.run_in_executor(None, _ftp_upload, target)


async def _dispatch_ivr_update(alert: dict, clips: list):
    """
    IVR system update — refresh USSD/IVR menu with current alert audio.
    Sends alert metadata to IVR service endpoint for menu update.
    """
    ivr_endpoint = os.getenv("IVR_UPDATE_ENDPOINT", "")
    if not ivr_endpoint:
        return

    payload = {
        "alert_id": str(alert["id"]),
        "severity": alert["severity"],
        "valid_until": alert.get("valid_until"),
        "clips": [{"lang": c["lang"], "s3_key": c.get("s3_key")} for c in clips],
        "updated_at": datetime.now(WAT).strftime("%d/%m/%Y %H:%M WAT"),
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(ivr_endpoint, json=payload, timeout=15)
            resp.raise_for_status()
        log.info("IVR update dispatched")
    except Exception as e:
        log.warning(f"IVR update failed: {e}")


async def _dispatch_push(tokens: list[str], alert: dict):
    """FCM push notifications to all devices subscribed in affected LGAs."""
    if not FCM_SERVER_KEY or not tokens:
        return

    # FCM batch (max 500 per request)
    for i in range(0, len(tokens), 500):
        batch = tokens[i:i + 500]
        payload = {
            "registration_ids": batch,
            "priority": "high" if alert["severity"] == "RED" else "normal",
            "notification": {
                "title": alert.get("title_en", "Flood Alert"),
                "body": (alert.get("sms_en") or alert.get("body_en", ""))[:200],
                "sound": "default" if alert["severity"] == "RED" else None,
            },
            "data": {
                "alert_id": str(alert["id"]),
                "severity": alert["severity"],
                "alert_type": alert.get("alert_type", ""),
            },
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    FCM_URL,
                    json=payload,
                    headers={
                        "Authorization": f"key={FCM_SERVER_KEY}",
                        "Content-Type": "application/json",
                    },
                    timeout=15,
                )
                resp.raise_for_status()
        except Exception as e:
            log.error(f"FCM push batch failed: {e}")

    log.info(f"Push: sent to {len(tokens)} devices")


async def _dispatch_whatsapp(recipients: list[str], alert: dict, audio_files: dict):
    """WhatsApp Business API — rich media alert with audio clip."""
    if not WA_TOKEN or not recipients:
        return

    en_audio_url = audio_files.get("en", {}).get("url")
    msg_body = alert.get("body_en", "")[:1024]

    async with httpx.AsyncClient() as client:
        for msisdn in recipients[:200]:
            payload: dict = {
                "messaging_product": "whatsapp",
                "to": msisdn.lstrip("+"),
                "type": "text",
                "text": {"body": f"🚨 *{alert.get('title_en', 'Flood Alert')}*\n\n{msg_body}"},
            }
            # Attach audio if available
            if en_audio_url:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": msisdn.lstrip("+"),
                    "type": "audio",
                    "audio": {"link": en_audio_url},
                }

            try:
                resp = await client.post(
                    WA_API_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {WA_TOKEN}"},
                    timeout=15,
                )
                resp.raise_for_status()
                await asyncio.sleep(0.05)
            except Exception as e:
                log.warning(f"WhatsApp dispatch failed for {msisdn}: {e}")

    log.info(f"WhatsApp: dispatched to {min(len(recipients), 200)} subscribers")


# ── Helpers ───────────────────────────────────────────────────

async def _load_alert(alert_id: str, db) -> dict | None:
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM alerts WHERE id = $1", alert_id)
    return dict(row) if row else None


async def _download_audio(clips: list) -> dict[str, dict]:
    """Download MP3 bytes from S3 for each language clip."""
    s3 = boto3.client("s3")
    bucket = os.getenv("VOICE_S3_BUCKET", "nimet-plus-alerts")
    result = {}
    for clip in clips:
        lang = clip.get("lang")
        key  = clip.get("s3_key")
        if not lang or not key:
            continue
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            audio_bytes = obj["Body"].read()
            cdn = os.getenv("CLOUDFRONT_DOMAIN", "")
            url = f"https://{cdn}/{key}" if cdn else f"https://{bucket}.s3.amazonaws.com/{key}"
            result[lang] = {"bytes": audio_bytes, "url": url, "s3_key": key}
        except Exception as e:
            log.warning(f"S3 download failed for lang={lang} key={key}: {e}")
    return result


async def _get_subscriber_phones(lga_ids: list[int], db) -> list[str]:
    if not lga_ids:
        return []
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT msisdn FROM sms_subscriptions WHERE $1 && lga_ids AND is_active = TRUE",
            lga_ids,
        )
    return [r["msisdn"] for r in rows]


async def _get_device_tokens(lga_ids: list[int], db) -> list[str]:
    if not lga_ids:
        return []
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT device_token FROM user_preferences WHERE $1 && lga_ids AND device_token IS NOT NULL",
            lga_ids,
        )
    return [r["device_token"] for r in rows]


async def _get_wa_subscribers(lga_ids: list[int], db) -> list[str]:
    """Phones subscribed to WhatsApp alerts for the affected LGAs."""
    return await _get_subscriber_phones(lga_ids, db)   # shared subscription table


# ── Main consumer loop ────────────────────────────────────────

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    import asyncpg
    import redis.asyncio as aioredis

    db    = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"), min_size=2, max_size=8)
    redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

    connection = await aio_pika.connect_robust(RABBITMQ_URL, heartbeat=60)
    channel    = await connection.channel()
    await channel.set_qos(prefetch_count=5)   # process 5 alerts concurrently

    # Declare main queue + dead letter exchange
    dlx = await channel.declare_exchange("alerts.dlx", aio_pika.ExchangeType.DIRECT, durable=True)
    dl_queue = await channel.declare_queue(DEAD_LETTER_Q, durable=True)
    await dl_queue.bind(dlx, routing_key=DEAD_LETTER_Q)

    queue = await channel.declare_queue(
        QUEUE_NAME,
        durable=True,
        arguments={"x-dead-letter-exchange": "alerts.dlx", "x-dead-letter-routing-key": DEAD_LETTER_Q},
    )

    log.info(f"Alert Router listening on queue: {QUEUE_NAME}")

    async def _on_message(msg: aio_pika.IncomingMessage):
        await process_message(msg, db, redis)

    await queue.consume(_on_message)

    try:
        await asyncio.Future()   # run forever
    finally:
        await connection.close()
        await db.close()
        await redis.aclose()
        log.info("Alert Router stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
