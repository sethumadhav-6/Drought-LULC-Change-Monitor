"""
Core analysis endpoint: run drought + LULC-change analysis for an AOI
over a pre-monsoon vs post-monsoon window, using GEE if available and
falling back to Planetary Computer otherwise.

This is a thin wrapper around services/analysis.py -- the actual logic
lives there so both this FastAPI route and the Streamlit app
(streamlit_app.py) share exactly one implementation.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.analysis import run_analysis as _run_analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalysisRequest(BaseModel):
    aoi_name: str = Field(default="Kerala")
    data_source: str = Field(default="sentinel-2", pattern="^(sentinel-2|landsat)$")
    pre_start: date
    pre_end: date
    post_start: date
    post_end: date
    indexes: list[str] = Field(default_factory=lambda: ["NDVI", "NDWI", "NDDI"])


class AnalysisResult(BaseModel):
    aoi_name: str
    source_used: str  # "gee" | "planetary-computer"
    stats: dict


@router.post("", response_model=AnalysisResult)
def run_analysis(req: AnalysisRequest):
    try:
        result = _run_analysis(
            aoi_name=req.aoi_name,
            data_source=req.data_source,
            pre_start=req.pre_start,
            pre_end=req.pre_end,
            post_start=req.post_start,
            post_end=req.post_end,
            indexes=req.indexes,
        )
    except ValueError as exc:
        status = 404 if "No cloud-free scenes" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc
    return AnalysisResult(**result)
