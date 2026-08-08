"""
Single-command launcher for Canopy GeoAI (Flask app).

Usage:
    cd canopy-geoai                  # repo root (where this file lives)
    python run.py

You do NOT need to `conda activate canopy-geoai` first -- this script
finds that environment's interpreter directly (via `conda run -n
canopy-geoai`, or a direct path to its python.exe as a fallback)
rather than trusting whatever `python` happens to resolve to on PATH.
That's a deliberate fix: on Windows it's very easy to have a second,
unrelated Python install (e.g. a Microsoft Store or user-site install)
shadow the conda one on PATH, silently running the app against the
wrong interpreter -- with confusing partial-failure symptoms (some
packages "installed", others mysteriously missing).

This starts ONE process: the Flask app (backend/flask_app.py), which
serves the whole UI (dashboard + admin queue) at
http://localhost:5000, backed by MySQL. There's no separate frontend
server, no CORS, and no second port to manage. See docs/DEPLOYMENT.md
for the superseded Streamlit and Next.js/FastAPI options, kept in the
repo but no longer the primary path.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT, "backend")
CONDA_ENV_NAME = "canopy-geoai"


def flask_command():
    """
    Resolve the launch command so it always runs inside the
    `canopy-geoai` conda env, regardless of what `python` on PATH
    would otherwise resolve to.
    """
    conda_exe = shutil.which("conda")
    if conda_exe:
        return [
            conda_exe, "run", "--no-capture-output", "-n", CONDA_ENV_NAME,
            "python", "flask_app.py",
        ]

    # Fallback: look for the env's python.exe directly under common conda
    # install locations, in case `conda` itself isn't on PATH in this shell.
    candidates = []
    for base_env_var in ("CONDA_ROOT", "USERPROFILE"):
        base = os.environ.get(base_env_var)
        if not base:
            continue
        candidates += [
            os.path.join(base, "envs", CONDA_ENV_NAME, "python.exe"),
            os.path.join(base, "Anaconda3", "envs", CONDA_ENV_NAME, "python.exe"),
            os.path.join(base, "miniconda3", "envs", CONDA_ENV_NAME, "python.exe"),
        ]
    for path in candidates:
        if os.path.isfile(path):
            return [path, "flask_app.py"]

    print(
        f"[run] Could not find `conda` on PATH or the '{CONDA_ENV_NAME}' env's "
        f"python.exe in the usual locations. Falling back to `{sys.executable}` "
        f"-- if this is not your conda env's interpreter, the app may fail "
        f"the same way it did before (wrong/incomplete package set).",
        flush=True,
    )
    return [sys.executable, "flask_app.py"]


def main():
    print("[run] Canopy GeoAI: http://localhost:5000", flush=True)
    print("[run] Ctrl+C to stop.", flush=True)
    try:
        subprocess.run(flask_command(), cwd=BACKEND_DIR, check=False)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
