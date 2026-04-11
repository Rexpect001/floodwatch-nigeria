"""
Forecast endpoints — 5-day flood & weather forecasts per LGA/community.

GET /api/v1/forecasts/flood/{lga_id}?days=5&lang=en
GET /api/v1/forecasts/flood/community/{community_id}?lang=yo
GET /api/v1/forecasts/weather/{lga_id}?lang=ha
GET /api/v1/forecasts/heatwave?state_code=SK&lang=en
GET /api/v1/forecasts/afo?lang=en          — Annual Flood Outlook (302+ communities)
"""
from datetime import date, timedelta
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db, get_redis
from ..utils.i18n import translate_severity, translate_alert_type

router = APIRouter()

Lang = Literal["en", "ha", "yo", "ig", "pg"]


class FloodForecastPoint(BaseModel):
    date: date
    severity: str
    probability_pct: float
    inundation_pct: Optional[float]
    discharge_m3s: Optional[float]
    baseline_2024_m3s: Optional[float]
    source: str
    # Translated label
    severity_label: str
    last_updated: str   # "DD/MM/YYYY HH:MM WAT"
    data_source_label: str  # "Data: NIHSA/NiMet" vs "Data: OpenWeatherMap (Global)"


class FloodForecastResponse(BaseModel):
    lga_id: int
    lga_name: str
    state_name: str
    flood_risk_class: str
    forecast: list[FloodForecastPoint]
    data_staleness_hours: Optional[float]
    is_cached: bool


@router.get("/flood/{lga_id}", response_model=FloodForecastResponse)
async def get_flood_forecast(
    lga_id: int,
    days: int = Query(default=5, ge=1, le=7),
    lang: Lang = Query(default="en"),
    db=Depends(get_db),
    redis=Depends(get_redis),
):
    """
    5-day flood forecast for an LGA. Merges NIHSA (Tier 1) + Google Flood Hub
    + GloFAS. Source attribution shown: 'Data: NIHSA/NiMet' vs 'Data: OWM (Global)'.
    Probability ≥ 20% triggers inundation display (Flood Hub threshold).
    """
    cache_key = f"forecast:flood:{lga_id}:{days}:{lang}"
    cached = await redis.get(cache_key)
    if cached:
        import json
        return FloodForecastResponse(**json.loads(cached))

    async with db.acquire() as conn:
        lga = await conn.fetchrow(
            "SELECT l.id, l.name_en, s.name_en state_name, l.flood_risk_class "
            "FROM lgas l JOIN states s ON s.id = l.state_id WHERE l.id = $1",
            lga_id,
        )
        if not lga:
            raise HTTPException(status_code=404, detail="LGA not found")

        forecasts_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (forecast_for)
                forecast_for, source, probability_pct, severity,
                inundation_pct, discharge_m3s, baseline_2024_m3s, created_at
            FROM flood_forecasts
            WHERE lga_id = $1
              AND forecast_for BETWEEN CURRENT_DATE AND CURRENT_DATE + ($2 - 1) * INTERVAL '1 day'
            ORDER BY forecast_for, CASE source
                WHEN 'NIHSA' THEN 1
                WHEN 'GOOGLE_FLOOD_HUB' THEN 2
                WHEN 'GLOFAS' THEN 3
                ELSE 4 END
            """,
            lga_id, days,
        )

    forecast_points = [
        FloodForecastPoint(
            date=row["forecast_for"],
            severity=row["severity"] or "NONE",
            probability_pct=float(row["probability_pct"] or 0),
            inundation_pct=float(row["inundation_pct"]) if row["inundation_pct"] else None,
            discharge_m3s=float(row["discharge_m3s"]) if row["discharge_m3s"] else None,
            baseline_2024_m3s=float(row["baseline_2024_m3s"]) if row["baseline_2024_m3s"] else None,
            source=row["source"],
            severity_label=translate_severity(row["severity"] or "NONE", lang),
            last_updated=row["created_at"].strftime("%d/%m/%Y %H:%M WAT"),
            data_source_label=(
                "Data: NIHSA/NiMet" if row["source"] in ("NIHSA",)
                else "Data: OpenWeatherMap (Global)"
                if row["source"] == "OWM"
                else f"Data: {row['source']}"
            ),
        )
        for row in forecasts_rows
    ]

    result = FloodForecastResponse(
        lga_id=lga_id,
        lga_name=lga["name_en"],
        state_name=lga["state_name"],
        flood_risk_class=lga["flood_risk_class"],
        forecast=forecast_points,
        data_staleness_hours=None,
        is_cached=False,
    )

    import json
    await redis.setex(cache_key, 900, result.model_dump_json())  # 15-min cache
    return result


@router.get("/afo", summary="Annual Flood Outlook — 302+ communities")
async def get_afo(
    lang: Lang = Query(default="en"),
    state_code: Optional[str] = Query(default=None),
    db=Depends(get_db),
):
    """
    Returns NIHSA Annual Flood Outlook classifications (HIGHLY_PROBABLE / PROBABLE / LOW_RISK)
    for all 302+ AFO communities. Filterable by state.
    August–October 2025 window; 148 HIGH-risk LGAs highlighted.
    """
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.name_en, c.afo_class,
                   l.name_en lga_name, s.name_en state_name, s.code state_code,
                   ST_Y(c.geom) lat, ST_X(c.geom) lng
            FROM communities c
            JOIN lgas l ON l.id = c.lga_id
            JOIN states s ON s.id = l.state_id
            WHERE c.afo_class IS NOT NULL
              AND ($1::text IS NULL OR s.code = $1)
            ORDER BY
                CASE c.afo_class
                    WHEN 'HIGHLY_PROBABLE' THEN 1
                    WHEN 'PROBABLE' THEN 2
                    ELSE 3 END,
                s.name_en, l.name_en
            """,
            state_code,
        )

    return {
        "total": len(rows),
        "source": "NIHSA Annual Flood Outlook 2025",
        "window": "August–October 2025",
        "data_source_label": "Data: NIHSA",
        "communities": [
            {
                "id": r["id"],
                "name": r["name_en"],
                "afo_class": r["afo_class"],
                "afo_label": translate_severity(r["afo_class"], lang),
                "lga": r["lga_name"],
                "state": r["state_name"],
                "state_code": r["state_code"],
                "lat": r["lat"],
                "lng": r["lng"],
            }
            for r in rows
        ],
    }
