"""
Canopy GeoAI -- single-process Flask web app.

Drought + land-use/land-cover change monitoring for tropical
countries, piloted on Kerala, India. Built on the opengeos/geemap +
leafmap ecosystem (https://github.com/opengeos, https://github.com/giswqs)
for Sentinel-2/Landsat access, index computation, and cartographic
timelapse rendering. Same pattern as the Canopy Geospatial Solutions
gps_accuracy_live_app reference: one Flask entrypoint, server-rendered
templates/, vanilla-JS static/ (no Node.js, no separate frontend
build), backed by MySQL for the admin request/approval workflow.

Named `flask_app.py` rather than `app.py` deliberately -- this
directory already has an `app/` package (core/services/db/api, used
by the legacy FastAPI stack), and a script named `app.py` sitting next
to a package named `app/` is a real Python import collision (its own
`from app.core import ...` would become ambiguous). Bear this in mind
if renaming.

Run locally:
    cd backend
    python flask_app.py
Or in production:
    gunicorn flask_app:app

Docs: README.md / docs/DEPLOYMENT.md
"""
from __future__ import annotations

import os
from datetime import date
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, render_template, send_from_directory, session

from app.core import aoi as aoi_module
from app.core import gee
from app.core.config import TIMELAPSE_DIR, get_settings
from app.db import crud
from app.db.database import SessionLocal, init_db
from app.db.models import RequestStatus
from app.services.analysis import run_analysis
from app.services.indexes import INDEX_CATALOG, INDEX_BY_CODE
from app.services.timelapse import generate_timelapse

settings = get_settings()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = settings.flask_secret_key

init_db()

KERALA_DISTRICTS_FALLBACK = [
    "Thiruvananthapuram", "Kollam", "Pathanamthitta", "Alappuzha", "Kottayam",
    "Idukki", "Ernakulam", "Thrissur", "Palakkad", "Malappuram",
    "Kozhikode", "Wayanad", "Kannur", "Kasaragod",
]
KERALA_BBOX = (74.86, 8.29, 77.42, 12.82)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_user"):
            return jsonify({"error": "Not logged in."}), 401
        return fn(*args, **kwargs)
    return wrapper


# --------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------- #
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/admin")
def admin_page():
    return render_template("admin.html")


# --------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "gee_available": gee.is_available(),
        "aoi_available": aoi_module.is_available(),
    })


@app.get("/api/catalog/indexes")
def catalog_indexes():
    return jsonify([
        {
            "code": i.code, "name": i.name, "formula": i.formula, "category": i.category,
            "reference": i.reference, "interpretation": i.interpretation,
        }
        for i in INDEX_CATALOG
    ])


@app.get("/api/catalog/aoi")
def catalog_aoi():
    if aoi_module.is_available():
        return jsonify({
            "state": "Kerala",
            "districts": aoi_module.district_names(),
            "bbox": aoi_module.state_bbox(),
            "boundary_source": "shapefile",
        })
    return jsonify({
        "state": "Kerala",
        "districts": KERALA_DISTRICTS_FALLBACK,
        "bbox": KERALA_BBOX,
        "boundary_source": "bbox-placeholder",
    })


@app.get("/api/catalog/kerala-geojson")
def catalog_kerala_geojson():
    """District boundaries as GeoJSON, for the Leaflet map. Empty
    FeatureCollection if the shapefile isn't loaded (see core/aoi.py)."""
    if not aoi_module.is_available():
        return jsonify({"type": "FeatureCollection", "features": []})
    import geopandas as gpd

    gdf = gpd.read_file(settings.kerala_shapefile_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    return app.response_class(gdf.to_json(), mimetype="application/json")


# --------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------- #
@app.post("/api/analysis")
def api_analysis():
    payload = request.get_json(force=True) or {}
    try:
        indexes = payload.get("indexes") or ["NDVI", "NDWI", "NDDI"]
        unknown = [c for c in indexes if c not in INDEX_BY_CODE]
        if unknown:
            return jsonify({"error": f"Unknown index code(s): {unknown}"}), 400
        result = run_analysis(
            aoi_name=payload.get("aoi_name", "Kerala"),
            data_source=payload.get("data_source", "sentinel-2"),
            pre_start=_parse_date(payload["pre_start"]),
            pre_end=_parse_date(payload["pre_end"]),
            post_start=_parse_date(payload["post_start"]),
            post_end=_parse_date(payload["post_end"]),
            indexes=indexes,
        )
        return jsonify(result)
    except ValueError as exc:
        status = 404 if "No cloud-free scenes" in str(exc) else 400
        return jsonify({"error": str(exc)}), status
    except (KeyError, TypeError) as exc:
        return jsonify({"error": f"Invalid request: {exc}"}), 400


# --------------------------------------------------------------------- #
# Timelapse
# --------------------------------------------------------------------- #
@app.post("/api/timelapse")
def api_timelapse():
    payload = request.get_json(force=True) or {}
    try:
        result = generate_timelapse(
            aoi_name=payload.get("aoi_name", "Kerala"),
            index_code=payload.get("index_code", "NDVI"),
            start=_parse_date(payload["start"]),
            end=_parse_date(payload["end"]),
            step_months=int(payload.get("step_months", 1)),
            fps=float(payload.get("fps", 1.0)),
        )
    except ValueError as exc:
        status = 503 if "requires the Google Earth Engine" in str(exc) else 400
        return jsonify({"error": str(exc)}), status
    except (KeyError, TypeError) as exc:
        return jsonify({"error": f"Invalid request: {exc}"}), 400

    run_id = result["run_id"]
    gif_name = Path(result["gif_path"]).name
    return jsonify({
        "run_id": run_id,
        "frame_count": result["frame_count"],
        "gif_url": f"/timelapse-files/{run_id}/{gif_name}",
        "frame_urls": [f"/timelapse-files/{run_id}/{Path(p).name}" for p in result["frame_paths"]],
    })


@app.get("/timelapse-files/<run_id>/<path:filename>")
def timelapse_files(run_id: str, filename: str):
    directory = TIMELAPSE_DIR / run_id
    return send_from_directory(directory, filename)


# --------------------------------------------------------------------- #
# Dataset requests (public) + Admin queue
# --------------------------------------------------------------------- #
@app.post("/api/requests")
def submit_request():
    payload = request.get_json(force=True) or {}
    required = ["requester_name", "requester_email", "aoi_name", "data_source", "indexes", "date_start", "date_end"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"error": f"Missing required field(s): {missing}"}), 400

    db = SessionLocal()
    try:
        req = crud.create_request(db, {
            "requester_name": payload["requester_name"],
            "requester_email": payload["requester_email"],
            "organization": payload.get("organization"),
            "aoi_name": payload["aoi_name"],
            "data_source": payload["data_source"],
            "indexes": payload["indexes"],
            "date_start": payload["date_start"],
            "date_end": payload["date_end"],
            "purpose": payload.get("purpose"),
        })
        return jsonify({"id": req.id, "status": req.status.value})
    finally:
        db.close()


