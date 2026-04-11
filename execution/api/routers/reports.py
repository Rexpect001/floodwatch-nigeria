"""
Community Reports (CBEWS) endpoints.

POST /api/v1/reports          — submit geo-tagged flood report + photo
GET  /api/v1/reports          — list public verified reports (GeoJSON)
GET  /api/v1/reports/{id}     — single report detail
"""
import hashlib
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db
from ...validation.cbews_verifier import verify_report

router = APIRouter()


class ReportSubmission(BaseModel):
    lat: float = Field(..., ge=4.0, le=14.0,  description="Nigerian latitude")
    lng: float = Field(..., ge=2.6, le=15.0,  description="Nigerian longitude")
    report_type: str = Field(
        ...,
        pattern="^(FLOOD_ACTIVE|FLOOD_RECEDING|ROAD_BLOCKED|SHELTER_FULL|DAMAGE|ALL_CLEAR)$"
    )
    description: str = Field(..., min_length=10, max_length=500)
    photo_url: Optional[str] = None
    lang: str = Field(default="en", pattern="^(en|ha|yo|ig|pg)$")


@router.post("", status_code=202)
async def submit_report(req: ReportSubmission, db=Depends(get_db)):
    """
    Submit a community flood report.
    Photo verification (AI flood detection + EXIF geotag) runs async.
    public_visible=False until verified.
    """
    # Hash reporter IP/phone for privacy (no raw PII stored)
    reporter_hash = hashlib.sha256(f"{req.lat:.3f}{req.lng:.3f}".encode()).hexdigest()[:16]

    async with db.acquire() as conn:
        # Reverse-geocode to LGA
        lga_row = await conn.fetchrow(
            "SELECT id FROM lgas WHERE ST_Contains(geom, ST_SetSRID(ST_Point($1,$2),4326)) LIMIT 1",
            req.lng, req.lat,
        )
        lga_id = lga_row["id"] if lga_row else None

        report_id = await conn.fetchval(
            """
            INSERT INTO community_reports
                (reporter_hash, lga_id, geom, report_type, description, photo_url, public_visible)
            VALUES ($1, $2, ST_SetSRID(ST_Point($3,$4),4326), $5, $6, $7, FALSE)
            RETURNING id
            """,
            reporter_hash, lga_id, req.lng, req.lat,
            req.report_type, req.description, req.photo_url,
        )

    # Kick off async verification if photo provided
    if req.photo_url:
        import asyncio
        asyncio.create_task(_run_verification(str(report_id), req.photo_url, req.lat, req.lng, db))

    return {
        "report_id": str(report_id),
        "status": "received",
        "message": "Report received. Photo verification in progress.",
        "public_visible": False,
    }


async def _run_verification(report_id: str, photo_url: str, lat: float, lng: float, db):
    """Background verification task."""
    from uuid import UUID
    result = await verify_report(UUID(report_id), photo_url, lat, lng)
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE community_reports SET
                photo_verified    = $2,
                photo_confidence  = $3,
                geotag_verified   = $4,
                is_false_report   = $5,
                public_visible    = $6
            WHERE id = $1
            """,
            UUID(report_id),
            result["photo_verified"],
            result["photo_confidence"],
            result["geotag_verified"],
            result["is_false_report"],
            result["public_visible"],
        )


@router.get("")
async def list_reports(
    lga_id: Optional[int] = Query(default=None),
    hours: int = Query(default=24, ge=1, le=168),
    verified_only: bool = Query(default=True),
    db=Depends(get_db),
):
    """
    Public verified community reports as GeoJSON FeatureCollection.
    Defaults: last 24h, verified only.
    """
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT r.id, r.report_type, r.description,
                   r.photo_verified, r.photo_confidence, r.is_false_report,
                   ST_Y(r.geom) lat, ST_X(r.geom) lng,
                   l.name_en lga_name, s.name_en state_name,
                   TO_CHAR(r.created_at AT TIME ZONE 'Africa/Lagos', 'DD/MM/YYYY HH24:MI WAT') ts
            FROM community_reports r
            LEFT JOIN lgas l   ON l.id  = r.lga_id
            LEFT JOIN states s ON s.id  = l.state_id
            WHERE r.public_visible = TRUE
              AND ($1::bool = FALSE OR r.photo_verified = TRUE)
              AND ($2::int  IS NULL  OR r.lga_id = $2)
              AND r.created_at >= NOW() - ($3 || ' hours')::INTERVAL
            ORDER BY r.created_at DESC
            LIMIT 200
            """,
            verified_only, lga_id, str(hours),
        )

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
            "properties": {
                "id": str(r["id"]),
                "report_type": r["report_type"],
                "description": r["description"],
                "photo_confidence": float(r["photo_confidence"]) if r["photo_confidence"] else None,
                "lga": r["lga_name"],
                "state": r["state_name"],
                "timestamp": r["ts"],
            },
        }
        for r in rows
    ]
    return {"type": "FeatureCollection", "features": features}


@router.get("/{report_id}")
async def get_report(report_id: UUID, db=Depends(get_db)):
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT r.*, ST_Y(r.geom) lat, ST_X(r.geom) lng,
                   l.name_en lga_name
            FROM community_reports r
            LEFT JOIN lgas l ON l.id = r.lga_id
            WHERE r.id = $1 AND r.public_visible = TRUE
            """,
            report_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found or not yet verified")
    return dict(row)
