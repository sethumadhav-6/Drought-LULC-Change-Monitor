"""
Core analysis endpoint: run drought + LULC-change analysis for an AOI
over a pre-monsoon vs post-monsoon window, using GEE if available and
falling back to Planetary Computer otherwise.

This wires together services/indexes.py, services/drought.py, and
services/lulc.py. Kept intentionally synchronous/simple for the MVP;
move to a background task queue (Celery/RQ) once real usage picks up,
since a full-state GEE reduction can take tens of seconds.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core import aoi as aoi_module
from ..core import gee
from ..services.drought import compute_vci_series, drought_summary
from ..services.indexes import INDEX_BY_CODE, S2_BANDS
from .routes_catalog import KERALA_BBOX, KERALA_DISTRICTS

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
    unknown = [c for c in req.indexes if c not in INDEX_BY_CODE]
    if unknown:
        raise HTTPException(400, f"Unknown index code(s): {unknown}")

    if gee.is_available():
        return _run_gee(req)
    return _run_planetary_computer(req)


def _run_gee(req: AnalysisRequest) -> AnalysisResult:
    ee = gee.ee_module()
    aoi = gee.kerala_boundary() if req.aoi_name.lower() == "kerala" else gee.kerala_districts().filter(
        ee.Filter.eq("ADM2_NAME", req.aoi_name)
    )
    geom = aoi.geometry()

    collection_id = "COPERNICUS/S2_SR_HARMONIZED"
    pre = ee.ImageCollection(collection_id).filterBounds(geom).filterDate(str(req.pre_start), str(req.pre_end))
    post = ee.ImageCollection(collection_id).filterBounds(geom).filterDate(str(req.post_start), str(req.post_end))

    stats = {}
    for code in req.indexes:
        idx_def = INDEX_BY_CODE[code]
        pre_img = pre.map(lambda img: idx_def.fn(img.divide(10000), S2_BANDS).rename(code)).median().clip(geom)
        post_img = post.map(lambda img: idx_def.fn(img.divide(10000), S2_BANDS).rename(code)).median().clip(geom)

        pre_mean = pre_img.reduceRegion(ee.Reducer.mean(), geom, scale=100, maxPixels=1e10, bestEffort=True).get(code)
        post_mean = post_img.reduceRegion(ee.Reducer.mean(), geom, scale=100, maxPixels=1e10, bestEffort=True).get(code)
        stats[code] = {
            "pre_mean": pre_mean.getInfo() if pre_mean is not None else None,
            "post_mean": post_mean.getInfo() if post_mean is not None else None,
        }

    if "NDVI" in stats and "NDWI" in stats:
        drought = drought_summary(stats["NDVI"]["post_mean"] or 0, stats.get("NDWI", {}).get("post_mean") or 0)
        stats["drought_summary"] = drought

    return AnalysisResult(aoi_name=req.aoi_name, source_used="gee", stats=stats)


def _run_planetary_computer(req: AnalysisRequest) -> AnalysisResult:
    from ..core.stac_pc import search_items, stack_bands
    from ..services import indexes as idx_mod

    # Uses the real district/state bbox from the Kerala shapefile (core/aoi.py)
    # when available, falling back to the coarse state bounding box otherwise.
    bbox = aoi_module.resolve_bbox(req.aoi_name, fallback=KERALA_BBOX)
    pre_items = search_items(bbox, req.pre_start, req.pre_end, req.data_source)
    post_items = search_items(bbox, req.post_start, req.post_end, req.data_source)
    if not pre_items or not post_items:
        raise HTTPException(
            404,
            "No cloud-free scenes found for the requested window on the Planetary Computer catalog. "
            "Try widening the date range or lowering the cloud-cover threshold.",
        )

    bands_needed = sorted({b for c in req.indexes for b in INDEX_BY_CODE[c].bands} | {"red", "green", "blue", "nir"})
    pre_stack = stack_bands(pre_items[0], bands_needed, collection=req.data_source)
    post_stack = stack_bands(post_items[0], bands_needed, collection=req.data_source)

    stats = {}
    for code in req.indexes:
        idx_def = INDEX_BY_CODE[code]
        pre_val = idx_def.fn(pre_stack, {b: b for b in bands_needed})
        post_val = idx_def.fn(post_stack, {b: b for b in bands_needed})
        stats[code] = {
            "pre_mean": float(pre_val.mean().values),
            "post_mean": float(post_val.mean().values),
        }

    if "NDVI" in stats and "NDWI" in stats:
        stats["drought_summary"] = drought_summary(stats["NDVI"]["post_mean"], stats["NDWI"]["post_mean"])

    return AnalysisResult(aoi_name=req.aoi_name, source_used="planetary-computer", stats=stats)
