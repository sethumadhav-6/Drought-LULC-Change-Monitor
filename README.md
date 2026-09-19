# Canopy GeoAI — Drought & Land Use/Land Cover Change Monitor

A geospatial AI application for monitoring **drought stress** and **land use / land
cover (LULC) change** across tropical countries, piloted on **Kerala, India**.
Built on the [opengeos](https://github.com/opengeos) / [giswqs](https://github.com/giswqs)
open-source geospatial-Python stack — `geemap`, `leafmap`, `cartoee` — for Sentinel-2
and Landsat access, index computation, and cartographic timelapse rendering.

## Why

Kerala's monsoon-driven hydrology means large land-cover change in the pre-monsoon
season (e.g. forest/wetland loss, reduced soil moisture) can compound flood, runoff,
and landslide risk once the monsoon arrives. This app lets a state official compare
pre- vs post-monsoon Sentinel-2/Landsat composites, compute standard drought and
vegetation indices, flag significant "shrinkage" transitions (forest/water → bare/
built-up) above a configurable area threshold, and generate a print-ready report
(timelapse + Excel + spatial exports) ahead of the next monsoon.

## Architecture

**Primary app: Flask + MySQL, one process, no build step.** Same pattern as Canopy
Geospatial Solutions' `gps_accuracy_live_app` reference: a single Flask entrypoint,
server-rendered HTML templates, vanilla JS in `static/` (no Node.js, no React, no
npm install, no CORS), deployed with `gunicorn`.

```
canopy-geoai/
  run.py                   One-command launcher (pins the right conda env, see below).
  backend/
    flask_app.py            Flask entrypoint: page routes (/,  /admin) + JSON API routes.
    templates/               index.html (dashboard), admin.html (request queue).
    static/                  main.js, admin.js, styles.css, logo.png -- vanilla JS/CSS.
    app/
      core/                  GEE auth (core/gee.py), Planetary Computer fallback
                              (core/stac_pc.py), Kerala shapefile AOI loader (core/aoi.py).
      services/               Index library, drought engine, LULC change detection,
                               timelapse/cartographic rendering, Excel/spatial reports --
                               framework-agnostic, called directly by flask_app.py.
      db/                     MySQL-backed (SQLite fallback) admin request/approval workflow.
      api/, main.py            Superseded FastAPI REST API -- see "Superseded stacks" below.
    streamlit_app.py, pages/  Superseded Streamlit UI -- see "Superseded stacks" below.
  frontend/                  Superseded Next.js UI -- see "Superseded stacks" below.
  data_store/                Generated timelapses/reports/spatial exports + your Kerala
                              shapefile (data_store/shapefiles/). MySQL holds the admin DB.
  docs/                      Index formula reference, deployment guide, data-source notes.
```

Data access is dual-path: **Google Earth Engine** (via `geemap`) is the primary
source and is what Timelapse generation requires; when GEE isn't configured,
Analysis automatically falls back to the **Microsoft Planetary Computer** open
STAC catalog (no account needed) for Sentinel-2/Landsat search + local index
computation.

## Quick start

**One-time setup — macOS/Linux**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**One-time setup — Windows**

`rasterio`/GDAL/`cartopy` (used for index math and the cartographic timelapse
renderer) don't have reliable `pip`-installable wheels on native Windows — use
conda instead (Anaconda/Miniconda):

```powershell
cd backend
conda env create -f environment.yml
copy .env.example .env
```

This pins a couple of versions that matter (see comments in `environment.yml`):
`setuptools<81` (newer setuptools dropped `pkg_resources`, which `geemap`
still imports) and `ipython<9` (`geemap`'s toolbar module uses an IPython
import path removed in 9.x). Both are upstream `geemap` compatibility issues,
not something specific to this app.

**MySQL**

Edit `backend/.env` with your MySQL credentials:
```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=canopy
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=canopy_geoai
```
Create the database if it doesn't exist yet: `CREATE DATABASE canopy_geoai;` in
a MySQL client. The app creates its one table (`dataset_requests`) automatically
on first run. If you leave `MYSQL_HOST` unset, the app falls back to a local
SQLite file instead — fine for quick testing without a MySQL server handy.

**Run it**
```powershell
cd canopy-geoai        # repo root
python run.py
```
Open http://localhost:5000 — dashboard at `/`, admin queue at `/admin`.
`run.py` runs the app inside the `canopy-geoai` conda env directly (via `conda
run -n canopy-geoai`) regardless of what `python` on your PATH would otherwise
resolve to — this avoids a real issue hit during development where a stray
global Python install shadowed the conda one, causing confusing
partial-failure symptoms. If you're on macOS/Linux with a plain venv instead
of conda, just run `python flask_app.py` from inside `backend/` with that
venv active.

## Getting Google Earth Engine access

1. Sign up / register a Cloud project for Earth Engine at
   https://code.earthengine.google.com/register (free for research/government/
   nonprofit use).
2. In that Google Cloud project: enable the **Earth Engine API**, then create a
   **service account** (IAM & Admin → Service Accounts → Create) and grant it
   two roles: **Earth Engine Resource Writer** and **Service Usage Consumer**
   (both are required — Earth Engine calls fail with a permissions error if
   only one is present).
3. Create a JSON key for that service account (Keys → Add key → JSON) and
   download it.
