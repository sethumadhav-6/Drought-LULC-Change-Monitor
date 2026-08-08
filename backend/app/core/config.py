"""
Central configuration for the Canopy GeoAI backend.

Reads settings from environment variables (.env in local dev, platform
env vars on Render). See ../../.env.example for the full list.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_STORE_DIR = Path(
    os.environ.get("DATA_STORE_DIR", BACKEND_DIR.parent / "data_store")
)
REQUESTS_DIR = DATA_STORE_DIR / "requests"
RELEASED_DIR = DATA_STORE_DIR / "released"
TIMELAPSE_DIR = DATA_STORE_DIR / "timelapses"
REPORTS_DIR = DATA_STORE_DIR / "reports"

for _d in (REQUESTS_DIR, RELEASED_DIR, TIMELAPSE_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """App-wide settings, override via environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Canopy GeoAI"
    environment: str = "development"

    # --- Google Earth Engine ---
    # Preferred path: a service account (works headless on Render).
    gee_service_account: str | None = None          # e.g. canopy-geoai@my-project.iam.gserviceaccount.com
    gee_service_account_key_path: str | None = None  # path to the JSON key file
    gee_service_account_key_json: str | None = None  # or the raw JSON as a single env var (Render-friendly)
    gee_project: str | None = None                   # Earth Engine / Cloud project id

    # --- Microsoft Planetary Computer (no-auth fallback for Sentinel-2/Landsat) ---
    pc_stac_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"

    # --- CORS ---
    allowed_origins: list[str] = ["http://localhost:4521"]

    # --- Admin ---
    # MVP-level single-account login for the admin review queue. Override
    # both via env vars (or .env) before deploying anywhere shared/public.
    admin_username: str = "canopyceo"
    admin_password: str = "plothy@4578"

    # --- Flask session cookie signing (admin login) ---
    flask_secret_key: str = "change-me-flask-secret-key"

    # --- Database: MySQL primary, SQLite automatic fallback for quick local
    # testing without a MySQL server set up. Set DATABASE_URL directly to
    # override both (e.g. for a different DB entirely). ---
    mysql_host: str | None = None
    mysql_port: int = 3306
    mysql_user: str | None = None
    mysql_password: str | None = None
    mysql_database: str = "canopy_geoai"
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        if self.mysql_host and self.mysql_user:
            from urllib.parse import quote_plus

            pw = quote_plus(self.mysql_password or "")
            return f"mysql+pymysql://{self.mysql_user}:{pw}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        return f"sqlite:///{DATA_STORE_DIR}/canopy.db"

    # --- AOI boundaries ---
    # Precise Kerala district boundaries (GADM-format shapefile: NAME_2 =
    # district name). Replaces the FAO GAUL / bounding-box placeholders on
    # the Planetary Computer path once present. See core/aoi.py.
    kerala_shapefile_path: str = str(DATA_STORE_DIR / "shapefiles" / "kerala_districts.shp")


@lru_cache
def get_settings() -> Settings:
    return Settings()
