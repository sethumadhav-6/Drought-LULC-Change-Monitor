"""
Core drought/LULC-index analysis: run a pre- vs post-monsoon comparison
for an AOI, using GEE if available and falling back to Planetary
Computer otherwise.

Framework-agnostic on purpose -- both the FastAPI route
(api/routes_analysis.py) and the Streamlit app (streamlit_app.py) call
these functions directly, so there is exactly one implementation of
the actual analysis logic to maintain and debug.
"""
from __future__ import annotations

from datetime import date

from ..core import aoi as aoi_module
from ..core import gee
from .drought import drought_summary, land_stress_index
from .geo_utils import flatten_bounds_ring, render_scale_for_region
from .indexes import INDEX_BY_CODE, S2_BANDS, default_vis_params

# Kerala state bounding box (lon_min, lat_min, lon_max, lat_max) -- used only
# as a last-resort fallback if the Kerala shapefile (core/aoi.py) isn't
# present. See docs/DATA_SOURCES.md.
KERALA_BBOX = (74.86, 8.29, 77.42, 12.82)


def run_analysis(
    aoi_name: str,
    data_source: str,
    pre_start: date,
    pre_end: date,
    post_start: date,
    post_end: date,
    indexes: list[str],
) -> dict:
    """
    Returns {"aoi_name", "source_used", "stats"}. Raises ValueError on
    bad input (unknown index code, AOI not found, no imagery found) --
    callers translate that to whatever error format their UI needs
    (HTTPException for FastAPI, st.error for Streamlit).
    """
    unknown = [c for c in indexes if c not in INDEX_BY_CODE]
    if unknown:
        raise ValueError(f"Unknown index code(s): {unknown}")

    if gee.is_available():
        return _run_gee(aoi_name, pre_start, pre_end, post_start, post_end, indexes)
    return _run_planetary_computer(aoi_name, data_source, pre_start, pre_end, post_start, post_end, indexes)


def _run_gee(aoi_name, pre_start, pre_end, post_start, post_end, indexes) -> dict:
    ee = gee.ee_module()
    aoi = gee.kerala_boundary() if aoi_name.lower() == "kerala" else gee.kerala_districts().filter(
        ee.Filter.eq("ADM2_NAME", aoi_name)
    )
    geom = aoi.geometry()

    collection_id = "COPERNICUS/S2_SR_HARMONIZED"
    pre = ee.ImageCollection(collection_id).filterBounds(geom).filterDate(str(pre_start), str(pre_end))
    post = ee.ImageCollection(collection_id).filterBounds(geom).filterDate(str(post_start), str(post_end))

    # Flat [south, west, north, east] bbox for the frontend to fit/pan the
    # Leaflet map to.
    west, south, east, north = flatten_bounds_ring(geom.bounds().getInfo()["coordinates"][0])
    bounds = [south, west, north, east]

    # Same reproject-to-safe-scale fix used in timelapse.py/webgis_publish.py:
    # without this, the live Map Layers tiles for a whole-state (or large
    # district) AOI compute at native ~10m resolution per tile, which is
    # slow and can silently fail (Leaflet just shows blank/missing tiles,
    # no visible error) for the same "Earth Engine memory capacity
    # exceeded" reason getThumbUrl hits without it. This is almost
    # certainly why layers rendered fine in the published static export
    # (which already reprojects) but not in the live checkbox layers here.
    render_scale = render_scale_for_region([west, south, east, north])

    stats = {}
    for code in indexes:
        idx_def = INDEX_BY_CODE[code]
        pre_img = (
            pre.map(lambda img: idx_def.fn(img.divide(10000), S2_BANDS).rename(code))
            .median().clip(geom).reproject(crs="EPSG:4326", scale=render_scale)
        )
        post_img = (
            post.map(lambda img: idx_def.fn(img.divide(10000), S2_BANDS).rename(code))
            .median().clip(geom).reproject(crs="EPSG:4326", scale=render_scale)
        )

        # scale matches render_scale (not a fixed 100m) since pre_img/post_img
        # are already reprojected to that resolution above -- requesting a
        # finer reduceRegion scale than the image actually has wastes
        # computation without adding precision.
        pre_mean = pre_img.reduceRegion(ee.Reducer.mean(), geom, scale=render_scale, maxPixels=1e10, bestEffort=True).get(code)
        post_mean = post_img.reduceRegion(ee.Reducer.mean(), geom, scale=render_scale, maxPixels=1e10, bestEffort=True).get(code)

        # Map-layer tile URLs so the frontend can drop these straight onto
        # the Leaflet map as a normal XYZ layer (standard geemap/leafmap
        # technique -- no export/download needed, GEE serves the tiles
        # directly). Wrapped in try/except: a getMapId() failure (e.g. a
        # transient GEE error) shouldn't take down the whole analysis when
        # the numeric stats are the more important result.
        vis = default_vis_params(idx_def)
        pre_tile_url = post_tile_url = None
        try:
            pre_tile_url = pre_img.getMapId(vis)["tile_fetcher"].url_format
            post_tile_url = post_img.getMapId(vis)["tile_fetcher"].url_format
        except Exception:  # noqa: BLE001
            pass

        stats[code] = {
            "pre_mean": pre_mean.getInfo() if pre_mean is not None else None,
            "post_mean": post_mean.getInfo() if post_mean is not None else None,
            "pre_tile_url": pre_tile_url,
            "post_tile_url": post_tile_url,
            "vis": vis,
        }

    if "NDVI" in stats and "NDWI" in stats:
        stats["drought_summary"] = drought_summary(stats["NDVI"]["post_mean"] or 0, stats.get("NDWI", {}).get("post_mean") or 0)

    # Weighted NDVI+NDBI land-stress score, computed for both windows when
    # both indexes were requested -- see drought.py::land_stress_index for
    # why this replaces a LULC classification here.
    if "NDVI" in stats and "NDBI" in stats:
        stats["land_stress"] = {
            "pre": land_stress_index(stats["NDVI"]["pre_mean"] or 0, stats["NDBI"]["pre_mean"] or 0),
            "post": land_stress_index(stats["NDVI"]["post_mean"] or 0, stats["NDBI"]["post_mean"] or 0),
        }

    return {"aoi_name": aoi_name, "source_used": "gee", "stats": stats, "bounds": bounds}


