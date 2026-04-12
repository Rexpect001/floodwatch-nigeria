"""
Mass Notification Dispatcher
Channels: SMS (Africa's Talking) · WhatsApp (Meta Graph API) · Push (FCM)
Fallback: Twilio SMS

Geofenced targeting:
  - Queries sms_subscriptions / push_subscriptions / whatsapp_subscriptions
    filtered by lga_ids and severity_threshold
  - Security alerts only sent to subscribers who opted in (security_alerts=TRUE)

Batching:
  - SMS: 1,000 recipients per AT call (concurrent tasks per language)
  - FCM: 500 tokens per batch
  - WhatsApp: 200 per batch (Meta rate limit)

Run: python -m execution.alerts.sms_dispatcher (test mode)
"""
import asyncio
import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

# ── Africa's Talking ──────────────────────────────────────────
AT_USERNAME  = os.getenv("AT_USERNAME", "sandbox")
AT_API_KEY   = os.getenv("AT_API_KEY", "")
AT_SENDER_ID = os.getenv("AT_SENDER_ID", "HazardWatch")
AT_BASE_URL  = "https://api.africastalking.com/version1/messaging"

# ── Twilio fallback ───────────────────────────────────────────
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM  = os.getenv("TWILIO_PHONE_FROM", "")

# ── Firebase Cloud Messaging ──────────────────────────────────
FCM_SERVER_KEY = os.getenv("FIREBASE_SERVER_KEY", "")
FCM_URL        = "https://fcm.googleapis.com/fcm/send"

# ── WhatsApp Business API (Meta Graph) ────────────────────────
WA_TOKEN    = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
WA_URL      = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"

MAX_SMS_BATCH = 1000
MAX_FCM_BATCH = 500
MAX_WA_BATCH  = 200
RETRY_LIMIT   = 3

# Security alert types — require explicit opt-in from subscriber
SECURITY_TYPES = {
    "BANDITRY", "INSURGENCY", "COMMUNAL_CONFLICT",
    "CIVIL_UNREST", "KIDNAPPING_HOTSPOT", "TERRORISM", "ARMED_CLASH",
}


async def dispatch_alert(alert: dict, db_pool=None):
    """
    Master dispatch: routes alert to SMS + Push + WhatsApp based on severity.
    All channels run concurrently. Geofenced to affected LGAs only.
    """
    severity   = alert.get("severity", "YELLOW")
    alert_type = alert.get("alert_type") or alert.get("event", "")
    is_security = alert_type in SECURITY_TYPES
    lga_ids    = alert.get("lga_ids") or (
                     [alert["lga_id"]] if alert.get("lga_id") else []
                 )

    if severity not in ("RED", "ORANGE"):
        # YELLOW → push only (no SMS, no WhatsApp)
        if severity == "YELLOW" and db_pool:
            tokens = await _get_push_tokens(lga_ids, severity, is_security, db_pool)
            await _dispatch_push(tokens, alert)
        return

    log.info(f"Dispatching {severity} alert (type={alert_type}) to LGAs {lga_ids}")

    if db_pool:
        sms_subs, push_tokens, wa_numbers = await asyncio.gather(
            _get_sms_subscribers(lga_ids, severity, is_security, db_pool),
            _get_push_tokens(lga_ids, severity, is_security, db_pool),
            _get_whatsapp_numbers(lga_ids, severity, is_security, db_pool),
        )
        await asyncio.gather(
            _dispatch_sms(sms_subs, alert),
            _dispatch_push(push_tokens, alert),
            _dispatch_whatsapp(wa_numbers, alert),
            return_exceptions=True,
        )
    else:
        log.warning("No DB pool — dry-run mode, no subscribers fetched")


# ── Subscriber fetchers (geofenced) ──────────────────────────

