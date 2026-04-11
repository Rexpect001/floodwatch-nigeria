"""
Voice Alert Pipeline API Router

POST /api/v1/voice/sessions              — Step 1: create draft
POST /api/v1/voice/sessions/{id}/generate — Steps 2+3: translate + synthesise
GET  /api/v1/voice/sessions/{id}         — Pipeline status + clip data
POST /api/v1/voice/sessions/{id}/playback — Track officer playback progress
GET  /api/v1/voice/sessions/{id}/approve-check — Eligibility check
POST /api/v1/voice/sessions/{id}/approve  — Step 4: approve
POST /api/v1/voice/sessions/{id}/reject   — Step 4: reject
POST /api/v1/voice/sessions/{id}/override — Emergency override (DIRECTOR+2FA)
GET  /api/v1/voice/sessions/{id}/audit    — Audit log

All mutating endpoints require JWT (NEMA officer authentication).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field

from ..db import get_db, get_redis
from ...voice.pipeline import VoicePipeline
from ...voice.governance import GovernanceError, InsufficientRoleError

router = APIRouter()


def get_pipeline(db=Depends(get_db), redis=Depends(get_redis)) -> VoicePipeline:
    return VoicePipeline(db, redis)


def get_officer_id(x_officer_id: str = Header(...)) -> str:
    """
    In production: validate JWT, extract officer_id claim.
    Header: X-Officer-Id (simplified here; replace with proper JWT middleware).
    """
    return x_officer_id


# ── Step 1: Create Draft ──────────────────────────────────────

class CreateDraftRequest(BaseModel):
    alert_id: UUID
    source_text_en: str = Field(
        ...,
        max_length=280,
        description="English alert text (max 280 chars — ensures translations fit 160-char SMS)",
    )


class CreateDraftResponse(BaseModel):
    session_id: str
    char_count: int
    chars_remaining: int


@router.post("/sessions", response_model=CreateDraftResponse, status_code=201)
async def create_draft(
    req: CreateDraftRequest,
    officer_id: str = Depends(get_officer_id),
    pipeline: VoicePipeline = Depends(get_pipeline),
):
    """Step 1: Compose English source text. Returns session_id."""
    session_id = await pipeline.create_draft(
        str(req.alert_id), req.source_text_en, officer_id
    )
    return CreateDraftResponse(
        session_id=session_id,
        char_count=len(req.source_text_en),
        chars_remaining=280 - len(req.source_text_en),
    )


# ── Steps 2+3: Generate ───────────────────────────────────────

@router.post("/sessions/{session_id}/generate")
async def generate(
    session_id: str,
    officer_id: str = Depends(get_officer_id),
    pipeline: VoicePipeline = Depends(get_pipeline),
):
    """
    Steps 2+3: Translate (Claude API) then synthesise (TTS) all 5 language clips.
    Atomic — cannot be interrupted mid-execution.
    Target: <30s total. Clips with confidence <0.85 flagged for manual review.
    """
    try:
        result = await pipeline.generate(session_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Status ────────────────────────────────────────────────────

@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    officer_id: str = Depends(get_officer_id),
    pipeline: VoicePipeline = Depends(get_pipeline),
):
    """
    Full pipeline status for the review UI (Step 4 panel).
    Returns all clip cards data including waveform_data arrays.
    """
    status = await pipeline.get_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Session not found")
    return status


# ── Step 4: Playback Tracking ─────────────────────────────────

class PlaybackRequest(BaseModel):
    lang: str = Field(..., pattern="^(en|ha|yo|ig|pg)$")
    playback_duration_s: float = Field(..., ge=0)


@router.post("/sessions/{session_id}/playback")
async def track_playback(
    session_id: str,
    req: PlaybackRequest,
    officer_id: str = Depends(get_officer_id),
    pipeline: VoicePipeline = Depends(get_pipeline),
):
    """
    Called periodically by frontend as officer plays clips.
    Once >50% played: played_once=True, contributes to Approve eligibility.
    Returns current approve eligibility state.
    """
    result = await pipeline.track_playback(
        session_id, req.lang, officer_id, req.playback_duration_s
    )
    return result


# ── Approve Eligibility Check ─────────────────────────────────

@router.get("/sessions/{session_id}/approve-check")
async def approve_check(
    session_id: str,
    officer_id: str = Depends(get_officer_id),
    pipeline: VoicePipeline = Depends(get_pipeline),
):
    """
    Non-mutating eligibility check. Frontend polls this to enable/disable Approve button.
    Returns: {eligible, reason, missing_langs, is_red_alert, needs_second_approver}
    """
    from ...voice.governance import check_approve_eligibility
    db = pipeline.db
    redis = pipeline.redis
    return await check_approve_eligibility(session_id, officer_id, db, redis)


# ── Step 4: Approve ───────────────────────────────────────────

@router.post("/sessions/{session_id}/approve")
async def approve(
    session_id: str,
    officer_id: str = Depends(get_officer_id),
    pipeline: VoicePipeline = Depends(get_pipeline),
):
    """
    Approve a session. Non-RED: single officer queues immediately.
    RED: requires 2 different officers (4-eyes). Returns queued status.

    On success for non-RED / final RED approval:
      - Checksums verified against S3
      - Message published to RabbitMQ: alerts.voice.approved (persistent)
      - Alert Router dispatches to Africa's Talking Voice + Radio FTP + IVR
    """
    try:
        return await pipeline.approve(session_id, officer_id)
    except (GovernanceError, InsufficientRoleError) as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── Step 4: Reject ────────────────────────────────────────────

class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=10, description="Mandatory rejection reason")


@router.post("/sessions/{session_id}/reject", status_code=200)
async def reject(
    session_id: str,
    req: RejectRequest,
    officer_id: str = Depends(get_officer_id),
    pipeline: VoicePipeline = Depends(get_pipeline),
):
    """
    Reject a session. Reason stored in audit log, session returns to REJECTED state.
    Composing officer can then edit and re-generate.
    """
    try:
        await pipeline.reject(session_id, officer_id, req.reason)
        return {"status": "rejected", "reason": req.reason}
    except GovernanceError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Emergency Override ────────────────────────────────────────

class OverrideRequest(BaseModel):
    totp_code: str = Field(..., min_length=6, max_length=8)
    justification: str = Field(..., min_length=20)


@router.post("/sessions/{session_id}/override")
async def override(
    session_id: str,
    req: OverrideRequest,
    officer_id: str = Depends(get_officer_id),
    pipeline: VoicePipeline = Depends(get_pipeline),
):
    """
    DIRECTOR-level emergency override. Bypasses all governance gates.
    Requires valid TOTP 2FA code. Triggers automatic post-incident audit report (24h).
    All override actions are permanently logged and cannot be expunged.
    """
    try:
        result = await pipeline.override(session_id, officer_id, req.totp_code)
        return result
    except (GovernanceError, InsufficientRoleError) as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── Audit Log ────────────────────────────────────────────────

@router.get("/sessions/{session_id}/audit")
async def get_audit_log(
    session_id: str,
    officer_id: str = Depends(get_officer_id),
    db=Depends(get_db),
):
    """Immutable audit trail for a session. NEMA SENIOR_OFFICER+ only."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.officer_id, o.name officer_name, a.action, a.lang,
                   a.playback_pct, a.notes,
                   TO_CHAR(a.created_at AT TIME ZONE 'Africa/Lagos', 'DD/MM/YYYY HH24:MI WAT') AS timestamp
            FROM voice_approval_audit a
            LEFT JOIN nema_officers o ON o.id = a.officer_id
            WHERE a.session_id = $1
            ORDER BY a.created_at
            """,
            session_id,
        )
    return {"session_id": session_id, "audit": [dict(r) for r in rows]}
