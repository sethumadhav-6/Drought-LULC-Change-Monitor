"""
Shared geometry helpers for the GEE-backed services (analysis.py,
timelapse.py, webgis_publish.py) -- factored out so the two GEE quirks
these functions work around (nested bounds rings, and Earth Engine's
memory limit on large-AOI thumbnail/tile requests) are fixed in exactly
one place instead of being re-derived independently in each service.
"""
from __future__ import annotations

import math


def flatten_bounds_ring(bounds_ring: list) -> list[float]:
    """
    `geom.bounds().getInfo()["coordinates"][0]` returns a closed 5-point
    polygon ring (`[[w,s],[w,n],[e,n],[e,s],[w,s]]`), not a flat bbox --
    but several GEE calls that take a `region` (cartoee.get_map,
    ee.Geometry.Rectangle inside cartoee.add_layer) need a flat
    `[west, south, east, north]` list instead. Passing the ring straight
    through raises `ee.ee_exception.EEException: Invalid geometry.`
    """
    lons = [pt[0] for pt in bounds_ring]
    lats = [pt[1] for pt in bounds_ring]
    return [min(lons), min(lats), max(lons), max(lats)]


def render_scale_for_region(region: list[float], dims: int = 900) -> float:
    """
    Pick a `.reproject()` scale (meters/pixel) that roughly matches `dims`
    pixels across the region's extent, so a GEE thumbnail/tile request
    doesn't try to evaluate a median composite at native ~10m Sentinel-2
    resolution across the *entire* AOI before downsampling -- which
    reliably fails with `EEException: Earth Engine memory capacity
    exceeded` (HTTP 503) for anything AOI-sized (a district, let alone the
    whole state). Clamped to a sane 20-500m range.
    """
    west, south, east, north = region
    mean_lat_rad = math.radians((south + north) / 2)
    width_km = (east - west) * 111.32 * math.cos(mean_lat_rad)
    height_km = (north - south) * 110.57
    extent_km = max(width_km, height_km, 1.0)
    return max(20, min(500, (extent_km * 1000) / dims))