def get_layer_tile(
    aoi_name: str,
    index_code: str,
    period: str,
    pre_start: date,
    pre_end: date,
    post_start: date,
    post_end: date,
    vis: dict,
) -> str:
    """
    Recompute a single Pre or Post composite for one index with
    caller-supplied visualization params (palette / min / max) and return
    a fresh GEE tile URL. Backs the dashboard's colormap/min-max
    customization controls on an already-run analysis -- cheap to
    recompute (same median-composite logic as _run_gee, just for one
    index/one period) rather than trying to cache ee.Image objects
    server-side between requests.
    """
    if not gee.is_available():
        raise ValueError("Custom layer rendering requires the Google Earth Engine backend.")
    if index_code not in INDEX_BY_CODE:
        raise ValueError(f"Unknown index: {index_code}")
    if period not in ("pre", "post"):
        raise ValueError("period must be 'pre' or 'post'")

    ee = gee.ee_module()
    idx_def = INDEX_BY_CODE[index_code]
    aoi = gee.kerala_boundary() if aoi_name.lower() == "kerala" else gee.kerala_districts().filter(
        ee.Filter.eq("ADM2_NAME", aoi_name)
    )
    geom = aoi.geometry()
    start, end = (pre_start, pre_end) if period == "pre" else (post_start, post_end)

    col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geom).filterDate(str(start), str(end))
    img = col.map(lambda i: idx_def.fn(i.divide(10000), S2_BANDS).rename(index_code)).median().clip(geom)
    try:
        return img.getMapId(vis)["tile_fetcher"].url_format
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not render this layer with the chosen settings: {exc}") from exc


def _run_planetary_computer(aoi_name, data_source, pre_start, pre_end, post_start, post_end, indexes) -> dict:
    from ..core.stac_pc import search_items, stack_bands

    bbox = aoi_module.resolve_bbox(aoi_name, fallback=KERALA_BBOX)
    pre_items = search_items(bbox, pre_start, pre_end, data_source)
    post_items = search_items(bbox, post_start, post_end, data_source)
    if not pre_items or not post_items:
        raise ValueError(
            "No cloud-free scenes found for the requested window on the Planetary Computer catalog. "
            "Try widening the date range or lowering the cloud-cover threshold."
        )

    bands_needed = sorted({b for c in indexes for b in INDEX_BY_CODE[c].bands} | {"red", "green", "blue", "nir"})
    pre_stack = stack_bands(pre_items[0], bands_needed, collection=data_source)
    post_stack = stack_bands(post_items[0], bands_needed, collection=data_source)

    stats = {}
    for code in indexes:
        idx_def = INDEX_BY_CODE[code]
        pre_val = idx_def.fn(pre_stack, {b: b for b in bands_needed})
        post_val = idx_def.fn(post_stack, {b: b for b in bands_needed})
        stats[code] = {
            "pre_mean": float(pre_val.mean().values),
            "post_mean": float(post_val.mean().values),
        }

    if "NDVI" in stats and "NDWI" in stats:
        stats["drought_summary"] = drought_summary(stats["NDVI"]["post_mean"], stats["NDWI"]["post_mean"])

    if "NDVI" in stats and "NDBI" in stats:
        stats["land_stress"] = {
            "pre": land_stress_index(stats["NDVI"]["pre_mean"], stats["NDBI"]["pre_mean"]),
            "post": land_stress_index(stats["NDVI"]["post_mean"], stats["NDBI"]["post_mean"]),
        }

    # bbox is (west, south, east, north); normalize to the same
    # [south, west, north, east] shape the GEE path returns. No tile_url
    # here -- GEE's getMapId() tile server isn't available on this path,
    # since there's no hosted tile pyramid for an ad-hoc xarray computation.
    # The frontend should skip map-layer checkboxes when tile_url is absent.
    west, south, east, north = bbox
    return {
        "aoi_name": aoi_name, "source_used": "planetary-computer", "stats": stats,
        "bounds": [south, west, north, east],
    }
