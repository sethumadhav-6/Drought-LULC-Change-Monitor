"""
Admin endpoints: review the request queue, approve/reject, and
"release" a validated dataset (spatial + Excel) so the requester's
GET /api/requests/{id} starts returning download links.

MVP-level auth: a single admin account (username/password, from
settings.admin_username / settings.admin_password). POST /login
exchanges credentials for a bearer session token; every other admin
route requires `Authorization: Bearer <token>`. Sessions are held
in-process (a Python set) -- fine for a single-instance pilot, but
they reset on restart and won't work if you ever run more than one
backend worker. Swap for real auth (SSO / role-based accounts /
JWT with a shared secret) before this goes beyond a pilot.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..db import crud
from ..db.database import get_db
from ..db.models import RequestStatus

router = APIRouter(prefix="/api/admin", tags=["admin"])

# In-memory session store: {token: username}. Single-process MVP only.
_ACTIVE_SESSIONS: dict[str, str] = {}


class LoginPayload(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginPayload):
    settings = get_settings()
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise HTTPException(401, "Invalid username or password.")
    token = secrets.token_urlsafe(32)
    _ACTIVE_SESSIONS[token] = payload.username
    return {"token": token, "username": payload.username}


@router.post("/logout")
def logout(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    _ACTIVE_SESSIONS.pop(token, None)
    return {"ok": True}


def require_admin(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    if token not in _ACTIVE_SESSIONS:
        raise HTTPException(401, "Not logged in. POST /api/admin/login first, then send Authorization: Bearer <token>.")
    return _ACTIVE_SESSIONS[token]


@router.get("/requests", dependencies=[Depends(require_admin)])
def list_requests(status: str | None = None, db: Session = Depends(get_db)):
    reqs = crud.list_requests(db, status)
    return [
        {
            "id": r.id, "requester_name": r.requester_name, "requester_email": r.requester_email,
            "aoi_name": r.aoi_name, "data_source": r.data_source, "indexes": r.indexes,
            "date_start": r.date_start, "date_end": r.date_end, "status": r.status,
            "created_at": r.created_at, "purpose": r.purpose,
        }
        for r in reqs
    ]


class ReviewPayload(BaseModel):
    admin_notes: str | None = None
    reviewed_by: str | None = None  # defaults to the logged-in admin username if omitted


@router.post("/requests/{request_id}/approve")
def approve(request_id: str, payload: ReviewPayload, db: Session = Depends(get_db), admin_user: str = Depends(require_admin)):
    req = crud.set_status(db, request_id, RequestStatus.approved, payload.admin_notes, payload.reviewed_by or admin_user)
    if not req:
        raise HTTPException(404, "Request not found.")
    return {"id": req.id, "status": req.status}


@router.post("/requests/{request_id}/reject")
def reject(request_id: str, payload: ReviewPayload, db: Session = Depends(get_db), admin_user: str = Depends(require_admin)):
    req = crud.set_status(db, request_id, RequestStatus.rejected, payload.admin_notes, payload.reviewed_by or admin_user)
    if not req:
        raise HTTPException(404, "Request not found.")
    return {"id": req.id, "status": req.status}


class ReleasePayload(BaseModel):
    excel_path: str | None = None
    spatial_path: str | None = None
    timelapse_path: str | None = None


@router.post("/requests/{request_id}/release", dependencies=[Depends(require_admin)])
def release(request_id: str, payload: ReleasePayload, db: Session = Depends(get_db)):
    """
    Marks the request as validated + released once the technical team
    has generated and checked the deliverables (typically produced via
    /api/analysis + /api/timelapse + services/reports.py, then attached
    here). This is the gate the workflow description calls for: request
    -> admin queue -> validate -> release.
    """
    req = crud.get_request(db, request_id)
    if not req:
        raise HTTPException(404, "Request not found.")
    if req.status != RequestStatus.approved:
        raise HTTPException(400, "Request must be 'approved' before it can be released.")
    crud.attach_results(db, request_id, payload.excel_path, payload.spatial_path, payload.timelapse_path)
    req = crud.set_status(db, request_id, RequestStatus.released)
    return {"id": req.id, "status": req.status}
