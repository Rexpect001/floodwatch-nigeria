"""
Tier 2 — GloFAS (Global Flood Awareness System) Fetcher
Copernicus Emergency Management Service

Provides:
  - Ensemble flood forecasting (51-member ensemble)
  - Current discharge vs 2022/2024 flood baselines
  - Return period thresholds (2yr, 5yr, 20yr)
  - Niger/Benue confluence monitoring (Kogi — highest risk)
  - Up to 30-day lead time (7-day used operationally here)

API: Copernicus Climate Data Store (CDS)
Auth: CDS API key (~/.cdsapirc or env vars)

Run: python -m execution.ingestion.glofas_fetcher
"""
import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

# CDS API
CDS_URL      = "https://cds.climate.copernicus.eu/api/v2"
CDS_KEY      = os.getenv("GLOFAS_API_KEY", "")      # format: "UID:API_KEY"

# GloFAS operational API (newer endpoint — preferred)
GLOFAS_API_URL = os.getenv("GLOFAS_API_URL", "https://cds.climate.copernicus.eu/api/v2")

# Nigerian river monitoring points (GloFAS station IDs)
# Niger/Benue confluence at Lokoja is highest priority
MONITORING_POINTS = [
    {"id": "G0263", "name": "Niger at Lokoja",      "lga_id": None,  "lat": 7.80,  "lng": 6.74},
    {"id": "G0264", "name": "Benue at Makurdi",     "lga_id": None,  "lat": 7.73,  "lng": 8.52},
    {"id": "G0265", "name": "Niger at Onitsha",     "lga_id": None,  "lat": 6.15,  "lng": 6.78},
    {"id": "G0266", "name": "Sokoto at Tambuwal",   "lga_id": None,  "lat": 12.40, "lng": 4.63},
    {"id": "G0267", "name": "Kaduna River",         "lga_id": None,  "lat": 10.52, "lng": 7.44},
    {"id": "G0268", "name": "Anambra at Otuocha",   "lga_id": None,  "lat": 6.33,  "lng": 6.78},
]

# 2024 flood baseline discharges (m³/s) for severity escalation
# Reference: NEMA 2024 — 5M affected, 1000+ deaths
BASELINE_2024 = {
    "G0263": 16200.0,   # Niger Lokoja: 2024 peak
    "G0264": 8500.0,    # Benue Makurdi: 2024 peak
    "G0265": 9800.0,    # Niger Onitsha: 2024 peak
}

# 2022 baseline (second reference year)
BASELINE_2022 = {
    "G0263": 14800.0,
    "G0264": 7900.0,
    "G0265": 9100.0,
}


async def fetch_ensemble_forecast(point_id: str, lead_days: int = 7) -> Optional[dict]:
    """
    Fetch GloFAS ensemble discharge forecast for a monitoring point.
    Returns median + 25th/75th percentile discharge m³/s per day.
    """
    headers = _cds_headers()
    if not headers:
        log.warning("GloFAS: CDS API key not configured — skipping")
        return None

    # GloFAS v4 API request
    payload = {
        "variable": "river_discharge_in_the_last_24_hours",
        "format": "json",
        "system_version": "operational",
        "product_type": "ensemble_perturbed_forecasts",
        "leadtime_hour": [str(h) for h in range(24, lead_days * 24 + 1, 24)],
        "area": _point_bbox(point_id),
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GLOFAS_API_URL}/resources/cems-glofas-forecast",
                json=payload,
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        log.error(f"GloFAS forecast failed for {point_id}: {e}")
        return None


