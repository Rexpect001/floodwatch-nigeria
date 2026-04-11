"""
Stations endpoints — hydrometric gauges, weather stations, dam registry.

GET /api/v1/stations/lgas                    — all 774 LGAs grouped by state
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

# ---------------------------------------------------------------------------
# Static fallback — used when the DB hasn't been seeded yet.
# Contains all 37 states + the 105 high/moderate-risk LGAs from seed.sql.
# Once the DB is seeded these are replaced with live rows.
# ---------------------------------------------------------------------------
_STATIC_STATES = [
    {"state_id":1,  "state_name":"Abia",        "state_code":"AB","lgas":[
        {"id":10001,"name":"Osisioma",    "flood_risk_class":"HIGH"},
        {"id":10002,"name":"Ugwunagbo",   "flood_risk_class":"HIGH"},
        {"id":10003,"name":"Umuahia North","flood_risk_class":"LOW"},
    ]},
    {"state_id":2,  "state_name":"Adamawa",      "state_code":"AD","lgas":[
        {"id":10004,"name":"Demsa",  "flood_risk_class":"HIGH"},
        {"id":10005,"name":"Fufore", "flood_risk_class":"HIGH"},
    ]},
    {"state_id":3,  "state_name":"Akwa Ibom",    "state_code":"AK","lgas":[
        {"id":10006,"name":"Eket","flood_risk_class":"HIGH"},
        {"id":10007,"name":"Uyo", "flood_risk_class":"MODERATE"},
    ]},
    {"state_id":4,  "state_name":"Anambra",      "state_code":"AN","lgas":[
        {"id":10008,"name":"Anambra East",  "flood_risk_class":"HIGH"},
        {"id":10009,"name":"Anambra West",  "flood_risk_class":"HIGH"},
        {"id":10010,"name":"Awka South",    "flood_risk_class":"MODERATE"},
        {"id":10011,"name":"Ogbaru",        "flood_risk_class":"HIGH"},
        {"id":10012,"name":"Onitsha North", "flood_risk_class":"HIGH"},
        {"id":10013,"name":"Onitsha South", "flood_risk_class":"HIGH"},
    ]},
    {"state_id":5,  "state_name":"Bauchi",       "state_code":"BA","lgas":[
        {"id":10014,"name":"Bauchi","flood_risk_class":"LOW"},
    ]},
    {"state_id":6,  "state_name":"Bayelsa",      "state_code":"BY","lgas":[
        {"id":10015,"name":"Brass",              "flood_risk_class":"HIGH"},
        {"id":10016,"name":"Kolokuma-Opokuma",   "flood_risk_class":"HIGH"},
        {"id":10017,"name":"Ogbia",              "flood_risk_class":"HIGH"},
        {"id":10018,"name":"Southern Ijaw",      "flood_risk_class":"HIGH"},
        {"id":10019,"name":"Yenagoa",            "flood_risk_class":"HIGH"},
    ]},
    {"state_id":7,  "state_name":"Benue",        "state_code":"BE","lgas":[
        {"id":10020,"name":"Agatu",       "flood_risk_class":"HIGH"},
        {"id":10021,"name":"Guma",        "flood_risk_class":"HIGH"},
        {"id":10022,"name":"Gwer East",   "flood_risk_class":"HIGH"},
        {"id":10023,"name":"Katsina-Ala", "flood_risk_class":"HIGH"},
        {"id":10024,"name":"Kwande",      "flood_risk_class":"HIGH"},
        {"id":10025,"name":"Logo",        "flood_risk_class":"HIGH"},
        {"id":10026,"name":"Makurdi",     "flood_risk_class":"HIGH"},
    ]},
    {"state_id":8,  "state_name":"Borno",        "state_code":"BO","lgas":[
        {"id":10027,"name":"Jere",     "flood_risk_class":"HIGH"},
        {"id":10028,"name":"Konduga",  "flood_risk_class":"HIGH"},
        {"id":10029,"name":"Maiduguri","flood_risk_class":"HIGH"},
        {"id":10030,"name":"Mobbar",   "flood_risk_class":"HIGH"},
        {"id":10031,"name":"Nganzai",  "flood_risk_class":"HIGH"},
    ]},
    {"state_id":9,  "state_name":"Cross River",  "state_code":"CR","lgas":[
        {"id":10032,"name":"Akpabuyo",          "flood_risk_class":"HIGH"},
        {"id":10033,"name":"Bakassi",           "flood_risk_class":"HIGH"},
        {"id":10034,"name":"Calabar Municipality","flood_risk_class":"MODERATE"},
        {"id":10035,"name":"Calabar South",     "flood_risk_class":"HIGH"},
    ]},
    {"state_id":10, "state_name":"Delta",        "state_code":"DE","lgas":[
        {"id":10036,"name":"Burutu",        "flood_risk_class":"HIGH"},
        {"id":10037,"name":"Ndokwa East",   "flood_risk_class":"HIGH"},
        {"id":10038,"name":"Ndokwa West",   "flood_risk_class":"HIGH"},
        {"id":10039,"name":"Oshimili North","flood_risk_class":"HIGH"},
        {"id":10040,"name":"Oshimili South","flood_risk_class":"HIGH"},
        {"id":10041,"name":"Ukwuani",       "flood_risk_class":"HIGH"},
        {"id":10042,"name":"Warri North",   "flood_risk_class":"HIGH"},
        {"id":10043,"name":"Warri South",   "flood_risk_class":"HIGH"},
    ]},
    {"state_id":11, "state_name":"Ebonyi",       "state_code":"EB","lgas":[
        {"id":10044,"name":"Abakaliki","flood_risk_class":"MODERATE"},
    ]},
    {"state_id":12, "state_name":"Edo",          "state_code":"ED","lgas":[
        {"id":10045,"name":"Etsako West", "flood_risk_class":"HIGH"},
        {"id":10046,"name":"Orhionmwon",  "flood_risk_class":"HIGH"},
    ]},
    {"state_id":13, "state_name":"Ekiti",        "state_code":"EK","lgas":[
        {"id":10047,"name":"Ado-Ekiti","flood_risk_class":"LOW"},
    ]},
    {"state_id":14, "state_name":"Enugu",        "state_code":"EN","lgas":[
        {"id":10048,"name":"Enugu North","flood_risk_class":"LOW"},
    ]},
    {"state_id":15, "state_name":"Gombe",        "state_code":"GO","lgas":[
        {"id":10049,"name":"Gombe","flood_risk_class":"LOW"},
    ]},
    {"state_id":16, "state_name":"Imo",          "state_code":"IM","lgas":[
        {"id":10050,"name":"Ohaji-Egbema",   "flood_risk_class":"HIGH"},
        {"id":10051,"name":"Oguta",          "flood_risk_class":"HIGH"},
        {"id":10052,"name":"Owerri Municipal","flood_risk_class":"LOW"},
    ]},
    {"state_id":17, "state_name":"Jigawa",       "state_code":"JI","lgas":[
        {"id":10053,"name":"Dutse",      "flood_risk_class":"LOW"},
        {"id":10054,"name":"Guri",       "flood_risk_class":"HIGH"},
        {"id":10055,"name":"Hadejia",    "flood_risk_class":"HIGH"},
        {"id":10056,"name":"Kafin Hausa","flood_risk_class":"HIGH"},
    ]},
    {"state_id":18, "state_name":"Kaduna",       "state_code":"KD","lgas":[
        {"id":10057,"name":"Kaduna North","flood_risk_class":"LOW"},
        {"id":10058,"name":"Zaria",       "flood_risk_class":"LOW"},
    ]},
    {"state_id":19, "state_name":"Kano",         "state_code":"KN","lgas":[
        {"id":10059,"name":"Kano Municipal","flood_risk_class":"LOW"},
    ]},
    {"state_id":20, "state_name":"Katsina",      "state_code":"KT","lgas":[
        {"id":10060,"name":"Faskari","flood_risk_class":"MODERATE"},
    ]},
    {"state_id":21, "state_name":"Kebbi",        "state_code":"KE","lgas":[
        {"id":10061,"name":"Argungu",     "flood_risk_class":"HIGH"},
        {"id":10062,"name":"Bagudo",      "flood_risk_class":"HIGH"},
        {"id":10063,"name":"Birnin Kebbi","flood_risk_class":"HIGH"},
        {"id":10064,"name":"Ngaski",      "flood_risk_class":"HIGH"},
        {"id":10065,"name":"Yauri",       "flood_risk_class":"HIGH"},
    ]},
    {"state_id":22, "state_name":"Kogi",         "state_code":"KO","lgas":[
        {"id":10066,"name":"Ajaokuta",        "flood_risk_class":"HIGH"},
        {"id":10067,"name":"Bassa",           "flood_risk_class":"MODERATE"},
        {"id":10068,"name":"Ibaji",           "flood_risk_class":"HIGH"},
        {"id":10069,"name":"Idah",            "flood_risk_class":"HIGH"},
        {"id":10070,"name":"Igalamela-Odolu", "flood_risk_class":"HIGH"},
        {"id":10071,"name":"Lokoja",          "flood_risk_class":"HIGH"},
    ]},
    {"state_id":23, "state_name":"Kwara",        "state_code":"KW","lgas":[
        {"id":10072,"name":"Edu",   "flood_risk_class":"HIGH"},
        {"id":10073,"name":"Kaiama","flood_risk_class":"HIGH"},
    ]},
    {"state_id":24, "state_name":"Lagos",        "state_code":"LA","lgas":[
        {"id":10074,"name":"Epe",          "flood_risk_class":"HIGH"},
        {"id":10075,"name":"Ikorodu",      "flood_risk_class":"HIGH"},
        {"id":10076,"name":"Ikeja",        "flood_risk_class":"MODERATE"},
        {"id":10077,"name":"Lagos Island", "flood_risk_class":"HIGH"},
        {"id":10078,"name":"Oshodi-Isolo", "flood_risk_class":"MODERATE"},
    ]},
    {"state_id":25, "state_name":"Nasarawa",     "state_code":"NA","lgas":[
        {"id":10079,"name":"Awe",  "flood_risk_class":"HIGH"},
        {"id":10080,"name":"Lafia","flood_risk_class":"LOW"},
        {"id":10081,"name":"Obi",  "flood_risk_class":"HIGH"},
    ]},
    {"state_id":26, "state_name":"Niger",        "state_code":"NI","lgas":[
        {"id":10082,"name":"Agaie", "flood_risk_class":"HIGH"},
        {"id":10083,"name":"Borgu", "flood_risk_class":"HIGH"},
        {"id":10084,"name":"Edati", "flood_risk_class":"MODERATE"},
        {"id":10085,"name":"Lavun", "flood_risk_class":"HIGH"},
        {"id":10086,"name":"Minna", "flood_risk_class":"LOW"},
    ]},
    {"state_id":27, "state_name":"Ogun",         "state_code":"OG","lgas":[
        {"id":10087,"name":"Abeokuta South","flood_risk_class":"MODERATE"},
        {"id":10088,"name":"Sagamu",        "flood_risk_class":"MODERATE"},
    ]},
    {"state_id":28, "state_name":"Ondo",         "state_code":"ON","lgas":[
        {"id":10089,"name":"Akure South","flood_risk_class":"LOW"},
        {"id":10090,"name":"Ese-Odo",    "flood_risk_class":"HIGH"},
        {"id":10091,"name":"Ilaje",      "flood_risk_class":"HIGH"},
    ]},
    {"state_id":29, "state_name":"Osun",         "state_code":"OS","lgas":[
        {"id":10092,"name":"Osogbo","flood_risk_class":"LOW"},
    ]},
    {"state_id":30, "state_name":"Oyo",          "state_code":"OY","lgas":[
        {"id":10093,"name":"Ibadan South-West","flood_risk_class":"LOW"},
        {"id":10094,"name":"Ogbomosho North", "flood_risk_class":"LOW"},
    ]},
    {"state_id":31, "state_name":"Plateau",      "state_code":"PL","lgas":[
        {"id":10095,"name":"Jos North","flood_risk_class":"LOW"},
        {"id":10096,"name":"Shendam", "flood_risk_class":"HIGH"},
        {"id":10097,"name":"Wase",    "flood_risk_class":"HIGH"},
    ]},
    {"state_id":32, "state_name":"Rivers",       "state_code":"RI","lgas":[
        {"id":10098,"name":"Asari-Toru",  "flood_risk_class":"HIGH"},
        {"id":10099,"name":"Degema",      "flood_risk_class":"HIGH"},
        {"id":10100,"name":"Port Harcourt","flood_risk_class":"HIGH"},
    ]},
    {"state_id":33, "state_name":"Sokoto",       "state_code":"SO","lgas":[
        {"id":10101,"name":"Bodinga",    "flood_risk_class":"HIGH"},
        {"id":10102,"name":"Dange Shuni","flood_risk_class":"HIGH"},
        {"id":10103,"name":"Sokoto North","flood_risk_class":"MODERATE"},
    ]},
    {"state_id":34, "state_name":"Taraba",       "state_code":"TA","lgas":[
        {"id":10104,"name":"Donga", "flood_risk_class":"HIGH"},
        {"id":10105,"name":"Wukari","flood_risk_class":"HIGH"},
    ]},
    {"state_id":35, "state_name":"Yobe",         "state_code":"YO","lgas":[
        {"id":10106,"name":"Bade",  "flood_risk_class":"HIGH"},
        {"id":10107,"name":"Geidam","flood_risk_class":"HIGH"},
    ]},
    {"state_id":36, "state_name":"Zamfara",      "state_code":"ZA","lgas":[
        {"id":10108,"name":"Gusau","flood_risk_class":"LOW"},
    ]},
    {"state_id":37, "state_name":"FCT Abuja",    "state_code":"FC","lgas":[
        {"id":10109,"name":"Abuja Municipal","flood_risk_class":"LOW"},
        {"id":10110,"name":"Gwagwalada",     "flood_risk_class":"LOW"},
    ]},
]

_STATIC_TOTAL = sum(len(s["lgas"]) for s in _STATIC_STATES)


@router.get("/lgas", summary="All LGAs grouped by state")
async def list_lgas(db=Depends(get_db)):
    """Returns all LGAs grouped by state for the forecast LGA selector.
    Falls back to static seed data when the DB has not been seeded yet."""
    try:
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT l.id, l.name_en, l.flood_risk_class,
                       s.id state_id, s.name_en state_name, s.code state_code
                FROM lgas l
                JOIN states s ON s.id = l.state_id
                ORDER BY s.name_en, l.name_en
                """
            )
    except Exception:
        rows = []

    if rows:
        # Live DB data
        states: dict = {}
        for r in rows:
            sc = r["state_code"]
            if sc not in states:
                states[sc] = {
                    "state_id": r["state_id"],
                    "state_name": r["state_name"],
                    "state_code": sc,
                    "lgas": [],
                }
            states[sc]["lgas"].append({
                "id": r["id"],
                "name": r["name_en"],
                "flood_risk_class": r["flood_risk_class"],
            })
        return {
            "total_lgas": len(rows),
            "total_states": len(states),
            "states": list(states.values()),
            "source": "db",
        }

    # DB empty — return static fallback so the UI always works
    return {
        "total_lgas": _STATIC_TOTAL,
        "total_states": len(_STATIC_STATES),
        "states": _STATIC_STATES,
        "source": "static",
    }


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
