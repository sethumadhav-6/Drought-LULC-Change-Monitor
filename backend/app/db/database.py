"""SQLite engine/session setup (SQLAlchemy). Simple local backend per
the "single admin, no login" MVP scope -- swap database_url for
Postgres later without touching the models/CRUD code."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..core.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401
    from .models import Base

    Base.metadata.create_all(bind=engine)
