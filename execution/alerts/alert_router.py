"""
Alert Router Microservice — Redis Streams Consumer
Replaces RabbitMQ (aio_pika) with Redis Streams so no extra broker is needed.

Stream:  alerts:voice:approved  (producer: voice_pipeline on approval)
DLQ:     alerts:voice:failed    (messages that fail after MAX_RETRIES)
Group:   alert-router

Dispatches to:
  1. Africa's Talking Voice API — automated phone calls
  2. Radio station FTP drop    — WAV file + script text
  3. IVR system update         — USSD/IVR menu refresh
  4. Push notifications        — FCM (Android) + APNs (iOS)
  5. WhatsApp Business API     — rich media alert message

Run: python -m execution.alerts.alert_router
"""
import asyncio
import json
import logging
import os
import ftplib
import io
from datetime import datetime, timezone, timedelta

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

STREAM_KEY     = "alerts:voice:approved"
FAILED_KEY     = "alerts:voice:failed"
GROUP_NAME     = "alert-router"
CONSUMER_NAME  = "router-1"
BLOCK_MS       = 5_000    # block XREADGROUP call for 5s before polling again
MAX_RETRIES    = 3        # before moving to failed stream

# Africa's Talking
AT_USERNAME    = os.getenv("AT_USERNAME", "sandbox")
AT_API_KEY     = os.getenv("AT_API_KEY", "")
AT_VOICE_URL   = "https://voice.africastalking.com/call"
AT_CALLER_ID   = os.getenv("AT_CALLER_ID", "+234800000000")

# Radio FTP targets (configured per station)
RADIO_FTP_TARGETS = json.loads(os.getenv("RADIO_FTP_TARGETS", "[]"))

# FCM (Push notifications)
FCM_SERVER_KEY = os.getenv("FIREBASE_SERVER_KEY", "")
FCM_URL        = "https://fcm.googleapis.com/fcm/send"

# WhatsApp
WA_TOKEN       = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE_ID    = os.getenv("WHATSAPP_PHONE_ID", "")
WA_API_URL     = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"

WAT = timezone(timedelta(hours=1))


# ── Message processing ────────────────────────────────────────

async def process_message(msg_id: str, payload: dict, db, redis):
    """Deserialise approved alert payload and dispatch to all channels."""
    try:
        session_id = payload["session_id"]
        alert_id   = payload["alert_id"]
        clips      = payload.get("clips", [])

        log.info(f"Router: processing session={session_id} alert={alert_id}")

        alert = await _load_alert(alert_id, db)
        if not alert:
            log.error(f"Alert {alert_id} not found — skipping")
            return True   # ack to avoid retry loop on bad data

        severity = alert["severity"]
        lga_ids  = alert.get("lga_ids") or []

        audio_files = await _download_audio(clips)

        dispatch_tasks = []

        if severity in ("RED", "ORANGE"):
            phones = await _get_subscriber_phones(lga_ids, db)
            dispatch_tasks.append(_dispatch_at_voice(phones, audio_files, alert))

        if RADIO_FTP_TARGETS and audio_files:
            dispatch_tasks.append(_dispatch_radio_ftp(audio_files, alert, clips))

        dispatch_tasks.append(_dispatch_ivr_update(alert, clips))

        device_tokens = await _get_device_tokens(lga_ids, db)
        if device_tokens:
            dispatch_tasks.append(_dispatch_push(device_tokens, alert))

        if severity in ("RED", "ORANGE"):
            wa_subs = await _get_wa_subscribers(lga_ids, db)
            if wa_subs:
                dispatch_tasks.append(_dispatch_whatsapp(wa_subs, alert, audio_files))

        results = await asyncio.gather(*dispatch_tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log.error(f"Dispatch task {i} failed: {r}")

        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE voice_alert_sessions SET status = 'DISPATCHED', dispatched_at = NOW() WHERE id = $1",
                session_id,
            )

        log.info(f"Router: session={session_id} dispatched to {len(dispatch_tasks)} channels")
        return True

    except Exception as e:
        log.error(f"Router: failed to process message {msg_id}: {e}", exc_info=True)
        return False


# ── Dispatch Functions ────────────────────────────────────────

async def _dispatch_at_voice(phones: list, audio_files: dict, alert: dict):
    if not phones or not AT_API_KEY:
        return
    lang_audio = {lang: files["url"] for lang, files in audio_files.items() if "url" in files}
    if not lang_audio:
        log.warning("AT Voice: no audio URLs — skipping")
        return
    async with httpx.AsyncClient() as client:
        for phone in phones[:500]:
            audio_url = lang_audio.get("en", next(iter(lang_audio.values())))
            try:
                resp = await client.post(
                    AT_VOICE_URL,
                    data={"username": AT_USERNAME, "to": phone,
                          "from": AT_CALLER_ID, "url": audio_url},
                    headers={"apiKey": AT_API_KEY, "Accept": "application/json"},
                    timeout=10,
                )
                resp.raise_for_status()
                await asyncio.sleep(0.05)
            except Exception as e:
                log.warning(f"AT Voice failed for {phone}: {e}")
    log.info(f"AT Voice: initiated calls to {min(len(phones), 500)} numbers")


