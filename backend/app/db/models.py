"""ORM models for the dataset request / admin-approval workflow.

Lifecycle: requested -> under_review -> approved|rejected -> released
An official (or automated job) submits a request for an AOI/date
range/index. It lands in the admin queue. The Canopy technical team
reviews, validates, and only then "releases" the dataset -- at which
point it becomes downloadable (spatial + Excel) from the portal.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RequestStatus(str, enum.Enum):
    requested = "requested"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    released = "released"


def _uuid() -> str:
    return str(uuid.uuid4())


class DatasetRequest(Base):
    __tablename__ = "dataset_requests"

    # Explicit lengths on every String column: SQLite doesn't care, but
    # MySQL's VARCHAR requires a length or SQLAlchemy fails to compile the
    # table (this model needs to work on both backends -- see core/aoi.py
    # docstring on the MySQL/SQLite dual-backend setup in db/database.py).
    id = Column(String(36), primary_key=True, default=_uuid)
    requester_name = Column(String(255), nullable=False)
    requester_email = Column(String(255), nullable=False)
    organization = Column(String(255), nullable=True)

    aoi_name = Column(String(255), nullable=False)      # e.g. "Idukki district" or "Kerala (state)"
    aoi_geojson = Column(JSON, nullable=True)           # custom AOI, if drawn on the map
    data_source = Column(String(50), nullable=False)    # "sentinel-2" | "landsat"
    indexes = Column(JSON, nullable=False)              # e.g. ["NDVI","NDDI","VHI"]
    date_start = Column(String(20), nullable=False)
    date_end = Column(String(20), nullable=False)
    purpose = Column(Text, nullable=True)

    status = Column(Enum(RequestStatus), default=RequestStatus.requested, nullable=False)
    admin_notes = Column(Text, nullable=True)
    reviewed_by = Column(String(255), nullable=True)

    result_excel_path = Column(String(500), nullable=True)
    result_spatial_path = Column(String(500), nullable=True)
    result_timelapse_path = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AnalysisRun(Base):
    """
    A log of every /api/analysis call made from the public dashboard --
    separate from DatasetRequest (which is the formal admin-approval
    workflow for datasets someone can't self-serve). This just lets the
    Canopy team see, from the admin dashboard, what analyses users have
    actually been running: who, which AOI, which indexes, what the
    results were. Optional user_name/user_email -- the dashboard doesn't
    require login, so these are only populated if the user filled in the
    (optional) name/email fields on the Analysis panel.
    """
    __tablename__ = "analysis_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_name = Column(String(255), nullable=True)
    user_email = Column(String(255), nullable=True)

    aoi_name = Column(String(255), nullable=False)
    data_source = Column(String(50), nullable=False)
    pre_start = Column(String(20), nullable=False)
    pre_end = Column(String(20), nullable=False)
    post_start = Column(String(20), nullable=False)
    post_end = Column(String(20), nullable=False)
    indexes = Column(JSON, nullable=False)
    source_used = Column(String(50), nullable=False)  # "gee" | "planetary-computer"
    stats = Column(JSON, nullable=False)               # full result["stats"] payload

    created_at = Column(DateTime, default=datetime.utcnow)