async def _get_sms_subscribers(
    lga_ids: list[int], severity: str, is_security: bool, db_pool
) -> list[tuple[str, str]]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT msisdn, lang
            FROM sms_subscriptions
            WHERE is_active = TRUE
              AND lga_ids && $1::integer[]
              AND CASE severity_threshold
                    WHEN 'RED'    THEN 1
                    WHEN 'ORANGE' THEN 2
                    WHEN 'YELLOW' THEN 3
                    ELSE 4
                  END >= CASE $2::text
                    WHEN 'RED'    THEN 1
                    WHEN 'ORANGE' THEN 2
                    WHEN 'YELLOW' THEN 3
                    ELSE 4
                  END
              AND ($3::boolean = FALSE OR security_alerts = TRUE)
        """, lga_ids, severity, is_security)
        return [(r["msisdn"], r["lang"]) for r in rows]


async def _get_push_tokens(
    lga_ids: list[int], severity: str, is_security: bool, db_pool
) -> list[tuple[str, str]]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT fcm_token, lang
            FROM push_subscriptions
            WHERE is_active = TRUE
              AND lga_ids && $1::integer[]
              AND CASE severity_threshold
                    WHEN 'RED'    THEN 1
                    WHEN 'ORANGE' THEN 2
                    WHEN 'YELLOW' THEN 3
                    ELSE 4
                  END >= CASE $2::text
                    WHEN 'RED'    THEN 1
                    WHEN 'ORANGE' THEN 2
                    WHEN 'YELLOW' THEN 3
                    ELSE 4
                  END
              AND ($3::boolean = FALSE OR security_alerts = TRUE)
        """, lga_ids, severity, is_security)
        return [(r["fcm_token"], r["lang"]) for r in rows]