async def _dispatch_radio_ftp(audio_files: dict, alert: dict, clips: list):
    if not RADIO_FTP_TARGETS:
        return
    alert_id  = str(alert["id"])
    timestamp = datetime.now(WAT).strftime("%Y%m%dT%H%M%S")
    lang_names = {"en": "English", "ha": "Hausa", "yo": "Yoruba", "ig": "Igbo", "pg": "Pidgin"}
    script_lines = [
        f"=== FLOOD WATCH NIGERIA ALERT — {alert['severity']} ===",
        f"Issued: {datetime.now(WAT).strftime('%d/%m/%Y %H:%M WAT')}", ""
    ]
    for clip in clips:
        script_lines.append(f"[{lang_names.get(clip['lang'], clip['lang'].upper())}]")
        script_lines.append(clip.get("script_text", ""))
        script_lines.append("")
    script_bytes = "\n".join(script_lines).encode("utf-8")

    def _ftp_upload(target: dict):
        try:
            ftp = ftplib.FTP(target["host"])
            ftp.login(target["user"], target["password"])
            ftp.cwd(target.get("path", "/"))
            ftp.storbinary(f"STOR {alert_id}_{timestamp}_scripts.txt", io.BytesIO(script_bytes))
            for lang, files in audio_files.items():
                if "bytes" in files:
                    ftp.storbinary(f"STOR {alert_id}_{lang}_{timestamp}.mp3",
                                   io.BytesIO(files["bytes"]))
            ftp.quit()
            log.info(f"Radio FTP: uploaded to {target['station_name']}")
        except Exception as e:
            log.error(f"Radio FTP failed for {target.get('station_name')}: {e}")

    loop = asyncio.get_event_loop()
    for target in RADIO_FTP_TARGETS:
        await loop.run_in_executor(None, _ftp_upload, target)


async def _dispatch_ivr_update(alert: dict, clips: list):
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


async def _dispatch_push(tokens: list, alert: dict):
    if not FCM_SERVER_KEY or not tokens:
        return
    for i in range(0, len(tokens), 500):
        batch = tokens[i:i + 500]
        payload = {
            "registration_ids": batch,
            "priority": "high" if alert["severity"] == "RED" else "normal",
            "notification": {
                "title": alert.get("title_en", "Flood Alert"),
                "body":  (alert.get("sms_en") or alert.get("body_en", ""))[:200],
                "sound": "default" if alert["severity"] == "RED" else None,
            },
            "data": {"alert_id": str(alert["id"]), "severity": alert["severity"],
                     "alert_type": alert.get("alert_type", "")},
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    FCM_URL, json=payload,
                    headers={"Authorization": f"key={FCM_SERVER_KEY}",
                             "Content-Type": "application/json"},
                    timeout=15,
                )
                resp.raise_for_status()
        except Exception as e:
            log.error(f"FCM push batch failed: {e}")
    log.info(f"Push: sent to {len(tokens)} devices")


async def _dispatch_whatsapp(recipients: list, alert: dict, audio_files: dict):
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
            if en_audio_url:
                payload = {"messaging_product": "whatsapp", "to": msisdn.lstrip("+"),
                           "type": "audio", "audio": {"link": en_audio_url}}
            try:
                resp = await client.post(WA_API_URL, json=payload,
                                         headers={"Authorization": f"Bearer {WA_TOKEN}"},
                                         timeout=15)
                resp.raise_for_status()
                await asyncio.sleep(0.05)
            except Exception as e:
                log.warning(f"WhatsApp failed for {msisdn}: {e}")
    log.info(f"WhatsApp: dispatched to {min(len(recipients), 200)} subscribers")


# ── DB helpers ────────────────────────────────────────────────

async def _load_alert(alert_id: str, db):
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM alerts WHERE id = $1", alert_id)
    return dict(row) if row else None


