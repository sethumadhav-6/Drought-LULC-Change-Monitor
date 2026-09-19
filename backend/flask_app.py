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

from app.core import ancillary as ancillary_module
from app.core import aoi as aoi_module
from app.core import gee
from app.core.config import TIMELAPSE_DIR, WEBGIS_DIR, get_settings
from app.db import crud
from app.db.database import SessionLocal, init_db
from app.db.models import RequestStatus
from app.services.analysis import run_analysis, get_layer_tile
from app.services.indexes import INDEX_CATALOG, INDEX_BY_CODE
from app.services.timelapse import generate_timelapse
from app.services.webgis_publish import publish_analysis_layer, publish_timelapse

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
        # Not yet used in the analysis math -- scaffolding for whenever DEM/
        # soil/geomorphology data gets configured (see core/ancillary.py).
        "ancillary_available": ancillary_module.availability(),
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


@app.get("/api/catalog/ancillary")
def catalog_ancillary():
    """
    AOI-level summary of the ancillary layers (DEM elevation stats,
    dominant soil-drainage/geomorphology/geology categories) -- not the
    raw features. drainage.shp alone has ~159k line features; sending
    that (or the other layers at full resolution) as GeoJSON to the
    browser would be tens of MB per request, so this returns a compact
    summary instead. Not yet used by the analysis math -- see
    core/ancillary.py and docs/ANCILLARY_DATA.md.
    """
    aoi_name = request.args.get("aoi_name", "Kerala")
    availability = ancillary_module.availability()

    geom = None
    bbox = None
    if aoi_module.is_available():
        if aoi_name.strip().lower() in ("kerala", "kerala (state)"):
            geom = aoi_module.state_geometry()
            bbox = aoi_module.state_bbox()
        else:
            geom = aoi_module.district_geometry(aoi_name)
            bbox = aoi_module.district_bbox(aoi_name)

    result = {"aoi_name": aoi_name, "available": availability}
    if availability["dem"]:
        result["elevation"] = ancillary_module.elevation_stats(bbox)
    for layer in ("soil", "geomorphology", "geology", "drainage"):
        if availability[layer]:
            result[layer] = ancillary_module.summarize_layer(layer, geom)
    return jsonify(result)


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
        aoi_name = payload.get("aoi_name", "Kerala")
        data_source = payload.get("data_source", "sentinel-2")
        pre_start, pre_end = payload["pre_start"], payload["pre_end"]
        post_start, post_end = payload["post_start"], payload["post_end"]
        result = run_analysis(
            aoi_name=aoi_name,
            data_source=data_source,
            pre_start=_parse_date(pre_start),
            pre_end=_parse_date(pre_end),
            post_start=_parse_date(post_start),
            post_end=_parse_date(post_end),
            indexes=indexes,
        )

        # Log this run for the admin dashboard's analytics history, best
        # effort -- a DB hiccup here shouldn't take down the response the
        # user is waiting on, since the analysis itself already succeeded.
        try:
            db = SessionLocal()
            try:
                crud.create_analysis_run(db, {
                    "user_name": (payload.get("user_name") or "").strip() or None,
                    "user_email": (payload.get("user_email") or "").strip() or None,
                    "aoi_name": aoi_name,
                    "data_source": data_source,
                    "pre_start": pre_start,
                    "pre_end": pre_end,
                    "post_start": post_start,
                    "post_end": post_end,
                    "indexes": indexes,
                    "source_used": result.get("source_used", "unknown"),
                    "stats": result.get("stats", {}),
                })
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            app.logger.exception("Failed to log analysis run for admin history")

        return jsonify(result)
    except ValueError as exc:
        status = 404 if "No cloud-free scenes" in str(exc) else 400
        return jsonify({"error": str(exc)}), status
    except (KeyError, TypeError) as exc:
        return jsonify({"error": f"Invalid request: {exc}"}), 400


@app.post("/api/analysis/layer-tile")
def api_layer_tile():
    """Re-render one Pre/Post layer with a custom palette/min/max, for the
    Map Layers panel's colormap customization controls."""
    payload = request.get_json(force=True) or {}
    try:
        tile_url = get_layer_tile(
            aoi_name=payload.get("aoi_name", "Kerala"),
            index_code=payload["index_code"],
            period=payload["period"],
            pre_start=_parse_date(payload["pre_start"]),
            pre_end=_parse_date(payload["pre_end"]),
            post_start=_parse_date(payload["post_start"]),
            post_end=_parse_date(payload["post_end"]),
            vis={
                "min": float(payload.get("min", -1)),
                "max": float(payload.get("max", 1)),
                "palette": payload.get("palette") or ["#a50026", "#ffffbf", "#1a9850"],
            },
        )
        return jsonify({"tile_url": tile_url})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
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
# WebGIS publish -- static, standalone packages for embedding on
# www.canopygs.in or any other website (see app/services/webgis_publish.py
# for why this is separate from the live Map Layers panel).
# --------------------------------------------------------------------- #
@app.post("/api/publish/analysis-layer")
def api_publish_analysis_layer():
    payload = request.get_json(force=True) or {}
    try:
        result = publish_analysis_layer(
            aoi_name=payload.get("aoi_name", "Kerala"),
            index_code=payload["index_code"],
            period=payload["period"],
            pre_start=_parse_date(payload["pre_start"]),
            pre_end=_parse_date(payload["pre_end"]),
            post_start=_parse_date(payload["post_start"]),
            post_end=_parse_date(payload["post_end"]),
            vis={
                "min": float(payload["min"]), "max": float(payload["max"]), "palette": payload["palette"],
            } if payload.get("palette") else None,
        )
        return jsonify({
            "publish_id": result["publish_id"],
            "viewer_url": f"/webgis/{result['publish_id']}/viewer.html",
            "folder": result["dir"],
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except (KeyError, TypeError) as exc:
        return jsonify({"error": f"Invalid request: {exc}"}), 400


@app.post("/api/publish/timelapse/<run_id>")
def api_publish_timelapse(run_id: str):
    payload = request.get_json(force=True) or {}
    try:
        result = publish_timelapse(run_id, aoi_name=payload.get("aoi_name"))
        return jsonify({
            "publish_id": result["publish_id"],
            "viewer_url": f"/webgis/{result['publish_id']}/viewer.html",
            "folder": result["dir"],
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/webgis/<publish_id>/<path:filename>")
def webgis_files(publish_id: str, filename: str):
    """
    Serves a published package for in-app preview (e.g. clicking the
    'Preview' link right after publishing). The same folder at
    WEBGIS_DIR/<publish_id>/ is also meant to be copied/uploaded as-is to
    an actual website -- this route is a convenience, not the intended
    long-term hosting location.
    """
    directory = WEBGIS_DIR / publish_id
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


@app.get("/api/admin/analysis-runs")
@require_admin
def admin_analysis_runs():
    """History of every dashboard Analysis run (see AnalysisRun in
    db/models.py) -- separate from the dataset-request queue below, this
    is just visibility into what users have been running."""
    db = SessionLocal()
    try:
        runs = crud.list_analysis_runs(db)
        return jsonify([
            {
                "id": r.id, "user_name": r.user_name, "user_email": r.user_email,
                "aoi_name": r.aoi_name, "data_source": r.data_source,
                "pre_start": r.pre_start, "pre_end": r.pre_end,
                "post_start": r.post_start, "post_end": r.post_end,
                "indexes": r.indexes, "source_used": r.source_used,
                "stats": r.stats, "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ])
    finally:
        db.close()


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
