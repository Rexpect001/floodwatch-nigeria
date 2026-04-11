"""
Tier 2 — OpenWeatherMap One Call API 3.0
Global coverage with NiMet alert aggregation.

Rate limit: 1,000 calls/day free tier.
Strategy:
  - Cache responses 10-30 minutes (client-side + server-side Redis)
  - Batch LGAs by proximity (one OWM call covers ~50km radius)
  - Priority order: HIGH-risk LGAs first, then remainder
  - Track daily quota; stop non-critical calls at 900/day (10% safety buffer)

Run: python -m execution.ingestion.owm_fetcher
"""
import asyncio
import logging
import os
from datetime import datetime, date
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

OWM_BASE_URL    = "https://api.openweathermap.org/data/3.0/onecall"
OWM_API_KEY     = os.getenv("OWM_API_KEY", "")
DAILY_QUOTA     = 1000
SAFETY_BUFFER   = 100   # stop at 900 calls
CACHE_TTL_MIN   = 15    # minutes for normal; 30 for overnight
HIGH_RISK_LGAS  = 148   # poll these first

# Approximate LGA centroids for batching — loaded from DB in production
# Format: {lga_id: (lat, lng)}


async def fetch_one_call(client: httpx.AsyncClient, lat: float, lng: float) -> dict:
    """
    Fetch OWM One Call 3.0 for a location.
    Returns: current, minutely, hourly, daily, alerts.
    """
    resp = await client.get(
        OWM_BASE_URL,
        params={
            "lat": lat,
            "lon": lng,
            "appid": OWM_API_KEY,
            "units": "metric",
            "exclude": "minutely",   # reduce payload size
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


async def check_quota(redis) -> bool:
    """Returns True if we have quota remaining (with safety buffer)."""
    today = date.today().isoformat()
    key = f"owm:quota:{today}"
    count = await redis.get(key)
    used = int(count) if count else 0
    if used >= (DAILY_QUOTA - SAFETY_BUFFER):
        log.warning(f"OWM quota nearly exhausted: {used}/{DAILY_QUOTA} calls today")
        return False
    return True


async def increment_quota(redis):
    today = date.today().isoformat()
    key = f"owm:quota:{today}"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 86400)   # expires midnight
    await pipe.execute()


def extract_heatwave_risk(data: dict) -> bool:
    """Flag heatwave if today's max > 40°C (verified 2024 Sokoto record: 44.8°C)."""
    daily = data.get("daily", [{}])
    if daily:
        temp_max = daily[0].get("temp", {}).get("max", 0)
        return temp_max > 40.0
    return False


def extract_severe_weather(data: dict) -> list[dict]:
    """Extract alerts from OWM response (NiMet alert aggregation)."""
    return data.get("alerts", [])


async def run_batch(lga_coords: list[tuple[int, float, float]], redis):
    """
    Process a batch of LGA coordinates against OWM.
    lga_coords: [(lga_id, lat, lng), ...]
    Respects daily quota; uses cache to avoid duplicate calls.
    """
    async with httpx.AsyncClient() as client:
        for lga_id, lat, lng in lga_coords:
            if not await check_quota(redis):
                log.warning("OWM daily quota reached — skipping remaining LGAs")
                break

            cache_key = f"owm:data:{lat:.2f}:{lng:.2f}"
            cached = await redis.get(cache_key)
            if cached:
                continue   # use cached data downstream

            try:
                data = await fetch_one_call(client, lat, lng)
                await increment_quota(redis)

                ttl = CACHE_TTL_MIN * 60
                import json
                await redis.setex(cache_key, ttl, json.dumps(data))

                # Check heatwave
                if extract_heatwave_risk(data):
                    await _publish_heatwave_risk(lga_id, data, redis)

                # Check NiMet-aggregated severe weather alerts
                alerts = extract_severe_weather(data)
                for alert in alerts:
                    await _publish_weather_alert(lga_id, alert, redis)

                await asyncio.sleep(0.1)   # gentle rate control

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    log.error("OWM 429 rate limit hit — stopping batch")
                    break
                log.error(f"OWM error for LGA {lga_id}: {e}")


async def _publish_heatwave_risk(lga_id: int, data: dict, redis):
    """Publish heatwave risk event to Redis for alert orchestration."""
    import json
    daily = data.get("daily", [{}])[0]
    payload = {
        "event": "HEATWAVE_RISK",
        "lga_id": lga_id,
        "temp_max_c": daily.get("temp", {}).get("max"),
        "source": "OWM",
        "threshold": 40.0,
        "note": "Reference: 2024 Sokoto verified record 44.8°C",
    }
    await redis.publish("weather_events", json.dumps(payload))
    log.warning(f"Heatwave risk published for LGA {lga_id}: {payload['temp_max_c']}°C")


async def _publish_weather_alert(lga_id: int, alert: dict, redis):
    import json
    payload = {
        "event": "WEATHER_ALERT",
        "lga_id": lga_id,
        "alert": alert,
        "source": "OWM",
        "data_source_label": "Data: OpenWeatherMap (Global)",
    }
    await redis.publish("weather_events", json.dumps(payload))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import redis.asyncio as aioredis
    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

    # Test: fetch for Lagos Island centroid
    sample_coords = [(260, 6.455027, 3.384082)]   # Lagos Island LGA
    asyncio.run(run_batch(sample_coords, r))
