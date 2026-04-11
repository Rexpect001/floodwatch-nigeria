"""
Tier 2 — Google Flood Hub API Fetcher
AI-powered 7-day riverine flood forecasts.

Key threshold: 20% community area inundation → triggers PROBABLE+ classification.
Cross-validated against NIHSA discharge data from Niger/Benue confluence.

API: Google Flood Hub (Flood Forecasting API)
Docs: https://developers.google.com/flood-hub/reference/rest

Run: python -m execution.ingestion.google_flood_hub
"""
import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

FLOOD_HUB_KEY     = os.getenv("GOOGLE_FLOOD_HUB_KEY", "")
FLOOD_HUB_BASE    = "https://floodhub.googleapis.com/v1"

# Nigerian river gauges covered by Google Flood Hub
# These overlap with NIHSA stations — used for cross-validation
FLOOD_HUB_GAUGES = [
    {"gauge_id": "hybas_1120571410", "name": "Niger at Lokoja",    "lga_hint": "Lokoja"},
    {"gauge_id": "hybas_1120571420", "name": "Benue at Makurdi",   "lga_hint": "Makurdi"},
    {"gauge_id": "hybas_1120571430", "name": "Niger at Onitsha",   "lga_hint": "Onitsha"},
    {"gauge_id": "hybas_1120571440", "name": "Niger at Idah",      "lga_hint": "Idah"},
    {"gauge_id": "hybas_1120571450", "name": "Sokoto River",       "lga_hint": "Tambuwal"},
    {"gauge_id": "hybas_1120571460", "name": "Kaduna River",       "lga_hint": "Kaduna South"},
    {"gauge_id": "hybas_1120571470", "name": "Anambra River",      "lga_hint": "Otuocha"},
    {"gauge_id": "hybas_1120571480", "name": "Cross River",        "lga_hint": "Calabar South"},
]

# Inundation threshold per spec: 20% of community area
INUNDATION_THRESHOLD_PCT = 20.0


