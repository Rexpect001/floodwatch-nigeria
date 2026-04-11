"""
Tier 1 — NiMet Data Ingestion
Nigerian Meteorological Agency

Fetches every 15 minutes:
  - Synoptic station observations (54 stations)
  - RADAR station data (6 stations)
  - Automatic Weather Station (AWS) readings
  - Heatwave detection (>40°C threshold; ref: 44.8°C Sokoto 2024 record)
  - Seasonal Climate Prediction (SCP) — 74% verified accuracy (2024 baseline)
  - Thunderstorm alerts: wind >50km/h, hail, lightning density
  - Harmattan/dust: Dec-Feb visibility <1000m
  - Precipitation forecasts (merged with NIHSA QPF)

Run: python -m execution.ingestion.nimet_fetcher
"""
import asyncio
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

NIMET_BASE_URL   = os.getenv("NIMET_BASE_URL", "https://api.nimet.gov.ng/v1")
NIMET_API_KEY    = os.getenv("NIMET_API_KEY", "")
POLL_INTERVAL_S  = 900
MAX_RETRIES      = 5
BACKOFF_BASE_S   = 30

WAT = ZoneInfo("Africa/Lagos")

# Thresholds per spec
HEATWAVE_THRESHOLD_C = 40.0    # auto-alert (ref: Sokoto 2024 record 44.8°C)
DUST_VISIBILITY_M    = 1000    # Harmattan dust threshold Dec-Feb
STORM_WIND_KMH       = 50.0    # Thunderstorm wind threshold


async def fetch_station_observations(client: httpx.AsyncClient) -> list[dict]:
    """
    Fetch current observations for all 54 synoptic + 6 RADAR stations.
    Returns normalised list ready for weather_observations table.
    """
    url = f"{NIMET_BASE_URL}/observations/current"
    resp = await _get_with_retry(client, url)
    observations = resp.get("data", [])
    log.info(f"NiMet: fetched {len(observations)} station observations")
    return [_normalise_observation(o) for o in observations]


async def fetch_scp() -> dict:
    """
    Seasonal Climate Prediction (SCP).
    74% verified accuracy (2024 baseline).
    Returns onset dates, rainfall predictions per state.
    Covers Northern delayed onset vs Southern early onset (per 2025 SCP).
    """
    async with httpx.AsyncClient() as client:
        resp = await _get_with_retry(client, f"{NIMET_BASE_URL}/scp/current")
    data = resp.get("data", {})
    log.info("NiMet SCP fetched")
    return data


async def fetch_precipitation_forecast(client: httpx.AsyncClient) -> list[dict]:
    """
    48-hour precipitation forecasts per LGA.
    Merged with NIHSA 5-day QPF at the DB level for comprehensive coverage.
    """
    url = f"{NIMET_BASE_URL}/forecast/precipitation/48h"
    resp = await _get_with_retry(client, url)
    return resp.get("data", [])


def _normalise_observation(raw: dict) -> dict:
    """Normalise NiMet API response to weather_observations schema."""
    temp_c = raw.get("temperature")
    wind_speed = raw.get("wind_speed_kmh") or raw.get("wind_speed", 0)
    visibility = raw.get("visibility_m")
    month = datetime.now(WAT).month

    obs = {
        "nimet_station_id": raw.get("station_id"),
        "observed_at": _parse_ts(raw.get("timestamp", "")),
        "temp_c": temp_c,
        "humidity_pct": raw.get("humidity"),
        "wind_speed_kmh": wind_speed,
        "wind_dir_deg": raw.get("wind_direction"),
        "precip_mm_1h": raw.get("precipitation_1h"),
        "visibility_m": visibility,
        "pressure_hpa": raw.get("pressure"),
        "raw_payload": raw,
        # Derived flags
        "_is_heatwave": temp_c is not None and temp_c > HEATWAVE_THRESHOLD_C,
        "_is_dust_event": (
            visibility is not None
            and visibility < DUST_VISIBILITY_M
            and month in (12, 1, 2)     # Harmattan season
        ),
        "_is_storm": wind_speed > STORM_WIND_KMH,
    }
    return obs


