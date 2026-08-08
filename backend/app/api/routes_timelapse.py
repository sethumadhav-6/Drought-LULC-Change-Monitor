"""
Timelapse endpoints: generate a print-ready cartographic GIF/MP4
(graticule + north arrow + scale bar + legend) for a chosen index
over a date range, e.g. NDVI or NDDI across pre- vs post-monsoon
composites, or a multi-year sequence for a "how did this dry up"
narrative.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core import gee
from ..services.indexes import INDEX_BY_CODE, S2_BANDS
from ..services.timelapse import build_gif, render_frame_gee

router = APIRouter(prefix="/api/timelapse", tags=["timelapse"])

# Simple diverging palettes tuned per index category; extend as needed.
VIS_PARAMS = {
    "NDVI": {"min": -0.2, "max": 0.9, "palette": ["#a50026", "#ffffbf", "#1a9850"]},
    "NDDI": {"min": -0.5, "max": 0.5, "palette": ["#1a9850", "#ffffbf", "#a50026"]},
    "NDWI": {"min": -0.5, "max": 0.5, "palette": ["#a50026", "#ffffbf", "#3288bd"]},
}


class TimelapseRequest(BaseModel):
    aoi_name: str = "Kerala"
    index_code: str = "NDVI"
    start: date
    end: date
    step_months: int = Field(default=1, ge=1, le=12)
    fps: float = 1.0


@router.post("")
def create_timelapse(req: TimelapseRequest):
    if req.index_code not in INDEX_BY_CODE:
        raise HTTPException(400, f"Unknown index: {req.index_code}")
    if not gee.is_available():
        raise HTTPException(
            503,
            "Timelapse generation currently requires the Google Earth Engine backend "
            "(geemap/cartoee). Configure GEE credentials, or request an admin-generated "
            "dataset instead via /api/requests.",
        )

    ee = gee.ee_module()
    idx_def = INDEX_BY_CODE[req.index_code]
    aoi_name = req.aoi_name.strip()
    if aoi_name.lower() in ("kerala", "kerala (state)"):
        aoi = gee.kerala_boundary()
    else:
        aoi = gee.kerala_districts().filter(ee.Filter.eq("ADM2_NAME", aoi_name))
        if aoi.size().getInfo() == 0:
            raise HTTPException(
                400,
                f"AOI '{aoi_name}' not found among Kerala districts (GEE FAO GAUL names). "
                "Use the exact district name from GET /api/catalog/aoi/kerala, or 'Kerala' for the whole state.",
            )
    geom = aoi.geometry()
    region = geom.bounds().getInfo()["coordinates"]

    from ..core.config import TIMELAPSE_DIR

    frames: list[Path] = []
    run_id = uuid.uuid4().hex[:10]
    out_dir = TIMELAPSE_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cur = req.start
    step = 0
    vis = VIS_PARAMS.get(req.index_code, {"min": -1, "max": 1, "palette": ["#a50026", "#ffffbf", "#1a9850"]})
    legend = {"Low": vis["palette"][0], "Mid": vis["palette"][1], "High": vis["palette"][-1]}

    while cur < req.end:
        nxt = _add_months(cur, req.step_months)
        col = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geom)
            .filterDate(str(cur), str(min(nxt, req.end)))
        )
        img = col.map(lambda i: idx_def.fn(i.divide(10000), S2_BANDS).rename(req.index_code)).median().clip(geom)
        out_png = out_dir / f"frame_{step:03d}.png"
        render_frame_gee(
            img, region, vis, out_png,
            title=f"{req.aoi_name} - {req.index_code} - {cur.isoformat()}",
            legend_dict=legend,
        )
        frames.append(out_png)
        cur = nxt
        step += 1

    if not frames:
        raise HTTPException(400, "Date range produced no frames; widen start/end.")

    gif_path = out_dir / "timelapse.gif"
    build_gif(frames, gif_path, fps=req.fps)
    return {
        "run_id": run_id,
        "frame_count": len(frames),
        "gif_path": str(gif_path),
        "frame_paths": [str(f) for f in frames],
    }


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, 28)
    return date(y, m, day)