4. In `backend/.env`, set:
   - `GEE_SERVICE_ACCOUNT` = the service account's email (looks like
     `canopy-geoai@your-project.iam.gserviceaccount.com`)
   - `GEE_SERVICE_ACCOUNT_KEY_PATH` = path to the downloaded JSON file (local
     dev), **or** `GEE_SERVICE_ACCOUNT_KEY_JSON` = the file's contents pasted
     as one line (needed for hosting where you can't drop in a key file)
   - `GEE_PROJECT` = your Google Cloud project ID
5. Restart the app. Check `GET http://localhost:5000/api/health` — should show
   `"gee_available": true`.

If you'd rather not set this up yet, leave GEE unset: Analysis will
automatically use the Planetary Computer fallback (no account needed);
Timelapse generation requires GEE.

## Admin login

The admin queue (`/admin`) uses a single pilot account, set in `backend/.env`
(or `Settings` defaults if unset):

```
ADMIN_USERNAME=canopyceo
ADMIN_PASSWORD=plothy@4578
```

Change these — and `FLASK_SECRET_KEY` (used to sign the login session cookie)
— before sharing the app beyond your own testing. This is a single shared
account (MVP-level auth), not per-user login. See `backend/flask_app.py` for
the login/session logic.

## Core workflow

1. **Dashboard** (`/`) — pick Sentinel-2 or Landsat (collapsible section), pick
   one or more indexes (collapsible section, sourced from the index catalog —
   see `docs/INDEX_LIBRARY.md`), run pre- vs post-monsoon Analysis, generate a
   Timelapse for the whole state or a single district.
2. **Can't self-serve a dataset?** Use "Request it" — submits to the admin
   queue.
3. **Admin** (`/admin`) — the Canopy technical team reviews the queue,
   approves or rejects, and once the deliverables are generated (via the
   Analysis/Timelapse tools on the main dashboard) and validated,
   **releases** them — spatial (GeoTIFF/GeoPackage) + Excel paths become
   visible to the requester.
4. **Print** — the Timelapse section has a "Print latest frame" button that
   opens the frame full-size and triggers your browser's print dialog, for a
   copy with graticule, north arrow, scale bar, and legend already baked in.

## Status: MVP scope

This build is a **deep, working pipeline for Kerala** — Sentinel-2/Landsat
access (both backends), the full index + drought (VCI/TCI/VHI/NDDI) engine,
cartographic timelapse rendering, Excel/spatial report export, and a
MySQL-backed admin request/approval workflow — with the Flask UI wired
directly to all of it (the actual GEE/analysis/timelapse logic lives in
framework-agnostic `services/` modules, called directly by Flask — no HTTP
layer in between).

**Land-change signal: weighted NDVI+NDBI, not LULC.** `services/lulc.py`'s
rule-based change-matrix classifier exists in the repo but is deliberately
*not* wired into the UI — project direction is to skip a discrete LULC
classification step and instead weight NDVI and NDBI directly
(`services/drought.py::land_stress_index`, default 0.6 NDVI / 0.4 NDBI,
adjustable) into a single continuous land-stress score. See that
function's docstring for the exact formula and reasoning.

**Ancillary layers loaded and shown as context, not yet scored.** DEM +
soil/drainage/geomorphology/geology (real Kerala datasets, see
`docs/ANCILLARY_DATA.md`) are loaded and queryable via `GET
/api/catalog/ancillary?aoi_name=...` (`app/core/ancillary.py`), and the
dashboard now shows a plain-language "Terrain context" paragraph tying
them to the index results. They're not yet folded into
`land_stress_index()`'s numeric score -- that weighting is a methodology
decision to make deliberately, not guess at.

**"Publish for web" uses folium.** `services/webgis_publish.py` builds
the standalone WebGIS viewer with
[folium](https://github.com/python-visualization/folium) (a Leaflet.js
wrapper that renders server-side to one self-contained HTML file).
folium's sibling libraries [ipyleaflet](https://github.com/jupyter-widgets/ipyleaflet)
and [ipywidgets](https://github.com/jupyter-widgets/ipywidgets) need a
live Jupyter kernel talking to the page over a websocket, so they can't
produce a static file the way folium does and aren't used in this Flask
app.

Left for the next iteration: wiring the ancillary layers into scoring,
background job handling for very long timelapse runs (requests currently
block the requesting user's session while they run), and extending the
AOI catalog to other tropical
countries. See `docs/DATA_SOURCES.md`.

## Superseded stacks

This app went through a few iterations during development; each prior stack
is still in the repo and still works, but isn't the maintained path going
forward. In all cases, the same `services/analysis.py` and
`services/timelapse.py::generate_timelapse` functions are what actually do
the work — only the UI layer differs, so fixes made for one apply to all.

- **Streamlit** (`backend/streamlit_app.py`, `backend/pages/`) — single
  Python process like the current Flask app, but Streamlit's own runtime
  overhead makes it slower under real hosting load, which is why this
  moved to Flask. Run with `streamlit run streamlit_app.py` from `backend/`.
- **Next.js + FastAPI** (`frontend/`, `backend/app/api/`, `backend/app/main.py`)
  — the original split-stack build (Vercel + Render). See
  `docs/DEPLOYMENT.md` for those steps if you specifically want a
  Vercel-hosted frontend.

## Docs

- [`docs/INDEX_LIBRARY.md`](docs/INDEX_LIBRARY.md) — every spectral/drought index implemented, formula + source.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — hosting the Flask app on your own server, plus the superseded Render/Vercel steps.
- [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) — Sentinel-2/Landsat collections used, AOI boundary notes, known limitations.
#   D r o u g h t - L U L C - C h a n g e - M o n i t o r  
 