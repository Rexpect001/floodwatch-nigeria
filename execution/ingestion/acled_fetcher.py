"""
ACLED Ingestion — Armed Conflict Location & Event Data
https://acleddata.com/acleddatanew/wp-content/uploads/2021/11/ACLED_API_User-Guide.pdf

Fetches armed conflict events for Nigeria, classifies severity,
creates security alerts for RED/ORANGE incidents.

Severity rules:
  RED    — fatalities > 5, or event_type TERRORISM / INSURGENCY
  ORANGE — fatalities 1–5, or BANDITRY / KIDNAPPING_HOTSPOT
  YELLOW — CIVIL_UNREST / COMMUNAL_CONFLICT with no fatalities
  GREEN  — PROTEST (non-violent)

Schedule: every 6h (ACLED updates daily, but we check frequently for breaking events)

Run: python -m execution.ingestion.acled_fetcher
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

ACLED_API_KEY   = os.getenv("ACLED_API_KEY", "")
ACLED_EMAIL     = os.getenv("ACLED_EMAIL", "")
ACLED_BASE_URL  = "https://api.acleddata.com/acled/read"
REDIS_URL       = os.getenv("REDIS_URL", "redis://localhost:6379")

# ACLED event_type → our internal event type
ACLED_TYPE_MAP: dict[str, str] = {
    "Battles":                          "ARMED_CLASH",
    "Violence against civilians":       "BANDITRY",
    "Explosions/Remote violence":       "TERRORISM",
    "Riots":                            "CIVIL_UNREST",
    "Protests":                         "CIVIL_UNREST",
    "Strategic developments":          "OTHER",
}

# ACLED sub_event_type → more specific mapping
ACLED_SUBTYPE_MAP: dict[str, str] = {
    "Armed clash":                      "ARMED_CLASH",
    "Government regains territory":     "INSURGENCY",
    "Non-state actor overtakes territory": "INSURGENCY",
    "Attack":                           "BANDITRY",
    "Abduction/forced disappearance":   "KIDNAPPING_HOTSPOT",
    "Sexual violence":                  "BANDITRY",
    "Looting/property destruction":     "COMMUNAL_CONFLICT",
    "Mob violence":                     "COMMUNAL_CONFLICT",
    "Grenade":                          "TERRORISM",
    "Suicide bomb":                     "TERRORISM",
    "Remote explosive/landmine/IED":    "TERRORISM",
    "Shelling/artillery/missile attack": "INSURGENCY",
    "Air/drone strike":                 "INSURGENCY",
    "Protest with intervention":        "CIVIL_UNREST",
    "Violent demonstration":            "CIVIL_UNREST",
}

# Nigerian states known for specific threats (for advisory context)
SECURITY_HOTSPOTS: dict[str, list[str]] = {
    "INSURGENCY":        ["Borno", "Yobe", "Adamawa"],
    "BANDITRY":          ["Zamfara", "Sokoto", "Kaduna", "Katsina", "Niger"],
    "KIDNAPPING_HOTSPOT": ["Abuja Federal Capital Territory", "Kaduna", "Niger", "Ondo"],
    "COMMUNAL_CONFLICT": ["Plateau", "Benue", "Taraba", "Nassarawa"],
    "TERRORISM":         ["Borno", "Yobe", "Adamawa", "Kogi"],
}


@dataclass
class AcledEvent:
    acled_id: int
    event_date: date
    event_type: str          # our internal type
    actor1: str
    actor2: str
    fatalities: int
    location: str
    state_name: str
    lga_name: str
    lat: float
    lng: float
    notes: str
    source: str
    source_scale: str


async def fetch_recent_events(days_back: int = 7) -> list[AcledEvent]:
    """
    Pull ACLED events for Nigeria from the last N days.
    Uses ACLED REST API with key + email authentication.
    """
    if not ACLED_API_KEY or not ACLED_EMAIL:
        log.warning("ACLED_API_KEY / ACLED_EMAIL not set — skipping security ingestion")
        return []

    since = (date.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    params = {
        "key":           ACLED_API_KEY,
        "email":         ACLED_EMAIL,
        "country":       "Nigeria",
        "event_date":    since,
        "event_date_where": ">=",
        "limit":         500,
        "fields":        "data_id|event_date|event_type|sub_event_type|actor1|actor2|"
                         "fatalities|location|admin1|admin2|latitude|longitude|notes|source|source_scale",
        "format":        "json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(ACLED_BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.error(f"ACLED API error: {e}")
        return []

    raw_events = data.get("data", [])
    log.info(f"ACLED: fetched {len(raw_events)} events for Nigeria (last {days_back}d)")

    events: list[AcledEvent] = []
    for r in raw_events:
        internal_type = _classify_acled_type(
            r.get("event_type", ""),
            r.get("sub_event_type", ""),
        )
        try:
            events.append(AcledEvent(
                acled_id=int(r["data_id"]),
                event_date=datetime.strptime(r["event_date"], "%Y-%m-%d").date(),
                event_type=internal_type,
                actor1=r.get("actor1", "Unknown"),
                actor2=r.get("actor2", ""),
                fatalities=int(r.get("fatalities", 0)),
                location=r.get("location", ""),
                state_name=r.get("admin1", ""),
                lga_name=r.get("admin2", ""),
                lat=float(r.get("latitude", 0)),
                lng=float(r.get("longitude", 0)),
                notes=r.get("notes", "")[:500],
                source=r.get("source", "ACLED"),
                source_scale=r.get("source_scale", ""),
            ))
        except (ValueError, KeyError) as e:
            log.warning(f"Skipping malformed ACLED record: {e}")

    return events


def _classify_acled_type(event_type: str, sub_event_type: str) -> str:
    """Map ACLED event/sub_event to our internal security type."""
    if sub_event_type in ACLED_SUBTYPE_MAP:
        return ACLED_SUBTYPE_MAP[sub_event_type]
    return ACLED_TYPE_MAP.get(event_type, "OTHER")


def _compute_severity(event: AcledEvent) -> str:
    """
    Severity classification for security events.
    RED    → fatalities > 5, or TERRORISM / INSURGENCY
    ORANGE → fatalities 1-5, or BANDITRY / KIDNAPPING_HOTSPOT
    YELLOW → COMMUNAL_CONFLICT / CIVIL_UNREST, 0 fatalities
    GREEN  → non-violent PROTEST
    """
    if event.event_type in ("TERRORISM", "INSURGENCY") or event.fatalities > 5:
        return "RED"
    if event.event_type in ("BANDITRY", "KIDNAPPING_HOTSPOT") or event.fatalities >= 1:
        return "ORANGE"
    if event.event_type in ("COMMUNAL_CONFLICT", "CIVIL_UNREST", "ARMED_CLASH"):
        return "YELLOW"
    return "GREEN"


def _build_sms_texts(event: AcledEvent, severity: str) -> dict[str, str]:
    """Generate 160-char GSM 7-bit SMS per language."""
    location = f"{event.location}, {event.state_name}"
    fatality_str = f", {event.fatalities} fatalities" if event.fatalities else ""

    return {
        "sms_en": f"HazardWatch SECURITY {severity}: {event.event_type.replace('_', ' ')} reported in {location}{fatality_str}. Stay indoors. Avoid area. Call 112."[:160],
        "sms_ha": f"HazardWatch TSARO {severity}: An ruwaito rikici a {location}{fatality_str}. Zauna a gida. Kira 112."[:160],
        "sms_yo": f"HazardWatch AABO {severity}: Ija ti royin ni {location}{fatality_str}. Wa ile. Pe 112."[:160],
        "sms_ig": f"HazardWatch NCHE {severity}: Agụọ esemokwu na {location}{fatality_str}. Nọrọ n'ụlọ. Kpọọ 112."[:160],
        "sms_pg": f"HazardWatch SECURITY {severity}: Wahala don happen for {location}{fatality_str}. Stay inside. Call 112."[:160],
    }


async def process_events(events: list[AcledEvent], db_pool, redis) -> int:
    """
    Persist events to security_incidents, publish RED/ORANGE to Redis
    for the alert classifier to pick up and dispatch.
    Returns count of new events stored.
    """
    stored = 0
    for event in events:
        severity = _compute_severity(event)

        # Skip GREEN — no alert needed
        if severity == "GREEN":
            continue

        # Upsert into security_incidents (dedup on acled_event_id)
        try:
            async with db_pool.acquire() as conn:
                # Resolve lga_id from DB by name
                lga_row = await conn.fetchrow(
                    "SELECT id, state_id FROM lgas WHERE name_en ILIKE $1 LIMIT 1",
                    event.lga_name,
                )
                lga_id = lga_row["id"] if lga_row else None
                state_id = lga_row["state_id"] if lga_row else None

                existing = await conn.fetchval(
                    "SELECT id FROM security_incidents WHERE acled_event_id = $1",
                    event.acled_id,
                )
                if existing:
                    continue  # already stored

                await conn.execute("""
                    INSERT INTO security_incidents
                        (acled_event_id, event_type, event_date, actor1, actor2,
                         fatalities, source, source_scale, notes,
                         state_id, lga_id, geom, location_name, severity, verified, public_visible)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
                            ST_SetSRID(ST_MakePoint($12,$13),4326),
                            $14,$15,TRUE,TRUE)
                """,
                    event.acled_id, event.event_type, event.event_date,
                    event.actor1, event.actor2, event.fatalities,
                    event.source, event.source_scale, event.notes,
                    state_id, lga_id, event.lng, event.lat,
                    event.location, severity,
                )
                stored += 1

        except Exception as e:
            log.error(f"DB insert failed for ACLED event {event.acled_id}: {e}")
            continue

        # Publish RED/ORANGE events to Redis → alert classifier picks up
        if severity in ("RED", "ORANGE"):
            sms = _build_sms_texts(event, severity)
            payload = {
                "event":        event.event_type,
                "lga_id":       lga_id,
                "source":       "ACLED",
                "severity_hint": severity,
                "fatalities":   event.fatalities,
                "location":     f"{event.location}, {event.state_name}",
                "actor1":       event.actor1,
                "notes":        event.notes,
                "lat":          event.lat,
                "lng":          event.lng,
                **sms,
            }
            await redis.publish("security_events", json.dumps(payload, default=str))
            log.info(f"Published {severity} security event: {event.event_type} in {event.location}")

    log.info(f"ACLED: stored {stored} new security incidents")
    return stored


async def run(db_pool=None, redis=None):
    """Entry point called by the scheduler."""
    import redis.asyncio as aioredis

    if redis is None:
        redis = aioredis.from_url(REDIS_URL)

    events = await fetch_recent_events(days_back=7)
    if not events:
        return

    if db_pool:
        await process_events(events, db_pool, redis)
    else:
        # Dry-run: just log what would happen
        for e in events:
            sev = _compute_severity(e)
            log.info(f"[DRY RUN] {sev} {e.event_type}: {e.location}, {e.state_name} "
                     f"({e.fatalities} fatalities) — {e.notes[:80]}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
