"""
Tier 1 — NIHSA Data Ingestion
Polls NIHSA API every 15 minutes for:
  - River gauge readings (273 hydrometric stations)
  - Annual Flood Outlook (AFO) classifications (302+ communities)
  - 5-day quantitative precipitation forecasts
  - Laggo Dam (Cameroon) release notifications

Run: python -m execution.ingestion.nihsa_fetcher
Or via APScheduler in the ingestion service.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

NIHSA_BASE_URL   = os.getenv("NIHSA_BASE_URL", "https://api.nihsa.gov.ng/v1")
NIHSA_API_KEY    = os.getenv("NIHSA_API_KEY", "")
LAGGO_DAM_ID     = "CM-LAGGO-001"   # Cameroon Laggo Dam — cross-reference required
POLL_INTERVAL_S  = 900              # 15 minutes
MAX_RETRIES      = 5
BACKOFF_BASE_S   = 30


async def fetch_gauge_readings(client: httpx.AsyncClient, station_ids: list[str]) -> list[dict]:
    """
    Fetch real-time river gauge readings for all 273 NIHSA stations.
    Returns list of reading dicts ready for DB insertion.
    """
    url = f"{NIHSA_BASE_URL}/hydro/gauges"
    resp = await _get_with_retry(client, url, params={"stations": ",".join(station_ids)})
    readings = resp.get("data", [])
    log.info(f"NIHSA: fetched {len(readings)} gauge readings")
    return [
        {
            "nihsa_station_id": r["station_id"],
            "observed_at": _parse_ts(r["timestamp"]),
            "water_level_m": r.get("water_level"),
            "discharge_m3s": r.get("discharge"),
            "stage_trend": r.get("trend", "STEADY").upper(),
            "source_tier": 1,
            "raw_payload": r,
        }
        for r in readings
    ]


async def fetch_afo_classifications(client: httpx.AsyncClient) -> list[dict]:
    """
    Fetch Annual Flood Outlook (AFO) classifications for 302+ communities.
    Classes: HIGHLY_PROBABLE / PROBABLE / LOW_RISK
    Seasonal (August–October 2025 window).
    """
    url = f"{NIHSA_BASE_URL}/afo/communities"
    resp = await _get_with_retry(client, url)
    communities = resp.get("data", [])
    log.info(f"NIHSA: fetched AFO for {len(communities)} communities")
    return communities


async def fetch_5day_qpf(client: httpx.AsyncClient) -> list[dict]:
    """
    Fetch 5-day Quantitative Precipitation Forecasts from NIHSA.
    Returns per-LGA daily rainfall totals + flood probability.
    """
    url = f"{NIHSA_BASE_URL}/forecast/qpf/5day"
    resp = await _get_with_retry(client, url)
    return resp.get("data", [])


async def check_laggo_dam_release(client: httpx.AsyncClient) -> Optional[dict]:
    """
    Check Laggo Dam (Cameroon) release notifications.
    Critical: upstream dam releases significantly impact Niger/Benue confluence flooding.
    When detected, triggers immediate cross-reference with NIHSA discharge data.
    """
    url = f"{NIHSA_BASE_URL}/dams/{LAGGO_DAM_ID}/releases"
    try:
        resp = await _get_with_retry(client, url)
        releases = resp.get("data", [])
        if releases:
            latest = releases[0]
            log.warning(
                f"NIHSA: Laggo Dam release detected! "
                f"Rate={latest.get('release_m3s')} m³/s at {latest.get('timestamp')}"
            )
            return latest
    except Exception as e:
        log.error(f"Laggo Dam check failed: {e}")
    return None


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict = None,
    attempt: int = 0,
) -> dict:
    """Exponential backoff retry for NIHSA API calls."""
    try:
        resp = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {NIHSA_API_KEY}"},
            timeout=30,
        )
        resp.raise_for_status()
        _log_ingestion("NIHSA", 1, url, resp.status_code, len(resp.content))
        return resp.json()

    except (httpx.HTTPError, httpx.TimeoutException) as e:
        if attempt >= MAX_RETRIES:
            log.error(f"NIHSA API failed after {MAX_RETRIES} retries: {url} — {e}")
            _log_ingestion("NIHSA", 1, url, None, 0, str(e))
            raise

        wait = BACKOFF_BASE_S * (2 ** attempt)
        log.warning(f"NIHSA retry {attempt + 1}/{MAX_RETRIES} in {wait}s: {e}")
        await asyncio.sleep(wait)
        return await _get_with_retry(client, url, params, attempt + 1)


def _parse_ts(ts_str: str) -> datetime:
    """Parse NIHSA timestamp; assume WAT (UTC+1) if no tz info."""
    from zoneinfo import ZoneInfo
    WAT = ZoneInfo("Africa/Lagos")
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=WAT)
    return dt


def _log_ingestion(source, tier, endpoint, status, size, error=None):
    """Write to api_ingestion_log table (fire-and-forget)."""
    # In production: use asyncpg pool connection
    pass


async def run_once():
    """Single poll cycle — called by scheduler every 15 minutes."""
    async with httpx.AsyncClient() as client:
        # 1. Gauge readings
        station_ids = await _get_all_station_ids()
        readings = await fetch_gauge_readings(client, station_ids)
        await _upsert_gauge_readings(readings)

        # 2. AFO classifications (less frequent — daily is sufficient)
        afo = await fetch_afo_classifications(client)
        await _upsert_afo(afo)

        # 3. 5-day QPF
        qpf = await fetch_5day_qpf(client)
        await _upsert_qpf(qpf)

        # 4. Laggo Dam
        release = await check_laggo_dam_release(client)
        if release:
            await _trigger_dam_alert(release)

    log.info("NIHSA ingestion cycle complete")


async def _get_all_station_ids() -> list[str]:
    """Load station IDs from DB (or fallback to static list)."""
    return []  # populated from DB in production


async def _upsert_gauge_readings(readings: list[dict]):
    pass  # asyncpg bulk insert


async def _upsert_afo(communities: list[dict]):
    pass


async def _upsert_qpf(qpf: list[dict]):
    pass


async def _trigger_dam_alert(release: dict):
    """Publish Laggo Dam release to Redis → alert orchestration."""
    import redis.asyncio as aioredis
    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    import json
    await r.publish("dam_releases", json.dumps(release))
    await r.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_once())
