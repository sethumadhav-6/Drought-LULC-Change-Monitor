"""SQLAlchemy engine/session setup. MySQL is the primary target (see
Settings.database_url in core/config.py -- built from MYSQL_HOST/USER/
PASSWORD/DATABASE env vars), with an automatic SQLite fallback for quick
local testing when no MySQL server is configured. The models/CRUD code
is DB-agnostic either way."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..core.config import get_settings

settings = get_settings()
_url = settings.database_url
connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}
# pool_pre_ping avoids "MySQL server has gone away" errors from stale
# connections after MySQL's default idle-connection timeout.
engine = create_engine(_url, connect_args=connect_args, pool_pre_ping=not _url.startswith("sqlite"))
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
