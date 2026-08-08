# Deployment

## Backend → Render

1. Push `canopy-geoai/` to a Git repo (GitHub/GitLab).
2. In Render: **New +** → **Blueprint**, point it at the repo, select
   `backend/render.yaml`.
3. Set the secret env vars Render will prompt for (marked `sync: false` in
   `render.yaml`): `GEE_SERVICE_ACCOUNT`, `GEE_SERVICE_ACCOUNT_KEY_JSON`,
   `GEE_PROJECT`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
4. Update `ALLOWED_ORIGINS` to your deployed Vercel URL once you have it, e.g.
   `["https://canopy-geoai.vercel.app"]`.
5. `render.yaml` attaches a 10 GB persistent disk at `/var/data/canopy` for
   `data_store/` (generated timelapses/reports/spatial exports + the SQLite
   admin DB) — without this, Render's ephemeral filesystem would lose
   generated datasets on every redeploy.
6. First deploy will be slow (GDAL/cartopy build) — subsequent deploys reuse
   the Docker layer cache.

## Frontend → Vercel

1. Import the repo in Vercel, set **Root Directory** to `frontend`.
2. Framework preset: Next.js (auto-detected).
3. Add env var `NEXT_PUBLIC_API_BASE_URL` = your Render backend URL
   (e.g. `https://canopy-geoai-backend.onrender.com`).
4. Deploy. `frontend/vercel.json` is already configured for the build command
   and framework.

## Local end-to-end check

```bash
# terminal 1
cd backend && uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend && npm run dev
# visit http://localhost:4521 -- confirm /api/health shows gee_available
# and the Indexes section populates from the running backend.
```

## Known gaps to close before production rollout

- **Auth**: the admin workflow uses a single shared username/password
  (`ADMIN_USERNAME` / `ADMIN_PASSWORD`) and in-memory sessions. Fine for a
  pilot with one reviewing team on a single backend instance; replace with
  real accounts/roles (and a shared session store, e.g. Redis) before
  running multiple backend workers or opening this to multiple agencies.
- **Background jobs**: `/api/analysis` and `/api/timelapse` run synchronously
  and can take tens of seconds for state-wide GEE reductions. Move to a task
  queue (Celery/RQ + Redis) once usage grows past a handful of concurrent
  requests.
- **LULC classifier**: currently rule-based thresholds (fast, explainable, no
  training data needed) rather than a trained classifier. Swap in
  `ee.Classifier.smileRandomForest` once labelled Kerala training points exist
  (see `services/lulc.py` docstring).
- **AOI precision**: Kerala boundary comes from FAO GAUL (GEE path) or a state
  bounding box (Planetary Computer path). For district-level precision, load a
  GADM or Survey of India boundary asset instead.
