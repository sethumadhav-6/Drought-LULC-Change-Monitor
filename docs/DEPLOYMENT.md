# Deployment

## Hosting the Flask app on your own server (primary path)

This assumes a Linux server (Ubuntu/Debian) you control via SSH. On Linux,
`pip install -r requirements.txt` inside a plain venv should work directly —
GDAL/rasterio/cartopy have proper prebuilt wheels for Linux, so you don't
need conda here the way the Windows dev setup does. You do need a couple of
system packages first (GDAL's C library, which the Python `gdal`/`rasterio`
wheels link against) plus a MySQL server.

**1. System packages**
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip gdal-bin libgdal-dev libgeos-dev libproj-dev ffmpeg
```

If MySQL isn't already running on this server (or a server you can reach):
```bash
sudo apt install -y mysql-server
sudo mysql -e "CREATE DATABASE canopy_geoai; CREATE USER 'canopy'@'localhost' IDENTIFIED BY 'change-me'; GRANT ALL ON canopy_geoai.* TO 'canopy'@'localhost';"
```

**2. Get the code and install**
```bash
git clone <your-repo-url> canopy-geoai
cd canopy-geoai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: set your GEE credentials (see README.md), `ADMIN_USERNAME`/
`ADMIN_PASSWORD`, `FLASK_SECRET_KEY` (long random string), your `MYSQL_*`
credentials, and `DATA_STORE_DIR` if you want it somewhere other than the
default `../data_store`. If you have a Kerala shapefile, place it at
`data_store/shapefiles/kerala_districts.shp` (with its `.dbf`/`.shx`/`.prj`
siblings) — see `docs/DATA_SOURCES.md`. The app creates its one MySQL table
(`dataset_requests`) automatically on first run — no manual migration step.

**3. Run it with gunicorn as a systemd service** (so it survives
reboots/SSH disconnects)

Create `/etc/systemd/system/canopy-geoai.service`:
```ini
[Unit]
Description=Canopy GeoAI (Flask)
After=network.target mysql.service

[Service]
Type=simple
User=<your-linux-user>
WorkingDirectory=/path/to/canopy-geoai/backend
Environment="PATH=/path/to/canopy-geoai/backend/.venv/bin"
ExecStart=/path/to/canopy-geoai/backend/.venv/bin/gunicorn flask_app:app --bind 0.0.0.0:5000 --workers 2 --timeout 300
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`--timeout 300` matters here: Timelapse generation can legitimately take a
couple of minutes for a multi-year run, and gunicorn's default 30s worker
timeout would kill the request mid-render. `--workers 2` gives you one
worker to keep serving the dashboard while another is busy with a long
Analysis/Timelapse job — bump it if you expect more concurrent users, but
each worker holds its own GEE session so don't go overboard on a small box.

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now canopy-geoai
sudo systemctl status canopy-geoai   # confirm it's running
```

The app is now reachable at `http://<your-server-ip>:5000`.

**4. Optional: put it behind nginx with a domain + HTTPS**

```nginx
server {
    listen 80;
    server_name geoai.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 50M;
    }
}
```
(No WebSocket-upgrade headers needed here — unlike the old Streamlit setup,
Flask is plain request/response, which is part of why this is the simpler
and faster stack to host.) Then run `sudo certbot --nginx -d
geoai.yourdomain.com` for a free HTTPS cert (Certbot / Let's Encrypt).

**5. Redeploying after code changes**
```bash
cd canopy-geoai
git pull
cd backend && source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart canopy-geoai
```

### If your server is Windows Server instead

Same conda-based setup as the local Windows dev instructions in README.md
applies (`conda env create -f environment.yml`), just run it as a persistent
service instead of a foreground terminal — e.g. via NSSM (Non-Sucking Service
Manager) wrapping `conda run -n canopy-geoai python flask_app.py`, or Task
Scheduler set to run at startup. For real production use on Windows Server,
`waitress` (a pure-Python WSGI server) is a more common choice than gunicorn,
which doesn't support Windows: `pip install waitress`, then `waitress-serve
--host 0.0.0.0 --port 5000 flask_app:app`.

## Superseded: Streamlit self-hosting

The Streamlit app (`backend/streamlit_app.py`) still runs the same way it
did before this pivot to Flask — `streamlit run streamlit_app.py
--server.port 8501 --server.address 0.0.0.0`, put behind nginx with
WebSocket-upgrade headers if you want a domain. Moved off this primarily
because Streamlit's own runtime (a persistent WebSocket connection re-running
the whole script on each interaction) adds overhead a plain request/response
Flask app doesn't have, which matters more once this is hosted for real
users rather than run locally.

## Legacy stack: Render (backend) + Vercel (frontend)

Kept working, but no longer the primary path — see README.md's "Superseded
stacks" section for why. Use this if you specifically want the Next.js UI
hosted on Vercel.

### Backend → Render

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
7. Render's free/starter tiers cost money past the free trial — this is the
   main reason the self-hosted Flask path above exists as an alternative.

### Frontend → Vercel

1. Import the repo in Vercel, set **Root Directory** to `frontend`.
2. Framework preset: Next.js (auto-detected).
3. Add env var `NEXT_PUBLIC_API_BASE_URL` = your Render backend URL
   (e.g. `https://canopy-geoai-backend.onrender.com`).
4. Deploy. `frontend/vercel.json` is already configured for the build command
   and framework.

### Local end-to-end check (legacy stack)

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
  (`ADMIN_USERNAME` / `ADMIN_PASSWORD`) with a signed session cookie
  (`FLASK_SECRET_KEY`). Fine for a pilot with one reviewing team; replace
  with real accounts/roles before opening this to multiple agencies.
- **Long-running operations**: Analysis and Timelapse generation run
  synchronously in the Flask request (blocking that user's session while it
  runs) and can take tens of seconds to minutes for state-wide GEE
  reductions / multi-year timelapses — this is why the gunicorn `--timeout`
  above is set high. Fine for a handful of concurrent users; move to a
  background task queue (e.g. Celery/RQ) if usage grows.
- **LULC classifier**: currently rule-based thresholds (fast, explainable, no
  training data needed) rather than a trained classifier, and not yet wired
  into the Flask UI (the engine exists in `services/lulc.py`). Swap in
  `ee.Classifier.smileRandomForest` once labelled Kerala training points
  exist.
- **AOI precision**: the Planetary Computer path uses your Kerala shapefile
  when present (`data_store/shapefiles/kerala_districts.shp`); the GEE path
  still uses FAO GAUL boundaries unless you upload that shapefile as an
  Earth Engine asset (see `docs/DATA_SOURCES.md`).
- **MySQL connection resilience**: `pool_pre_ping` is enabled so stale
  connections (e.g. after a MySQL restart or idle timeout) get transparently
  reconnected, but there's no retry/backoff around initial connection at
  startup — if MySQL isn't reachable when the app starts, it'll fail fast
  rather than wait and retry.