async def _get_whatsapp_numbers(
    lga_ids: list[int], severity: str, is_security: bool, db_pool
) -> list[tuple[str, str]]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT wa_id, lang
            FROM whatsapp_subscriptions
            WHERE is_active = TRUE AND opted_in = TRUE
              AND lga_ids && $1::integer[]
              AND CASE severity_threshold
                    WHEN 'RED'    THEN 1
                    WHEN 'ORANGE' THEN 2
                    WHEN 'YELLOW' THEN 3
                    ELSE 4
                  END >= CASE $2::text
                    WHEN 'RED'    THEN 1
                    WHEN 'ORANGE' THEN 2
                    WHEN 'YELLOW' THEN 3
                    ELSE 4
                  END
              AND ($3::boolean = FALSE OR security_alerts = TRUE)
        """, lga_ids, severity, is_security)
        return [(r["wa_id"], r["lang"]) for r in rows]


# ── SMS ───────────────────────────────────────────────────────

async def _dispatch_sms(subscribers: list[tuple[str, str]], alert: dict):
    if not subscribers:
        return
    by_lang: dict[str, list[str]] = {}
    for msisdn, lang in subscribers:
        by_lang.setdefault(lang, []).append(msisdn)

    tasks = []
    for lang, phones in by_lang.items():
        body = alert.get(f"sms_{lang}") or alert.get("sms_en", "")
        if not body:
            continue
        for i in range(0, len(phones), MAX_SMS_BATCH):
            tasks.append(_send_sms_batch(phones[i:i + MAX_SMS_BATCH], body, alert.get("id", ""), lang))

    log.info(f"SMS: {len(subscribers)} subscribers, {len(by_lang)} languages")
    await asyncio.gather(*tasks, return_exceptions=True)


async def _send_sms_batch(
    phones: list[str], message: str, alert_id: str,
    lang: str, attempt: int = 0,
) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                AT_BASE_URL,
                data={"username": AT_USERNAME, "to": ",".join(phones),
                      "message": message, "from": AT_SENDER_ID},
                headers={"apiKey": AT_API_KEY, "Accept": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            log.info(f"AT SMS: {len(phones)} sent, lang={lang}")
            return resp.json()
    except httpx.HTTPError as e:
        if attempt < RETRY_LIMIT:
            await asyncio.sleep(5 * (2 ** attempt))
            return await _send_sms_batch(phones, message, alert_id, lang, attempt + 1)
        log.error(f"AT SMS failed after retries — falling back to Twilio")
        return await _send_sms_batch_twilio(phones, message, lang)


async def _send_sms_batch_twilio(phones: list[str], message: str, lang: str) -> dict:
    if not TWILIO_SID:
        log.error("Twilio not configured — SMS delivery failed")
        return {}
    from twilio.rest import Client
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    sent = 0
    for phone in phones:
        try:
            client.messages.create(body=message, from_=TWILIO_FROM, to=phone)
            sent += 1
        except Exception as e:
            log.error(f"Twilio failed for {phone}: {e}")
    log.info(f"Twilio fallback: {sent}/{len(phones)} sent, lang={lang}")
    return {"twilio_sent": sent}


# ── Push (FCM) ────────────────────────────────────────────────

async def _dispatch_push(tokens: list[tuple[str, str]], alert: dict):
    if not tokens or not FCM_SERVER_KEY:
        return
    severity = alert.get("severity", "YELLOW")
    title    = alert.get("title") or alert.get("title_en", "HazardWatch Alert")
    body     = (alert.get("body") or alert.get("body_en", ""))[:200]
    all_tokens = [t for t, _ in tokens]
    log.info(f"FCM Push: {len(all_tokens)} devices")

    for i in range(0, len(all_tokens), MAX_FCM_BATCH):
        batch = all_tokens[i:i + MAX_FCM_BATCH]
        payload = {
            "registration_ids": batch,
            "priority": "high" if severity == "RED" else "normal",
            "notification": {
                "title": title,
                "body":  body,
                "sound": "alert_critical" if severity == "RED" else "default",
                "badge": 1,
            },
            "data": {
                "alert_id":   str(alert.get("id", "")),
                "alert_type": alert.get("alert_type") or alert.get("event", ""),
                "severity":   severity,
            },
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    FCM_URL,
                    json=payload,
                    headers={"Authorization": f"key={FCM_SERVER_KEY}",
                             "Content-Type": "application/json"},
                    timeout=20,
                )
                resp.raise_for_status()
                r = resp.json()
                log.info(f"FCM batch: success={r.get('success')}, failure={r.get('failure')}")
        except httpx.HTTPError as e:
            log.error(f"FCM batch failed: {e}")


# ── WhatsApp ──────────────────────────────────────────────────

async def _dispatch_whatsapp(numbers: list[tuple[str, str]], alert: dict):
    if not numbers or not WA_TOKEN:
        return
    log.info(f"WhatsApp: {len(numbers)} subscribers")
    tasks = [_send_wa_batch(numbers[i:i + MAX_WA_BATCH], alert)
             for i in range(0, len(numbers), MAX_WA_BATCH)]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _send_wa_batch(numbers: list[tuple[str, str]], alert: dict):
    severity = alert.get("severity", "YELLOW")
    emoji    = {"RED": "🚨", "ORANGE": "⚠️", "YELLOW": "⚡"}.get(severity, "ℹ️")

    async with httpx.AsyncClient(timeout=30) as client:
        for wa_id, lang in numbers:
            body = (alert.get(f"sms_{lang}") or alert.get("sms_en") or
                    alert.get("body_en", ""))[:1000]
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type":    "individual",
                "to":  wa_id,
                "type": "text",
                "text": {"preview_url": False,
                         "body": f"{emoji} *HazardWatch Nigeria*\n\n{body}"},
            }
            try:
                resp = await client.post(
                    WA_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {WA_TOKEN}",
                             "Content-Type": "application/json"},
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                log.error(f"WhatsApp failed for {wa_id}: {e}")
            await asyncio.sleep(0.013)   # 80 msg/sec Meta rate limit


# ── Backward-compat alias ─────────────────────────────────────

async def dispatch_sms_alert(alert: dict, db_pool=None):
    """Kept for backward compatibility with alert_classifier."""
    await dispatch_alert(alert, db_pool)


# ── Test helpers ──────────────────────────────────────────────

async def send_test_sms(msisdn: str, lang: str = "en") -> dict:
    msgs = {
        "en": "HazardWatch Test: Your subscription is active. You will receive hazard & security alerts. Reply STOP to unsubscribe.",
        "ha": "HazardWatch Gwaji: Karatun ku na aiki. Za ku sami sanarwar hadari. Tura STOP don hana.",
        "yo": "HazardWatch Idanwo: Iforukọsilẹ rẹ n ṣiṣẹ. Iwọ yoo gba awọn itaniji. Firanṣẹ STOP lati fagilee.",
        "ig": "HazardWatch Nnwale: Ndebanye aha gị dị ọrụ. Ị ga-enweta ọdịmara. Zipu STOP iji kwụsị.",
        "pg": "HazardWatch Test: Your subscription dey work. You go receive hazard alerts. Send STOP to cancel.",
    }
    return await _send_sms_batch([msisdn], msgs.get(lang, msgs["en"]), "test", lang)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) >= 2:
        asyncio.run(send_test_sms(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "en"))
