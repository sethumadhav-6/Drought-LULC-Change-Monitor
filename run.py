"""
Single-command dev launcher for Canopy GeoAI.

Starts the FastAPI backend (port 8000) and the Next.js frontend
(port 4521) together, streams both logs to this one terminal with
[backend]/[frontend] prefixes, and shuts both down cleanly on
Ctrl+C.

Usage:
    cd canopy-geoai                  # repo root (where this file lives)
    python run.py

You do NOT need to `conda activate canopy-geoai` first -- this script finds
that environment's interpreter directly (via `conda run -n canopy-geoai`,
or a direct path to its python.exe as a fallback) rather than trusting
whatever `python`/`uvicorn` happens to resolve to on PATH. That's a
deliberate fix: on Windows it's very easy to have a second, unrelated
Python install (e.g. a Microsoft Store or user-site install) shadow the
conda one on PATH, silently running the backend against the wrong
interpreter -- with confusing partial-failure symptoms (some packages
"installed", others mysteriously missing).

Frontend deps must already be installed once via `npm install` in
frontend/ -- this script doesn't run npm install for you (that's a
slow, one-time step, not something you want on every launch).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT, "backend")
FRONTEND_DIR = os.path.join(ROOT, "frontend")
CONDA_ENV_NAME = "canopy-geoai"


def stream(pipe, prefix):
    for line in iter(pipe.readline, ""):
        if line:
            print(f"[{prefix}] {line.rstrip()}", flush=True)
    pipe.close()


def npm_cmd():
    # On Windows, npm is npm.cmd; shutil.which finds it on PATH either way.
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def backend_command():
    """
    Resolve the backend launch command so it always runs inside the
    `canopy-geoai` conda env, regardless of what `python`/`uvicorn` on
    PATH would otherwise resolve to.
    """
    conda_exe = shutil.which("conda")
    if conda_exe:
        return [
            conda_exe, "run", "--no-capture-output", "-n", CONDA_ENV_NAME,
            "python", "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000",
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
            return [path, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"]

    print(
        f"[run] Could not find `conda` on PATH or the '{CONDA_ENV_NAME}' env's "
        f"python.exe in the usual locations. Falling back to `{sys.executable}` "
        f"-- if this is not your conda env's interpreter, the backend will fail "
        f"the same way it did before (wrong/incomplete package set).",
        flush=True,
    )
    return [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"]


def main():
    if not os.path.isdir(os.path.join(FRONTEND_DIR, "node_modules")):
        print(
            "[run] frontend/node_modules not found -- run `npm install` in "
            "frontend/ once before using this launcher.",
            flush=True,
        )
        sys.exit(1)

    backend_proc = subprocess.Popen(
        backend_command(),
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    frontend_proc = subprocess.Popen(
        [npm_cmd(), "run", "dev"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        shell=(os.name == "nt"),
    )

    threads = [
        threading.Thread(target=stream, args=(backend_proc.stdout, "backend"), daemon=True),
        threading.Thread(target=stream, args=(frontend_proc.stdout, "frontend"), daemon=True),
    ]
    for t in threads:
        t.start()

    print("[run] backend:  http://localhost:8000  (docs at /docs)", flush=True)
    print("[run] frontend: http://localhost:4521", flush=True)
    print("[run] Ctrl+C to stop both.", flush=True)

    try:
        while True:
            if backend_proc.poll() is not None:
                print(f"[run] backend exited ({backend_proc.returncode}) -- stopping frontend too.", flush=True)
                break
            if frontend_proc.poll() is not None:
                print(f"[run] frontend exited ({frontend_proc.returncode}) -- stopping backend too.", flush=True)
                break
            threading.Event().wait(0.5)
    except KeyboardInterrupt:
        print("\n[run] stopping...", flush=True)
    finally:
        for proc in (backend_proc, frontend_proc):
            if proc.poll() is None:
                proc.terminate()
        for proc in (backend_proc, frontend_proc):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