async def _download_audio(clips: list) -> dict:
    """Download MP3s from S3 if VOICE_S3_BUCKET is set; otherwise return empty."""
    bucket = os.getenv("VOICE_S3_BUCKET", "")
    if not bucket:
        return {}
    try:
        import boto3
        s3 = boto3.client("s3")
    except Exception:
        return {}
    result = {}
    cdn = os.getenv("CLOUDFRONT_DOMAIN", "")
    for clip in clips:
        lang = clip.get("lang")
        key  = clip.get("s3_key")
        if not lang or not key:
            continue
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            audio_bytes = obj["Body"].read()
            url = f"https://{cdn}/{key}" if cdn else f"https://{bucket}.s3.amazonaws.com/{key}"
            result[lang] = {"bytes": audio_bytes, "url": url, "s3_key": key}
        except Exception as e:
            log.warning(f"S3 download failed lang={lang} key={key}: {e}")
    return result


async def _get_subscriber_phones(lga_ids: list, db) -> list:
    if not lga_ids:
        return []
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT msisdn FROM sms_subscriptions WHERE $1 && lga_ids AND is_active = TRUE",
            lga_ids)
    return [r["msisdn"] for r in rows]


async def _get_device_tokens(lga_ids: list, db) -> list:
    if not lga_ids:
        return []
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT device_token FROM user_preferences WHERE $1 && lga_ids AND device_token IS NOT NULL",
            lga_ids)
    return [r["device_token"] for r in rows]


async def _get_wa_subscribers(lga_ids: list, db) -> list:
    return await _get_subscriber_phones(lga_ids, db)


# ── Main consumer loop (Redis Streams) ───────────────────────

async def _ensure_consumer_group(redis):
    """Create stream + consumer group if they don't exist yet."""
    try:
        await redis.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        log.info(f"Created consumer group '{GROUP_NAME}' on stream '{STREAM_KEY}'")
    except Exception as e:
        if "BUSYGROUP" in str(e):
            log.info(f"Consumer group '{GROUP_NAME}' already exists — OK")
        else:
            raise


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    import asyncpg
    import redis.asyncio as aioredis

    # Connect to DB with retry (Render services may start before DB is ready)
    db = None
    for attempt in range(1, 6):
        try:
            db = await asyncpg.create_pool(
                dsn=os.getenv("DATABASE_URL"), min_size=2, max_size=8)
            log.info("DB pool ready")
            break
        except Exception as e:
            log.warning(f"DB connect attempt {attempt}/5 failed: {e}")
            if attempt == 5:
                log.error("DB unavailable — exiting")
                raise SystemExit(1)
            await asyncio.sleep(attempt * 3)

    # Connect to Redis with retry
    redis_client = None
    for attempt in range(1, 4):
        try:
            redis_client = aioredis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379"),
                decode_responses=True,
            )
            await redis_client.ping()
            log.info("Redis ready")
            break
        except Exception as e:
            log.warning(f"Redis connect attempt {attempt}/3 failed: {e}")
            if attempt == 3:
                log.error("Redis unavailable — exiting")
                raise SystemExit(1)
            await asyncio.sleep(attempt * 3)

    await _ensure_consumer_group(redis_client)

    log.info(f"Alert Router listening on Redis stream: {STREAM_KEY} (group={GROUP_NAME})")

    retry_counts: dict = {}   # msg_id → retry count

    try:
        while True:
            try:
                # Read up to 5 new messages (or pending on restart)
                results = await redis_client.xreadgroup(
                    groupname=GROUP_NAME,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_KEY: ">"},
                    count=5,
                    block=BLOCK_MS,
                )
            except Exception as e:
                log.error(f"XREADGROUP error: {e} — retrying in 5s")
                await asyncio.sleep(5)
                continue

            if not results:
                continue   # timeout, no messages — loop

            for _stream, messages in results:
                for msg_id, fields in messages:
                    raw = fields.get("payload", "{}")
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        log.error(f"Bad JSON in message {msg_id} — moving to failed stream")
                        await redis_client.xadd(FAILED_KEY, {"msg_id": msg_id, "payload": raw, "error": "json_decode"})
                        await redis_client.xack(STREAM_KEY, GROUP_NAME, msg_id)
                        continue

                    success = await process_message(msg_id, payload, db, redis_client)

                    if success:
                        await redis_client.xack(STREAM_KEY, GROUP_NAME, msg_id)
                        retry_counts.pop(msg_id, None)
                    else:
                        count = retry_counts.get(msg_id, 0) + 1
                        retry_counts[msg_id] = count
                        if count >= MAX_RETRIES:
                            log.error(f"Message {msg_id} failed {count} times — moving to failed stream")
                            await redis_client.xadd(FAILED_KEY, {"msg_id": msg_id, "payload": raw})
                            await redis_client.xack(STREAM_KEY, GROUP_NAME, msg_id)
                            retry_counts.pop(msg_id, None)
                        else:
                            log.warning(f"Message {msg_id} failed (attempt {count}/{MAX_RETRIES}) — will retry")

    finally:
        await db.close()
        await redis_client.aclose()
        log.info("Alert Router stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