async def _publish_weather_events(observations: list[dict], redis):
    """
    Publish heatwave, dust, and storm events to Redis → alert_classifier.
    """
    import json
    for obs in observations:
        station_id = obs["nimet_station_id"]

        if obs.get("_is_heatwave"):
            payload = {
                "event": "HEATWAVE_RISK",
                "source": "NIMET",
                "nimet_station_id": station_id,
                "temp_max_c": obs["temp_c"],
                "observed_at": obs["observed_at"].isoformat() if obs["observed_at"] else None,
                "note": f"NiMet observed {obs['temp_c']}°C. Threshold: {HEATWAVE_THRESHOLD_C}°C. "
                        f"Reference: Sokoto 2024 record 44.8°C",
            }
            await redis.publish("weather_events", json.dumps(payload, default=str))
            log.warning(f"NiMet heatwave event: station={station_id}, temp={obs['temp_c']}°C")

        if obs.get("_is_dust_event"):
            payload = {
                "event": "DUST_HARMATTAN",
                "source": "NIMET",
                "nimet_station_id": station_id,
                "visibility_m": obs["visibility_m"],
                "season": "Harmattan (Dec-Feb)",
                "severity_hint": "YELLOW",
            }
            await redis.publish("weather_events", json.dumps(payload, default=str))

        if obs.get("_is_storm"):
            payload = {
                "event": "THUNDERSTORM",
                "source": "NIMET",
                "nimet_station_id": station_id,
                "wind_speed_kmh": obs["wind_speed_kmh"],
                "severity_hint": "ORANGE" if obs["wind_speed_kmh"] > 80 else "YELLOW",
            }
            await redis.publish("weather_events", json.dumps(payload, default=str))


async def _upsert_observations(observations: list[dict], db):
    """Bulk-insert observations into weather_observations table."""
    async with db.acquire() as conn:
        # Map station IDs to DB IDs
        station_map = {}
        ids = [o["nimet_station_id"] for o in observations if o["nimet_station_id"]]
        if ids:
            rows = await conn.fetch(
                "SELECT id, nimet_station_id FROM weather_stations WHERE nimet_station_id = ANY($1)",
                ids,
            )
            station_map = {r["nimet_station_id"]: r["id"] for r in rows}

        insert_data = [
            (
                station_map.get(o["nimet_station_id"]),
                o["observed_at"],
                o["temp_c"], o["humidity_pct"],
                o["wind_speed_kmh"], o["wind_dir_deg"],
                o["precip_mm_1h"], o["visibility_m"],
                o["pressure_hpa"],
            )
            for o in observations
            if o["nimet_station_id"] in station_map and o["observed_at"]
        ]

        if insert_data:
            await conn.executemany(
                """
                INSERT INTO weather_observations
                    (station_id, observed_at, temp_c, humidity_pct,
                     wind_speed_kmh, wind_dir_deg, precip_mm_1h, visibility_m, pressure_hpa)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT DO NOTHING
                """,
                insert_data,
            )
            log.info(f"NiMet: inserted {len(insert_data)} observations")


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict = None,
    attempt: int = 0,
) -> dict:
    try:
        resp = await client.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {NIMET_API_KEY}",
                "Accept": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        if attempt >= MAX_RETRIES:
            log.error(f"NiMet API failed after {MAX_RETRIES} retries: {url}")
            raise
        wait = BACKOFF_BASE_S * (2 ** attempt)
        log.warning(f"NiMet retry {attempt + 1}/{MAX_RETRIES} in {wait}s: {e}")
        await asyncio.sleep(wait)
        return await _get_with_retry(client, url, params, attempt + 1)


def _parse_ts(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=WAT)
    except ValueError:
        return None


async def run_once():
    """Single NiMet poll cycle — called by scheduler every 15 minutes."""
    import redis.asyncio as aioredis
    import asyncpg

    db    = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"), min_size=1, max_size=3)
    redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

    try:
        async with httpx.AsyncClient() as client:
            observations = await fetch_station_observations(client)
            precip       = await fetch_precipitation_forecast(client)

        await _upsert_observations(observations, db)
        await _publish_weather_events(observations, redis)
        log.info(f"NiMet cycle complete: {len(observations)} obs, {len(precip)} precip forecasts")
    finally:
        await db.close()
        await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_once())
