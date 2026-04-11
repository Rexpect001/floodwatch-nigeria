"""
Admin endpoints (JWT-protected, NEMA SENIOR_OFFICER+).

GET  /api/v1/admin/ingestion/status      — data freshness per source
GET  /api/v1/admin/alerts/pending-red    — RED alerts awaiting 2nd source
GET  /api/v1/admin/sms/delivery-stats    — SMS delivery rates
GET  /api/v1/admin/error-reports         — queued error reports for review
PATCH /api/v1/admin/error-reports/{id}   — mark reviewed/actioned
GET  /api/v1/admin/quota                 — API quota usage (esp. OWM)
GET  /api/v1/admin/voice/pending-override-audits  — override audit reports due
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..db import get_db, get_redis

router = APIRouter()


@router.get("/ingestion/status")
async def ingestion_status(db=Depends(get_db)):
    """
    Data freshness per source. Shows staleness hours, consecutive failures,
    current fallback tier, and degraded flag.
    """
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source, last_success, last_attempt,
                   consecutive_failures, current_tier, is_degraded,
                   EXTRACT(EPOCH FROM (NOW() - last_success))/3600 AS staleness_hours
            FROM data_staleness
            ORDER BY is_degraded DESC, staleness_hours DESC NULLS LAST
            """
        )
        recent = await conn.fetch(
            """
            SELECT source, COUNT(*) total_calls,
                   SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) success,
                   AVG(latency_ms) avg_latency_ms,
                   MAX(ingested_at) last_call
            FROM api_ingestion_log
            WHERE ingested_at >= NOW() - INTERVAL '1 hour'
            GROUP BY source
            ORDER BY source
            """
        )
    return {
        "sources": [dict(r) for r in rows],
        "last_hour_stats": [dict(r) for r in recent],
    }


@router.get("/alerts/pending-red")
async def pending_red_alerts(db=Depends(get_db), redis=Depends(get_redis)):
    """
    RED alerts awaiting 2nd source confirmation before being published.
    These are stored in Redis under red:pending:* keys.
    """
    import json
    keys = await redis.keys("red:pending:*")
    pending = []
    for key in keys:
        raw = await redis.get(key)
        if raw:
            pending.append(json.loads(raw))
    return {"count": len(pending), "alerts": pending}


@router.get("/sms/delivery-stats")
async def sms_delivery_stats(
    hours: int = Query(default=24, ge=1, le=168),
    db=Depends(get_db),
):
    """SMS delivery rates by severity, channel, and language."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                d.channel, d.language,
                a.severity,
                COUNT(*)                                           AS total,
                SUM(CASE WHEN d.status = 'DELIVERED' THEN 1 ELSE 0 END) AS delivered,
                SUM(CASE WHEN d.status = 'FAILED'    THEN 1 ELSE 0 END) AS failed,
                ROUND(
                    SUM(CASE WHEN d.status = 'DELIVERED' THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*), 0) * 100, 1
                )                                                  AS delivery_rate_pct,
                AVG(EXTRACT(EPOCH FROM (d.delivered_at - d.sent_at)))  AS avg_delivery_s
            FROM alert_deliveries d
            JOIN alerts a ON a.id = d.alert_id
            WHERE d.created_at >= NOW() - ($1 || ' hours')::INTERVAL
            GROUP BY d.channel, d.language, a.severity
            ORDER BY a.severity, d.channel
            """,
            str(hours),
        )
    return {"period_hours": hours, "stats": [dict(r) for r in rows]}


@router.get("/error-reports")
async def list_error_reports(
    status: str = Query(default="PENDING"),
    db=Depends(get_db),
):
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.id, e.alert_id, e.description, e.status,
                   e.created_at, l.name_en lga_name
            FROM error_reports e
            LEFT JOIN lgas l ON l.id = e.lga_id
            WHERE e.status = $1
            ORDER BY e.created_at DESC
            LIMIT 100
            """,
            status,
        )
    return {"total": len(rows), "reports": [dict(r) for r in rows]}


class ErrorReportUpdate(BaseModel):
    status: str
    reviewer_notes: Optional[str] = None


@router.patch("/error-reports/{report_id}")
async def update_error_report(
    report_id: UUID,
    update: ErrorReportUpdate,
    db=Depends(get_db),
):
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE error_reports
            SET status = $2, reviewer_notes = $3, reviewed_at = NOW()
            WHERE id = $1
            """,
            report_id, update.status, update.reviewer_notes,
        )
    return {"id": str(report_id), "status": update.status}


@router.get("/quota")
async def api_quota(db=Depends(get_db), redis=Depends(get_redis)):
    """Current API quota usage. Critical: OWM 1,000 calls/day free tier."""
    from datetime import date
    today = date.today().isoformat()

    owm_used_raw = await redis.get(f"owm:quota:{today}")
    owm_used = int(owm_used_raw) if owm_used_raw else 0

    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT source, calls_made, quota_limit FROM api_quota_log WHERE date = $1",
            date.today(),
        )

    return {
        "date": today,
        "owm": {
            "used": owm_used,
            "limit": 1000,
            "safety_buffer": 100,
            "remaining": max(0, 900 - owm_used),
            "exhausted": owm_used >= 900,
        },
        "other_sources": [dict(r) for r in rows],
    }


@router.get("/voice/pending-override-audits")
async def pending_override_audits(db=Depends(get_db)):
    """
    Voice sessions with emergency override where audit report is due.
    Directors must file these within 24h of override.
    """
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.override_officer_id, s.override_at,
                   s.override_audit_report_due,
                   a.severity, a.alert_type,
                   EXTRACT(EPOCH FROM (s.override_audit_report_due - NOW()))/3600
                       AS hours_until_due
            FROM voice_alert_sessions s
            JOIN alerts a ON a.id = s.alert_id
            WHERE s.is_emergency_override = TRUE
              AND s.override_audit_report_due > NOW() - INTERVAL '7 days'
            ORDER BY s.override_audit_report_due
            """
        )
    return {
        "count": len(rows),
        "overdue": [r for r in rows if r["hours_until_due"] < 0],
        "due_soon": [r for r in rows if 0 <= r["hours_until_due"] <= 4],
        "all": [dict(r) for r in rows],
    }
