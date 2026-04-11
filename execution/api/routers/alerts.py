"""
Alert endpoints.

GET  /api/v1/alerts?severity=RED&lang=en&lga_id=123
GET  /api/v1/alerts/{alert_id}?lang=yo
POST /api/v1/alerts/subscribe   — register phone for SMS alerts
GET  /api/v1/alerts/shelters/{lga_id}  — evacuation shelter coordinates
POST /api/v1/alerts/report-error       — in-app error report → NiMet/NEMA
"""
from typing import Optional, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, Body
from pydantic import BaseModel, Field

from ..db import get_db, get_redis
from ..utils.i18n import get_alert_text

router = APIRouter()

Lang = Literal["en", "ha", "yo", "ig", "pg"]


class AlertSummary(BaseModel):
    id: UUID
    alert_type: str
    severity: str
    severity_color: str
    title: str
    body: str
    sms_text: Optional[str]
    affected_lga_count: int
    nema_alert_id: Optional[str]
    nihsa_alert_id: Optional[str]
    confirmed_by: list[str]
    shelter_coords: Optional[list]
    evacuation_routes: Optional[dict]
    valid_from: str
    valid_until: Optional[str]
    last_updated: str     # "DD/MM/YYYY HH:MM WAT"
    data_source_label: str


SEVERITY_COLORS = {
    "RED": "#D32F2F",
    "ORANGE": "#F57C00",
    "YELLOW": "#F9A825",
    "GREEN": "#388E3C",
}


@router.get("", response_model=list[AlertSummary])
async def list_active_alerts(
    lang: Lang = Query(default="en"),
    severity: Optional[str] = Query(default=None),
    lga_id: Optional[int] = Query(default=None),
    state_id: Optional[int] = Query(default=None),
    db=Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Returns active alerts. RED alerts always appear first.
    For RED severity, confirmed_by will contain 2+ sources (e.g. NIHSA + GOOGLE_FLOOD_HUB).
    """
    cache_key = f"alerts:active:{lang}:{severity}:{lga_id}:{state_id}"
    cached = await redis.get(cache_key)
    if cached:
        import json
        return [AlertSummary(**a) for a in json.loads(cached)]

    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id, a.alert_type, a.severity, a.lga_ids,
                   a.title_en, a.title_ha, a.title_yo, a.title_ig, a.title_pg,
                   a.body_en, a.body_ha, a.body_yo, a.body_ig, a.body_pg,
                   a.sms_en, a.sms_ha, a.sms_yo, a.sms_ig, a.sms_pg,
                   a.nema_alert_id, a.nihsa_alert_id, a.confirmed_by,
                   a.shelter_coords, a.evacuation_routes,
                   a.valid_from, a.valid_until, a.updated_at,
                   a.source_primary,
                   array_length(a.lga_ids, 1) AS affected_lga_count
            FROM v_active_alerts a
            WHERE ($1::text IS NULL OR a.severity = $1)
              AND ($2::int  IS NULL OR $2 = ANY(a.lga_ids))
              AND ($3::int  IS NULL OR $3 = ANY(a.state_ids))
            LIMIT 100
            """,
            severity, lga_id, state_id,
        )

    results = [
        AlertSummary(
            id=r["id"],
            alert_type=r["alert_type"],
            severity=r["severity"],
            severity_color=SEVERITY_COLORS.get(r["severity"], "#9E9E9E"),
            title=get_alert_text(r, "title", lang),
            body=get_alert_text(r, "body", lang),
            sms_text=get_alert_text(r, "sms", lang),
            affected_lga_count=r["affected_lga_count"] or 0,
            nema_alert_id=r["nema_alert_id"],
            nihsa_alert_id=r["nihsa_alert_id"],
            confirmed_by=list(r["confirmed_by"] or []),
            shelter_coords=r["shelter_coords"],
            evacuation_routes=r["evacuation_routes"],
            valid_from=r["valid_from"].strftime("%d/%m/%Y %H:%M WAT"),
            valid_until=r["valid_until"].strftime("%d/%m/%Y %H:%M WAT") if r["valid_until"] else None,
            last_updated=r["updated_at"].strftime("%d/%m/%Y %H:%M WAT"),
            data_source_label=(
                "Data: NEMA/NIHSA" if r["nema_alert_id"] or r["nihsa_alert_id"]
                else f"Data: {r['source_primary']}"
            ),
        )
        for r in rows
    ]

    import json
    # RED alerts: cache 60s only (near-real-time); others 5 min
    ttl = 60 if any(a.severity == "RED" for a in results) else 300
    await redis.setex(cache_key, ttl, json.dumps([a.model_dump() for a in results], default=str))
    return results


class SubscribeRequest(BaseModel):
    msisdn: str = Field(..., pattern=r"^\+234[0-9]{10}$", description="Nigerian number: +234XXXXXXXXXX")
    lang: Lang = "en"
    lga_ids: list[int] = Field(..., max_length=10)
    severity_threshold: str = Field(default="ORANGE", pattern="^(RED|ORANGE|YELLOW|GREEN)$")


@router.post("/subscribe", status_code=201)
async def subscribe_sms(req: SubscribeRequest, db=Depends(get_db)):
    """Register a phone number for SMS alerts at or above the given severity threshold."""
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sms_subscriptions (msisdn, lang, lga_ids, severity_threshold)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (msisdn) DO UPDATE SET
                lang = EXCLUDED.lang,
                lga_ids = EXCLUDED.lga_ids,
                severity_threshold = EXCLUDED.severity_threshold,
                updated_at = NOW()
            """,
            req.msisdn, req.lang, req.lga_ids, req.severity_threshold,
        )
    return {"status": "subscribed", "msisdn": req.msisdn}


@router.get("/shelters/{lga_id}")
async def get_shelters(lga_id: int, db=Depends(get_db)):
    """
    Evacuation shelter GPS coordinates for an LGA.
    Populated from active RED/ORANGE alerts and NEMA EOC data.
    """
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT jsonb_array_elements(a.shelter_coords) AS shelter
            FROM alerts a
            WHERE $1 = ANY(a.lga_ids)
              AND a.status = 'ACTIVE'
              AND a.severity IN ('RED', 'ORANGE')
              AND a.shelter_coords IS NOT NULL
            """,
            lga_id,
        )
    return {"lga_id": lga_id, "shelters": [r["shelter"] for r in rows]}


class ErrorReport(BaseModel):
    alert_id: Optional[UUID]
    lga_id: Optional[int]
    description: str
    reporter_contact: Optional[str]


@router.post("/report-error", status_code=202)
async def report_error(report: ErrorReport = Body(...), db=Depends(get_db)):
    """
    In-app error report feeds directly to NiMet/NEMA verification teams.
    Queued for review; does NOT immediately alter alert status.
    """
    async with db.acquire() as conn:
        await conn.execute(
            "INSERT INTO error_reports (alert_id, lga_id, description, reporter_contact) "
            "VALUES ($1, $2, $3, $4)",
            report.alert_id, report.lga_id, report.description, report.reporter_contact,
        )
    return {"status": "received", "message": "Report forwarded to NiMet/NEMA verification team"}
