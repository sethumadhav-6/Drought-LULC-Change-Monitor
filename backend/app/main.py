"""
Canopy GeoAI -- FastAPI entrypoint.

Drought + land-use/land-cover change monitoring for tropical
countries, piloted on Kerala, India. Built on the opengeos/geemap +
leafmap ecosystem (https://github.com/opengeos, https://github.com/giswqs)
for Sentinel-2 / Landsat access, index computation, and cartographic
timelapse rendering.

Run locally:   uvicorn app.main:app --reload --port 8000
Docs:          http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import routes_admin, routes_analysis, routes_catalog, routes_requests, routes_timelapse
from .core import gee
from .core.config import get_settings
from .db.database import init_db

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Drought & LULC change monitoring for tropical countries (Kerala pilot).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_catalog.router)
app.include_router(routes_analysis.router)
app.include_router(routes_timelapse.router)
app.include_router(routes_requests.router)
app.include_router(routes_admin.router)


@app.on_event("startup")
def on_startup():
    init_db()
    gee.is_available()  # warms the GEE init attempt once at boot; logs the outcome either way


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "gee_available": gee.is_available(),
    }
