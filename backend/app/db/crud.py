"""CRUD helpers for the dataset-request admin workflow."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AnalysisRun, DatasetRequest, RequestStatus


def create_request(db: Session, payload: dict) -> DatasetRequest:
    req = DatasetRequest(**payload)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def list_requests(db: Session, status: str | None = None) -> list[DatasetRequest]:
    q = db.query(DatasetRequest)
    if status:
        q = q.filter(DatasetRequest.status == status)
    return q.order_by(DatasetRequest.created_at.desc()).all()


def get_request(db: Session, request_id: str) -> DatasetRequest | None:
    return db.query(DatasetRequest).filter(DatasetRequest.id == request_id).first()


def set_status(db: Session, request_id: str, status: RequestStatus, admin_notes: str | None = None, reviewed_by: str | None = None) -> DatasetRequest | None:
    req = get_request(db, request_id)
    if not req:
        return None
    req.status = status
    if admin_notes is not None:
        req.admin_notes = admin_notes
    if reviewed_by is not None:
        req.reviewed_by = reviewed_by
    db.commit()
    db.refresh(req)
    return req


def attach_results(db: Session, request_id: str, excel_path: str | None = None, spatial_path: str | None = None, timelapse_path: str | None = None) -> DatasetRequest | None:
    req = get_request(db, request_id)
    if not req:
        return None
    if excel_path:
        req.result_excel_path = excel_path
    if spatial_path:
        req.result_spatial_path = spatial_path
    if timelapse_path:
        req.result_timelapse_path = timelapse_path
    db.commit()
    db.refresh(req)
    return req


def create_analysis_run(db: Session, payload: dict) -> AnalysisRun:
    run = AnalysisRun(**payload)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def list_analysis_runs(db: Session, limit: int = 200) -> list[AnalysisRun]:
    return db.query(AnalysisRun).order_by(AnalysisRun.created_at.desc()).limit(limit).all()
