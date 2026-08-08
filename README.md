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

```
canopy-geoai/
  backend/     FastAPI + geemap/leafmap (Python). Sentinel-2/Landsat access,
               index + drought + LULC-change engine, timelapse/report generation,
               SQLite-backed admin request/approval workflow. -> deploy to Render.
  frontend/    Next.js (TypeScript, Tailwind, react-leaflet). Map UI with
               collapsible Sentinel-2/Landsat + index sections, timelapse viewer,
               dataset-request form, admin review queue, print view. -> deploy to Vercel.
  data_store/  Local file store for generated timelapses/reports/spatial exports
               (mount a persistent disk here in production -- see render.yaml).
  docs/        Index formula reference, deployment guide, data-source notes.
```

Data access is dual-path: **Google Earth Engine** (via `geemap`) is the primary
source and is what the "indexes"/"timelapse" endpoints assume; when GEE isn't
configured, the backend automatically falls back to the **Microsoft Planetary
Computer** open STAC catalog (no account needed) for Sentinel-2/Landsat search +
local index computation.

## Quick start (local dev)

**Run both at once** — after doing the one-time setup below for backend and
frontend separately (installing deps, `.env` files), you don't need two
terminals every time. From the repo root:

```powershell
python run.py
```

You don't need to `conda activate canopy-geoai` first — `run.py` finds that
environment's Python directly (via `conda run -n canopy-geoai`), so it can't
accidentally run against the wrong global Python install (this is what
caused the `ModuleNotFoundError: No module named 'pkg_resources'` /
`geemap` import failures earlier — the server was running under an
unrelated global Python 3.14, not the conda env, because `python`/`uvicorn`
on PATH resolved to the wrong one).

This starts the backend (port 8000) and frontend (port 4521) together in one
terminal, with `[backend]`/`[frontend]`-prefixed logs, and stops both on
Ctrl+C. It assumes `npm install` has already been run once in `frontend/`
(see below) — it won't install frontend deps for you.

**One-time setup — Backend, macOS/Linux**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
# docs: http://localhost:8000/docs
```

**One-time setup — Backend, Windows**

`rasterio`/GDAL/`cartopy` (used for index math and the cartographic timelapse
renderer) don't have reliable `pip`-installable wheels on native Windows —
`pip install -r requirements.txt` will fail trying to build `rasterio` from
source (missing GDAL/build tools). Use conda instead (Anaconda/Miniconda):

```powershell
cd backend
conda env create -f environment.yml
conda activate canopy-geoai
copy .env.example .env
python -m uvicorn app.main:app --reload --port 8000
# docs: http://localhost:8000/docs
```

Use `python -m uvicorn ...` (not bare `uvicorn ...`) — it guarantees the
`uvicorn` that's actually on your `PATH` (e.g. from a global Anaconda install)
doesn't get picked up instead of the one in your active environment.

**One-time setup — Frontend**
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
# app: http://localhost:4521, admin: http://localhost:4521/admin
```

After both one-time setups are done, use `python run.py` from the repo root
(see above) instead of running these `npm run dev` / `uvicorn` commands by
hand each time.

## Getting Google Earth Engine access

1. Sign up / register a Cloud project for Earth Engine at
   https://code.earthengine.google.com/register (free for research/government/
   nonprofit use).
2. In that Google Cloud project: enable the **Earth Engine API**, then create a
   **service account** (IAM & Admin → Service Accounts → Create) and grant it
   the "Earth Engine Resource Writer" role (or register it directly at
   https://code.earthengine.google.com/register under "Service account").
3. Create a JSON key for that service account (Keys → Add key → JSON) and
   download it.
4. In `backend/.env`, set:
   - `GEE_SERVICE_ACCOUNT` = the service account's email (looks like
     `canopy-geoai@your-project.iam.gserviceaccount.com`)
   - `GEE_SERVICE_ACCOUNT_KEY_PATH` = path to the downloaded JSON file (local
     dev), **or** `GEE_SERVICE_ACCOUNT_KEY_JSON` = the file's contents pasted
     as one line (needed for Render, since it can't mount a key file)
   - `GEE_PROJECT` = your Google Cloud project ID
5. Restart the backend. Check it worked: `GET http://localhost:8000/api/health`
   should show `"gee_available": true`.

If you'd rather not set this up yet, leave GEE unset: `/api/analysis` will
automatically use the Planetary Computer fallback (no account needed); only
`/api/timelapse` (cartoee-based cartographic rendering) requires GEE for now.

## Admin login

The admin queue at `/admin` uses a single pilot account, set in
`backend/.env` (or `Settings` defaults if unset):

```
ADMIN_USERNAME=canopyceo
ADMIN_PASSWORD=plothy@4578
```

Change these before sharing the app beyond your own testing — it's a single
shared account (MVP-level auth), not per-user login. See
`backend/app/api/routes_admin.py` for the login/session logic.

## Core workflow

1. **Dashboard** (`/`) — pick Sentinel-2 or Landsat (collapsible section), pick
   one or more indexes (collapsible section, sourced from the index catalog —
   see `docs/INDEX_LIBRARY.md`), inspect the Kerala map, generate a timelapse.
2. **Can't self-serve a dataset?** Use "Request it" — submits to the admin queue
   (`POST /api/requests`).
3. **Admin** (`/admin`) — the Canopy technical team reviews the queue, approves
   or rejects, and once the deliverables are generated and validated, **releases**
   them (`POST /api/admin/requests/{id}/release`) — spatial (GeoTIFF/GeoPackage)
   + Excel become downloadable to the requester.
4. **Print** (`/print?src=<frame-url>`) — full-page print/PDF view of a
   cartographic timelapse frame (graticule, north arrow, scale bar, legend).

## Status: MVP scope

This first build is a **deep, working pipeline for Kerala** — Sentinel-2/Landsat
access (both backends), the full index + drought (VCI/TCI/VHI/NDDI) + LULC
change-matrix engine, cartographic timelapse rendering, Excel/spatial report
export, and a local SQLite admin request/approval workflow — with the UI wired
to all of it. Left for the next iteration: a supervised (trained) LULC
classifier in place of the current rule-based thresholds, a precise Kerala
district boundary layer (GADM/Survey of India) in place of the FAO GAUL /
bbox default, background job processing for long-running GEE reductions, and
extending the AOI catalog to other tropical countries. See `docs/DATA_SOURCES.md`.

## Docs

- [`docs/INDEX_LIBRARY.md`](docs/INDEX_LIBRARY.md) — every spectral/drought index implemented, formula + source.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — Render (backend) + Vercel (frontend) deployment steps.
- [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) — Sentinel-2/Landsat collections used, AOI boundary notes, known limitations.
