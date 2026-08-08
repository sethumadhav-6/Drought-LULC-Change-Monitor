"""
Public-facing endpoints for the "request a dataset" flow: any signed-in
official/user submits a request (AOI + date range + indexes + purpose).
It lands in the admin queue as `requested`. See routes_admin.py for the
review/approve/release side.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..db import crud
from ..db.database import get_db
from ..db.models import RequestStatus

router = APIRouter(prefix="/api/requests", tags=["requests"])


class DatasetRequestIn(BaseModel):
    requester_name: str
    requester_email: EmailStr
    organization: str | None = None
    aoi_name: str
    aoi_geojson: dict | None = None
    data_source: str
    indexes: list[str]
    date_start: date
    date_end: date
    purpose: str | None = None


@router.post("")
def submit_request(payload: DatasetRequestIn, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["date_start"] = str(data["date_start"])
    data["date_end"] = str(data["date_end"])
    req = crud.create_request(db, data)
    return {"id": req.id, "status": req.status}


@router.get("/{request_id}")
def get_request_status(request_id: str, db: Session = Depends(get_db)):
    req = crud.get_request(db, request_id)
    if not req:
        return {"error": "not found"}
    return {
        "id": req.id,
        "status": req.status,
        "aoi_name": req.aoi_name,
        "created_at": req.created_at,
        "result_excel_path": req.result_excel_path if req.status == RequestStatus.released else None,
        "result_spatial_path": req.result_spatial_path if req.status == RequestStatus.released else None,
        "result_timelapse_path": req.result_timelapse_path if req.status == RequestStatus.released else None,
    }