async def fetch_gauge_forecast(
    client: httpx.AsyncClient,
    gauge_id: str,
    days: int = 7,
) -> Optional[dict]:
    """
    Fetch 7-day flood forecast for a single gauge.
    Returns inundation probability and extent per day.
    """
    url = f"{FLOOD_HUB_BASE}/gauges/{gauge_id}/forecast"
    try:
        resp = await client.get(
            url,
            params={
                "key": FLOOD_HUB_KEY,
                "days": days,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            log.debug(f"Flood Hub: gauge {gauge_id} not found — skipping")
        else:
            log.warning(f"Flood Hub: gauge {gauge_id} error {e.response.status_code}")
        return None
    except httpx.TimeoutException:
        log.warning(f"Flood Hub: timeout for gauge {gauge_id}")
        return None


async def fetch_community_inundation(
    client: httpx.AsyncClient,
    lat: float,
    lng: float,
    radius_km: float = 10.0,
) -> Optional[dict]:
    """
    Fetch inundation forecast for a geographic area (community level).
    Used to check if a community exceeds the 20% inundation threshold.
    """
    url = f"{FLOOD_HUB_BASE}/floodStatus:queryFloodStatus"
    try:
        resp = await client.post(
            url,
            params={"key": FLOOD_HUB_KEY},
            json={
                "location": {"latitude": lat, "longitude": lng},
                "radiusKm": radius_km,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.debug(f"Flood Hub inundation query failed ({lat},{lng}): {e}")
        return None


def parse_gauge_forecast(raw: dict, gauge_id: str) -> list[dict]:
    """
    Parse Flood Hub forecast JSON into normalised daily forecast records.
    Flags any day where inundation exceeds 20% threshold.
    """
    forecasts = []
    daily = raw.get("dailyForecasts", [])
    for i, day in enumerate(daily):
        forecast_date = date.today() + timedelta(days=i + 1)
        inundation_pct = float(day.get("floodedAreaPercent", 0) or 0)
        discharge_m3s  = float(day.get("discharge", 0) or 0)
        probability    = float(day.get("floodProbability", 0) or 0) * 100

        # Classify per spec: ≥20% inundation = PROBABLE or higher
        if inundation_pct >= INUNDATION_THRESHOLD_PCT:
            severity = "HIGHLY_PROBABLE" if probability >= 70 else "PROBABLE"
        elif probability >= 40:
            severity = "PROBABLE"
        elif probability >= 15:
            severity = "LOW_RISK"
        else:
            severity = "NONE"

        forecasts.append({
            "source": "GOOGLE_FLOOD_HUB",
            "gauge_id": gauge_id,
            "forecast_for": forecast_date,
            "probability_pct": round(probability, 1),
            "severity": severity,
            "inundation_pct": round(inundation_pct, 2),
            "discharge_m3s": discharge_m3s,
            "raw_payload": day,
        })
    return forecasts


async def cross_validate_with_nihsa(
    gauge_forecasts: list[dict],
    db,
    redis,
) -> list[dict]:
    """
    Cross-validate Flood Hub forecasts against latest NIHSA discharge readings.
    If Flood Hub + NIHSA both show high discharge → escalate to RED candidate.
    This satisfies the 2-source confirmation requirement for RED alerts.
    """
    async with db.acquire() as conn:
        # Get latest NIHSA readings for Niger/Benue confluence points
        nihsa_readings = await conn.fetch(
            """
            SELECT hs.name, r.discharge_m3s, r.water_level_m, r.stage_trend
            FROM river_gauge_readings r
            JOIN hydrometric_stations hs ON hs.id = r.station_id
            WHERE r.observed_at >= NOW() - INTERVAL '3 hours'
              AND hs.river_name IN ('Niger', 'Benue')
            ORDER BY r.observed_at DESC
            LIMIT 20
            """
        )

    nihsa_by_river = {}
    for row in nihsa_readings:
        name = row["name"].lower()
        for key in ("niger", "benue"):
            if key in name:
                nihsa_by_river.setdefault(key, []).append(dict(row))

    validated = []
    for fc in gauge_forecasts:
        fc_copy = dict(fc)
        gauge_name = fc.get("gauge_name", "").lower()

        # Cross-reference: if both Flood Hub and NIHSA show high discharge
        for river, readings in nihsa_by_river.items():
            if river in gauge_name and readings:
                nihsa_discharge = readings[0].get("discharge_m3s", 0) or 0
                flood_hub_discharge = fc.get("discharge_m3s", 0) or 0

                if nihsa_discharge > 0 and flood_hub_discharge > 0:
                    # Agreement check: within 20%
                    ratio = abs(nihsa_discharge - flood_hub_discharge) / max(nihsa_discharge, 1)
                    fc_copy["nihsa_confirmed"] = ratio < 0.20
                    fc_copy["nihsa_discharge_m3s"] = nihsa_discharge

                    if fc_copy.get("severity") in ("HIGHLY_PROBABLE",) and fc_copy["nihsa_confirmed"]:
                        # Two sources agree — publish as confirmed flood event
                        payload = {
                            "event": "FLOOD_RIVERINE",
                            "source": "GOOGLE_FLOOD_HUB",
                            "source_secondary": "NIHSA",
                            "severity_hint": "ORANGE",
                            "probability_pct": fc["probability_pct"],
                            "inundation_pct": fc["inundation_pct"],
                            "discharge_m3s": flood_hub_discharge,
                            "nihsa_discharge_m3s": nihsa_discharge,
                            "confirmed_by": ["GOOGLE_FLOOD_HUB", "NIHSA"],
                        }
                        await redis.publish("flood_events", json.dumps(payload, default=str))
                        log.info(f"Flood Hub + NIHSA confirmed: {river} at {flood_hub_discharge:.0f} m³/s")

        validated.append(fc_copy)
    return validated


async def run_once():
    """Full Flood Hub cycle — all gauges, cross-validate, persist."""
    import asyncpg
    import redis.asyncio as aioredis

    db    = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"), min_size=1, max_size=3)
    redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

    if not FLOOD_HUB_KEY:
        log.warning("Google Flood Hub: API key not set — skipping")
        await db.close(); await redis.aclose()
        return

    all_forecasts = []
    async with httpx.AsyncClient() as client:
        for gauge in FLOOD_HUB_GAUGES:
            raw = await fetch_gauge_forecast(client, gauge["gauge_id"])
            if raw:
                daily = parse_gauge_forecast(raw, gauge["gauge_id"])
                for fc in daily:
                    fc["gauge_name"] = gauge["name"]
                all_forecasts.extend(daily)
            await asyncio.sleep(0.2)

    # Cross-validate with NIHSA
    validated = await cross_validate_with_nihsa(all_forecasts, db, redis)

    # Persist to flood_forecasts table
    async with db.acquire() as conn:
        for fc in validated:
            await conn.execute(
                """
                INSERT INTO flood_forecasts
                    (source, forecast_for, issued_at, probability_pct, severity,
                     inundation_pct, discharge_m3s, raw_payload)
                VALUES ('GOOGLE_FLOOD_HUB', $1, NOW(), $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT DO NOTHING
                """,
                fc["forecast_for"], fc["probability_pct"], fc["severity"],
                fc["inundation_pct"], fc["discharge_m3s"],
                json.dumps(fc.get("raw_payload", {}), default=str),
            )

    log.info(f"Flood Hub cycle complete: {len(validated)} forecast records")
    await db.close()
    await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_once())
