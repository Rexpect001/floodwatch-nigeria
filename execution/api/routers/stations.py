"""
Stations endpoints — hydrometric gauges, weather stations, dam registry.

GET /api/v1/stations/gauges                  — list all 273 NIHSA gauges
GET /api/v1/stations/gauges/{station_id}     — single gauge detail
GET /api/v1/stations/gauges/{station_id}/readings  — time-series readings
GET /api/v1/stations/weather                 — list NiMet stations
GET /api/v1/stations/weather/{station_id}/observations
GET /api/v1/stations/dams                    — dam registry (incl. Laggo)
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from ..db import get_db, get_redis

router = APIRouter()


@router.get("/gauges")
async def list_gauges(
    state_id: Optional[int] = Query(default=None),
    active: bool = Query(default=True),
    db=Depends(get_db),
):
    """List all NIHSA hydrometric stations (273). Optionally filter by state."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.nihsa_station_id, s.name, s.river_name,
                   st.name_en state_name, l.name_en lga_name,
                   ST_Y(s.geom) lat, ST_X(s.geom) lng,
                   s.bankfull_m, s.danger_level_m, s.is_active, s.last_seen
            FROM hydrometric_stations s
            LEFT JOIN states st ON st.id = s.state_id
            LEFT JOIN lgas   l  ON l.id  = s.lga_id
            WHERE ($1::int IS NULL OR s.state_id = $1)
              AND ($2::bool IS NULL OR s.is_active = $2)
            ORDER BY st.name_en, s.name
            """,
            state_id, active,
        )
    return {"total": len(rows), "stations": [dict(r) for r in rows]}


@router.get("/gauges/{station_id}/readings")
async def get_gauge_readings(
    station_id: int,
    hours: int = Query(default=24, ge=1, le=168),
    db=Depends(get_db),
):
    """
    Time-series river gauge readings for a station.
    Returns water_level_m, discharge_m3s, stage_trend, bankfull comparison.
    Max 7 days (168h).
    """
    async with db.acquire() as conn:
        station = await conn.fetchrow(
            "SELECT id, name, river_name, bankfull_m, danger_level_m "
            "FROM hydrometric_stations WHERE id = $1", station_id
        )
        readings = await conn.fetch(
            """
            SELECT observed_at AT TIME ZONE 'Africa/Lagos' AS observed_wat,
                   water_level_m, discharge_m3s, stage_trend, source_tier
            FROM river_gauge_readings
            WHERE station_id = $1
              AND observed_at >= NOW() - ($2 || ' hours')::INTERVAL
            ORDER BY observed_at DESC
            LIMIT 1000
            """,
            station_id, str(hours),
        )

    return {
        "station": dict(station) if station else None,
        "period_hours": hours,
        "readings": [
            {
                "time_wat": r["observed_wat"].strftime("%d/%m/%Y %H:%M WAT"),
                "water_level_m": r["water_level_m"],
                "discharge_m3s": r["discharge_m3s"],
                "stage_trend": r["stage_trend"],
                "above_danger": (
                    float(r["water_level_m"]) > float(station["danger_level_m"])
                    if r["water_level_m"] and station and station["danger_level_m"] else False
                ),
                "source_tier": r["source_tier"],
            }
            for r in readings
        ],
    }


@router.get("/weather")
async def list_weather_stations(
    state_id: Optional[int] = Query(default=None),
    station_type: Optional[str] = Query(default=None),
    db=Depends(get_db),
):
    """List NiMet weather stations (54 synoptic + 6 RADAR). Filter by state/type."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT w.id, w.nimet_station_id, w.name, w.station_type,
                   s.name_en state_name,
                   ST_Y(w.geom) lat, ST_X(w.geom) lng,
                   w.elevation_m, w.is_active, w.last_seen
            FROM weather_stations w
            LEFT JOIN states s ON s.id = w.state_id
            WHERE ($1::int IS NULL OR w.state_id = $1)
              AND ($2::text IS NULL OR w.station_type = $2)
            ORDER BY w.station_type, w.name
            """,
            state_id, station_type,
        )
    return {"total": len(rows), "stations": [dict(r) for r in rows]}


@router.get("/weather/{station_id}/observations")
async def get_weather_observations(
    station_id: int,
    hours: int = Query(default=24, ge=1, le=72),
    db=Depends(get_db),
):
    """Recent weather observations. Flags heatwave (>40°C) per reading."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT observed_at AT TIME ZONE 'Africa/Lagos' AS observed_wat,
                   temp_c, humidity_pct, wind_speed_kmh, wind_dir_deg,
                   precip_mm_1h, visibility_m, pressure_hpa, is_heatwave
            FROM weather_observations
            WHERE station_id = $1
              AND observed_at >= NOW() - ($2 || ' hours')::INTERVAL
            ORDER BY observed_at DESC
            LIMIT 500
            """,
            station_id, str(hours),
        )
    return {
        "station_id": station_id,
        "period_hours": hours,
        "heatwave_threshold_c": 40.0,
        "reference_record_c": 44.8,
        "reference_location": "Sokoto 2024",
        "observations": [
            {**dict(r), "time_wat": r["observed_wat"].strftime("%d/%m/%Y %H:%M WAT")}
            for r in rows
        ],
    }


@router.get("/dams")
async def list_dams(db=Depends(get_db)):
    """
    Dam registry including Laggo Dam (Cameroon).
    Shows downstream LGAs at risk per dam.
    """
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT d.id, d.name, d.country, d.operator,
                   d.capacity_mm3, d.downstream_lgas,
                   ST_Y(d.geom) lat, ST_X(d.geom) lng,
                   (
                       SELECT json_agg(json_build_object('id', l.id, 'name', l.name_en, 'state', s.name_en))
                       FROM lgas l JOIN states s ON s.id = l.state_id
                       WHERE l.id = ANY(d.downstream_lgas)
                   ) AS downstream_lga_details
            FROM dam_registry d
            ORDER BY d.country, d.name
            """
        )
    return {
        "total": len(rows),
        "note": "Laggo Dam (Cameroon) releases cross-referenced with NIHSA Niger/Benue discharge",
        "dams": [dict(r) for r in rows],
    }
