"""
Alert Orchestration — Severity Classifier & Multilingual Payload Builder

Consumes Redis pub/sub events from ingestion services.
Rules:
  1. RED requires 2+ source confirmation (NEMA standard)
  2. Laggo Dam release → immediate cross-ref with NIHSA discharge
  3. Heatwave > 40°C → ORANGE; > 44°C → RED (2024 Sokoto 44.8°C record)
  4. Discharge > 2024 baseline → escalate severity
  5. Google Flood Hub inundation >= 20% → PROBABLE+ classification
  6. Deduplication: suppress duplicate alerts within 6h window

Run: python -m execution.alerts.alert_classifier
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as aioredis
from dotenv import load_dotenv

from .sms_dispatcher import dispatch_sms_alert
from .multilingual import build_multilingual_payload

load_dotenv()
log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Thresholds
HEATWAVE_ORANGE_C = 40.0
HEATWAVE_RED_C    = 44.0    # near 2024 Sokoto record 44.8°C
FLOOD_HUB_INUNDATION_THRESHOLD = 20.0  # % community area
DEDUP_WINDOW_H    = 6       # hours


@dataclass
class AlertEvent:
    event_type: str
    lga_id: Optional[int]
    community_id: Optional[int]
    source: str
    severity_hint: str
    data: dict


async def classify_and_publish(event: AlertEvent, redis) -> Optional[dict]:
    """
    Classify an event into RED/ORANGE/YELLOW/GREEN.
    For RED: verify 2+ sources before creating alert.
    Returns the alert dict if published, None if suppressed.
    """
    severity = _compute_severity(event)
    if severity == "GREEN":
        return None   # GREEN = in-app only, no alert record needed at this stage

    # Deduplication check
    dedup_key = f"alert:dedup:{event.event_type}:{event.lga_id}:{severity}"
    if await redis.get(dedup_key):
        log.debug(f"Suppressed duplicate alert: {dedup_key}")
        return None

    # RED requires 2-source confirmation
    if severity == "RED":
        confirmed = await _confirm_red_alert(event, redis)
        if not confirmed:
            log.info(f"RED alert pending 2nd source confirmation: lga={event.lga_id}")
            # Store as pending; will be promoted when 2nd source arrives
            await _store_pending_red(event, redis)
            return None

    alert = await _build_alert(event, severity, redis)
    await _persist_alert(alert, redis)
    await _dispatch_alert(alert, severity, redis)

    # Set dedup key
    await redis.setex(dedup_key, DEDUP_WINDOW_H * 3600, "1")
    return alert


def _compute_severity(event: AlertEvent) -> str:
    """Deterministic severity from event data."""
    data = event.data

    if event.event_type == "HEATWAVE_RISK":
        temp = data.get("temp_max_c", 0)
        if temp >= HEATWAVE_RED_C:
            return "RED"
        elif temp >= HEATWAVE_ORANGE_C:
            return "ORANGE"
        return "GREEN"

    if event.event_type in ("FLOOD_RIVERINE", "FLOOD_RISK"):
        prob = data.get("probability_pct", 0)
        afo = data.get("afo_class")
        inundation = data.get("inundation_pct", 0)
        discharge = data.get("discharge_m3s", 0)
        baseline_2024 = data.get("baseline_2024_m3s", 0)

        # Google Flood Hub: 20% inundation threshold
        if inundation >= FLOOD_HUB_INUNDATION_THRESHOLD:
            severity = "ORANGE"
        elif afo == "HIGHLY_PROBABLE" or prob >= 75:
            severity = "ORANGE"
        elif afo == "PROBABLE" or prob >= 40:
            severity = "YELLOW"
        else:
            severity = "GREEN"

        # Escalate to RED if discharge exceeds 2024 flood baseline
        if baseline_2024 > 0 and discharge >= baseline_2024:
            severity = "RED"

        return severity

    if event.event_type == "DAM_RELEASE":
        release_m3s = data.get("release_m3s", 0)
        if release_m3s > 5000:   # major release — 2024 Alau baseline
            return "RED"
        return "ORANGE"

    if event.event_type == "EVACUATION":
        return "RED"

    return event.severity_hint or "YELLOW"


async def _confirm_red_alert(event: AlertEvent, redis) -> bool:
    """
    RED alerts require 2+ source confirmation.
    Check if a corroborating event exists in the confirmation cache.
    """
    sources_key = f"red:sources:{event.event_type}:{event.lga_id}"
    existing = await redis.smembers(sources_key)

    # Add current source
    await redis.sadd(sources_key, event.source)
    await redis.expire(sources_key, 3600)  # 1h window for confirmation

    all_sources = existing | {event.source.encode()}
    confirmed = len(all_sources) >= 2
    if confirmed:
        log.info(f"RED confirmed by {len(all_sources)} sources: {all_sources}")
    return confirmed


async def _store_pending_red(event: AlertEvent, redis):
    """Store pending RED awaiting 2nd-source confirmation."""
    key = f"red:pending:{event.event_type}:{event.lga_id}"
    await redis.setex(key, 3600, json.dumps(event.__dict__))


async def _build_alert(event: AlertEvent, severity: str, redis) -> dict:
    """Build full multilingual alert payload."""
    payload = build_multilingual_payload(event, severity)
    return payload


async def _persist_alert(alert: dict, redis):
    """Publish to Redis; ingestion API persists to PostgreSQL."""
    await redis.publish("new_alerts", json.dumps(alert, default=str))
    # Also push to high-priority queue for RED
    if alert.get("severity") == "RED":
        await redis.lpush("alerts:red:queue", json.dumps(alert, default=str))


async def _dispatch_alert(alert: dict, severity: str, redis):
    """Route to correct dispatch channels based on severity."""
    if severity in ("RED", "ORANGE"):
        await dispatch_sms_alert(alert)   # SMS + Push + WhatsApp
    elif severity == "YELLOW":
        pass   # Push + in-app only


async def main():
    """Subscribe to Redis channels and process events."""
    r = aioredis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe("weather_events", "flood_events", "dam_releases", "nema_alerts")
    log.info("Alert classifier listening on Redis channels...")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            event = AlertEvent(
                event_type=data.get("event", "UNKNOWN"),
                lga_id=data.get("lga_id"),
                community_id=data.get("community_id"),
                source=data.get("source", "UNKNOWN"),
                severity_hint=data.get("severity_hint", "YELLOW"),
                data=data,
            )
            await classify_and_publish(event, r)
        except Exception as e:
            log.error(f"Classifier error: {e}", exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