@app.get("/api/requests/<request_id>")
def request_status(request_id: str):
    db = SessionLocal()
    try:
        req = crud.get_request(db, request_id)
        if not req:
            return jsonify({"error": "not found"}), 404
        released = req.status == RequestStatus.released
        return jsonify({
            "id": req.id,
            "status": req.status.value,
            "aoi_name": req.aoi_name,
            "created_at": req.created_at.isoformat(),
            "result_excel_path": req.result_excel_path if released else None,
            "result_spatial_path": req.result_spatial_path if released else None,
            "result_timelapse_path": req.result_timelapse_path if released else None,
        })
    finally:
        db.close()


@app.post("/api/admin/login")
def admin_login():
    payload = request.get_json(force=True) or {}
    username, password = payload.get("username"), payload.get("password")
    if username == settings.admin_username and password == settings.admin_password:
        session["admin_user"] = username
        return jsonify({"ok": True, "username": username})
    return jsonify({"error": "Invalid username or password."}), 401


@app.post("/api/admin/logout")
def admin_logout():
    session.pop("admin_user", None)
    return jsonify({"ok": True})


@app.get("/api/admin/session")
def admin_session():
    return jsonify({"logged_in": bool(session.get("admin_user")), "username": session.get("admin_user")})


@app.get("/api/admin/requests")
@require_admin
def admin_list_requests():
    status = request.args.get("status")
    db = SessionLocal()
    try:
        reqs = crud.list_requests(db, status)
        return jsonify([
            {
                "id": r.id, "requester_name": r.requester_name, "requester_email": r.requester_email,
                "organization": r.organization, "aoi_name": r.aoi_name, "data_source": r.data_source,
                "indexes": r.indexes, "date_start": r.date_start, "date_end": r.date_end,
                "purpose": r.purpose, "status": r.status.value, "admin_notes": r.admin_notes,
                "created_at": r.created_at.isoformat(),
                "result_excel_path": r.result_excel_path, "result_spatial_path": r.result_spatial_path,
                "result_timelapse_path": r.result_timelapse_path,
            }
            for r in reqs
        ])
    finally:
        db.close()


@app.post("/api/admin/requests/<request_id>/approve")
@require_admin
def admin_approve(request_id: str):
    payload = request.get_json(force=True) or {}
    db = SessionLocal()
    try:
        req = crud.set_status(db, request_id, RequestStatus.approved, payload.get("admin_notes"), session["admin_user"])
        if not req:
            return jsonify({"error": "not found"}), 404
        return jsonify({"id": req.id, "status": req.status.value})
    finally:
        db.close()


@app.post("/api/admin/requests/<request_id>/reject")
@require_admin
def admin_reject(request_id: str):
    payload = request.get_json(force=True) or {}
    db = SessionLocal()
    try:
        req = crud.set_status(db, request_id, RequestStatus.rejected, payload.get("admin_notes"), session["admin_user"])
        if not req:
            return jsonify({"error": "not found"}), 404
        return jsonify({"id": req.id, "status": req.status.value})
    finally:
        db.close()


@app.post("/api/admin/requests/<request_id>/release")
@require_admin
def admin_release(request_id: str):
    payload = request.get_json(force=True) or {}
    db = SessionLocal()
    try:
        req = crud.get_request(db, request_id)
        if not req:
            return jsonify({"error": "not found"}), 404
        if req.status != RequestStatus.approved:
            return jsonify({"error": "Request must be 'approved' before it can be released."}), 400
        crud.attach_results(
            db, request_id,
            payload.get("excel_path"), payload.get("spatial_path"), payload.get("timelapse_path"),
        )
        req = crud.set_status(db, request_id, RequestStatus.released)
        return jsonify({"id": req.id, "status": req.status.value})
    finally:
        db.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
