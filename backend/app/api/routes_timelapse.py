"""
Timelapse endpoints: generate a print-ready cartographic GIF/MP4
(graticule + north arrow + scale bar + legend) for a chosen index
over a date range, e.g. NDVI or NDDI across pre- vs post-monsoon
composites, or a multi-year sequence for a "how did this dry up"
narrative.

Thin wrapper around services/timelapse.py::generate_timelapse -- the
actual GEE + rendering logic lives there so both this FastAPI route
and the Streamlit app share exactly one implementation.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.timelapse import generate_timelapse

router = APIRouter(prefix="/api/timelapse", tags=["timelapse"])


class TimelapseRequest(BaseModel):
    aoi_name: str = "Kerala"
    index_code: str = "NDVI"
    start: date
    end: date
    step_months: int = Field(default=1, ge=1, le=12)
    fps: float = 1.0


@router.post("")
def create_timelapse(req: TimelapseRequest):
    try:
        result = generate_timelapse(
            aoi_name=req.aoi_name,
            index_code=req.index_code,
            start=req.start,
            end=req.end,
            step_months=req.step_months,
            fps=req.fps,
        )
    except ValueError as exc:
        status = 503 if "requires the Google Earth Engine" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc

    return {
        "run_id": result["run_id"],
        "frame_count": result["frame_count"],
        "gif_path": str(result["gif_path"]),
        "frame_paths": [str(f) for f in result["frame_paths"]],
    }