async def fetch_return_period_thresholds(point_id: str) -> Optional[dict]:
    """
    Fetch return period thresholds (2yr, 5yr, 20yr discharge m³/s).
    Used to classify alert severity beyond just comparing to 2024 baseline.
    2yr  threshold → YELLOW
    5yr  threshold → ORANGE
    20yr threshold → RED
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GLOFAS_API_URL}/thresholds/{point_id}",
                headers=_cds_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        log.warning(f"GloFAS thresholds not available for {point_id}: {e}")
        return None


def classify_severity_from_discharge(
    discharge_m3s: float,
    point_id: str,
    thresholds: Optional[dict] = None,
) -> str:
    """
    Map discharge to severity using return period thresholds where available,
    falling back to 2024 baseline comparison.
    """
    if thresholds:
        rp20 = thresholds.get("rp20", float("inf"))
        rp5  = thresholds.get("rp5",  float("inf"))
        rp2  = thresholds.get("rp2",  float("inf"))
        if discharge_m3s >= rp20:  return "RED"
        if discharge_m3s >= rp5:   return "ORANGE"
        if discharge_m3s >= rp2:   return "YELLOW"
        return "GREEN"

    # Fallback: 2024 baseline comparison
    baseline = BASELINE_2024.get(point_id)
    if baseline:
        ratio = discharge_m3s / baseline
        if ratio >= 1.0:   return "RED"      # equals or exceeds 2024 disaster
        if ratio >= 0.75:  return "ORANGE"
        if ratio >= 0.50:  return "YELLOW"
    return "GREEN"


async def run_once():
    """
    Full GloFAS fetch cycle.
    Fetches all monitoring points, persists forecasts, publishes flood events.
    """
    import asyncpg
    import redis.asyncio as aioredis
    import json

    db    = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"), min_size=1, max_size=3)
    redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

    try:
        for point in MONITORING_POINTS:
            pid = point["id"]
            log.info(f"GloFAS: fetching {point['name']} ({pid})")

            forecast_data = await fetch_ensemble_forecast(pid)
            if not forecast_data:
                continue

            thresholds = await fetch_return_period_thresholds(pid)

            # Parse ensemble — extract median discharge per lead day
            daily_forecasts = _parse_ensemble(forecast_data, pid)

            for day_offset, (median_q, p25, p75) in enumerate(daily_forecasts):
                forecast_date = date.today() + timedelta(days=day_offset + 1)
                severity = classify_severity_from_discharge(median_q, pid, thresholds)
                baseline_2024 = BASELINE_2024.get(pid)
                prob_pct = _discharge_to_probability(median_q, p25, p75, pid)

                # Persist to flood_forecasts
                async with db.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO flood_forecasts
                            (source, forecast_for, issued_at, probability_pct, severity,
                             discharge_m3s, baseline_2024_m3s, raw_payload)
                        VALUES ('GLOFAS', $1, NOW(), $2, $3, $4, $5, $6::jsonb)
                        ON CONFLICT DO NOTHING
                        """,
                        forecast_date, prob_pct, severity,
                        median_q, baseline_2024,
                        json.dumps({"point_id": pid, "p25": p25, "p75": p75}),
                    )

                # Publish high-risk events to alert classifier
                if severity in ("RED", "ORANGE") and day_offset == 0:
                    payload = {
                        "event": "FLOOD_RIVERINE",
                        "source": "GLOFAS",
                        "severity_hint": severity,
                        "discharge_m3s": median_q,
                        "baseline_2024_m3s": baseline_2024,
                        "probability_pct": prob_pct,
                        "glofas_point_id": pid,
                        "river": point["name"],
                        "note": f"GloFAS ensemble median {median_q:.0f} m³/s. "
                                f"2024 baseline: {baseline_2024} m³/s",
                    }
                    await redis.publish("flood_events", json.dumps(payload))
                    log.warning(f"GloFAS: {severity} event at {point['name']}: {median_q:.0f} m³/s")

            await asyncio.sleep(0.5)   # rate control between points

        log.info("GloFAS cycle complete")
    finally:
        await db.close()
        await redis.aclose()


def _parse_ensemble(raw: dict, point_id: str) -> list[tuple[float, float, float]]:
    """
    Parse GloFAS ensemble JSON → list of (median, p25, p75) per day.
    Returns empty list if data format unexpected (graceful degradation).
    """
    try:
        members = raw.get("members", [])
        if not members:
            return []
        import statistics
        days = len(members[0].get("discharge", []))
        result = []
        for d in range(days):
            vals = sorted([m["discharge"][d] for m in members if len(m.get("discharge", [])) > d])
            n = len(vals)
            if n == 0:
                continue
            median = statistics.median(vals)
            p25 = vals[n // 4]
            p75 = vals[3 * n // 4]
            result.append((float(median), float(p25), float(p75)))
        return result
    except Exception as e:
        log.warning(f"GloFAS parse error for {point_id}: {e}")
        return []


def _discharge_to_probability(median: float, p25: float, p75: float, point_id: str) -> float:
    """Convert ensemble spread to approximate flood probability %."""
    baseline = BASELINE_2024.get(point_id, median * 1.5)
    if baseline == 0:
        return 0.0
    base_prob = min(100.0, (median / baseline) * 100)
    # Narrow ensemble spread = higher confidence
    spread_factor = 1.0 - min(0.3, (p75 - p25) / max(median, 1) * 0.5)
    return round(base_prob * spread_factor, 1)


def _point_bbox(point_id: str) -> list[float]:
    """Return [N, W, S, E] bounding box for a monitoring point."""
    pt = next((p for p in MONITORING_POINTS if p["id"] == point_id), None)
    if not pt:
        return [14.0, 2.6, 4.0, 15.0]   # all Nigeria
    lat, lng = pt["lat"], pt["lng"]
    return [lat + 0.5, lng - 0.5, lat - 0.5, lng + 0.5]


def _cds_headers() -> dict:
    if not CDS_KEY:
        return {}
    return {"Authorization": f"Basic {CDS_KEY}"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_once())
