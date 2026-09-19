"""
Ancillary layers for Kerala: DEM (raster) + soil / drainage /
geomorphology / geology (vector shapefiles, State Land Use Board /
Bhuvan-style datasets).

Same "graceful when absent" pattern as core/aoi.py's Kerala districts
shapefile loader: every function here returns None/False/[] if the
configured path isn't set or doesn't exist, so the rest of the app never
has to special-case "ancillary data not loaded yet". Verified against the
actual files in data_store/ (see docs/ANCILLARY_DATA.md):

    dem            data_store/dem/kl_dem.tif           EPSG:4326, ~30m, int16, nodata -32768
    soil           data_store/shapefiles/soil.shp       EPSG:32643 (UTM 43N), polygons
    drainage       data_store/shapefiles/drainage.shp   EPSG:32643, lines
    geomorphology  data_store/shapefiles/geomorphology.shp  EPSG:32643, polygons
    geology        data_store/shapefiles/geology.shp    EPSG:32643, polygons

Vector layers get reprojected to EPSG:4326 on load (same as
core/aoi.py's Kerala districts shapefile) so they line up with
everything else in the app (GEE geometries, Leaflet, the DEM itself).

NOT yet wired into the drought/land-stress analysis math (services/
drought.py::land_stress_index) -- what's here is loading + AOI-level
summary/zonal-stats helpers. Deciding exactly how slope, soil drainage
class, geomorphology unit, and rock type should factor into a
vulnerability score is a methodology call worth making deliberately
rather than guessing at silently.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .config import get_settings

_VECTOR_LAYER_SETTINGS_ATTR = {
    "soil": "soil_shapefile_path",
    "drainage": "drainage_shapefile_path",
    "geomorphology": "geomorphology_shapefile_path",
    "geology": "geology_shapefile_path",
}

# The categorical column most useful for a quick "what's here" summary per
# layer -- not necessarily the only interesting column (see the full
# schemas in docs/ANCILLARY_DATA.md), just a sensible default. ORDER_ for
# drainage is Strahler-ish stream order -- there isn't a natural
# "category" for a line network the way there is for the polygon layers,
# but stream order is a reasonable stand-in.
_SUMMARY_COLUMN = {
    "soil": "DRAINAGE",
    "geomorphology": "DISCR_L1",
    "geology": "ROCK_GROUP",
    "drainage": "ORDER_",
}


# --------------------------------------------------------------------- #
# DEM (raster)
# --------------------------------------------------------------------- #
def dem_is_available() -> bool:
    return _dem_path() is not None


def _dem_path() -> Path | None:
    settings = get_settings()
    if not settings.dem_path:
        return None
    path = Path(settings.dem_path)
    return path if path.exists() else None


@lru_cache
def _dem_dataset():
    import rasterio

    path = _dem_path()
    if path is None:
        return None
    return rasterio.open(path)


def dem_dataset():
    """Open rasterio dataset for the DEM, or None if not configured."""
    return _dem_dataset()


def elevation_stats(bbox: tuple[float, float, float, float] | None = None) -> dict | None:
    """
    Min/max/mean elevation (meters) over `bbox` (west, south, east, north,
    EPSG:4326), or over the whole DEM if bbox is None. Returns None if the
    DEM isn't configured. Uses a windowed read so this stays cheap even
    for a whole-state bbox against a ~150MB raster.
    """
    import numpy as np
    import rasterio.windows

    ds = dem_dataset()
    if ds is None:
        return None

    if bbox is not None:
        west, south, east, north = bbox
        window = rasterio.windows.from_bounds(west, south, east, north, transform=ds.transform)
        data = ds.read(1, window=window, boundless=True, fill_value=ds.nodata)
    else:
        data = ds.read(1)

    valid = data[data != (ds.nodata if ds.nodata is not None else -32768)]
    if valid.size == 0:
        return None
    return {
        "min_m": float(np.min(valid)),
        "max_m": float(np.max(valid)),
        "mean_m": float(np.mean(valid)),
        "pixel_count": int(valid.size),
    }


# --------------------------------------------------------------------- #
# Vector layers (soil / drainage / geomorphology / geology)
# --------------------------------------------------------------------- #
def vector_layer_names() -> list[str]:
    return list(_VECTOR_LAYER_SETTINGS_ATTR)


def is_available(layer: str) -> bool:
    if layer == "dem":
        return dem_is_available()
    if layer not in _VECTOR_LAYER_SETTINGS_ATTR:
        raise ValueError(f"Unknown ancillary layer '{layer}' -- expected 'dem' or one of {vector_layer_names()}")
    return _vector_path(layer) is not None


def availability() -> dict:
    """{'dem': bool, 'soil': bool, 'drainage': bool, 'geomorphology': bool,
    'geology': bool} -- for a status endpoint/UI indicator."""
    return {"dem": dem_is_available(), **{layer: is_available(layer) for layer in _VECTOR_LAYER_SETTINGS_ATTR}}


def _vector_path(layer: str) -> Path | None:
    settings = get_settings()
    raw = getattr(settings, _VECTOR_LAYER_SETTINGS_ATTR[layer], None)
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


@lru_cache
def _load_vector(layer: str):
    import geopandas as gpd

    path = _vector_path(layer)
    if path is None:
        return None
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        return None  # can't safely reproject an unknown CRS
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    return gdf


def vector_gdf(layer: str):
    """Reprojected (EPSG:4326) GeoDataFrame for `layer`, or None if not
    configured. Caller's responsibility from here -- this module doesn't
    assume how the data will be used (zonal summary, map layer, scoring
    input, etc.)."""
    return _load_vector(layer)


def layer_columns(layer: str) -> list[str]:
    gdf = vector_gdf(layer)
    if gdf is None:
        return []
    return [c for c in gdf.columns if c != "geometry"]


# Skip the exact polygon `.clip()` (using the bbox pre-filter result as
# a close-enough approximation instead) when BOTH the candidate-feature
# count and the AOI geometry's complexity are high -- that combination is
# what's actually expensive, not either alone. Measured while building
# this: clipping geomorphology.shp's 12,781 polygons against the whole
# Kerala state boundary (a 14-district dissolved multipolygon, ~612KB
# WKB) took 47+ seconds -- long enough to hang a request. But clipping
# the same layer's ~1,400 bbox-prefiltered candidates against a single
# district (a much simpler polygon, a few KB) took under a second, and
# clipping drainage.shp's ~53,000 bbox-prefiltered candidates against
# Idukki district (simple geometry) also took under 2 seconds. So: a
# large candidate set is fine against a simple geometry, and a complex
# geometry is fine against a small candidate set -- it's the state-wide
# case (both large) that needs the shortcut. For a category-share
# summary like this one, bbox-only vs. exactly-clipped makes negligible
# difference anyway.
_APPROX_CANDIDATE_THRESHOLD = 2_000
_APPROX_GEOM_WKB_BYTES_THRESHOLD = 50_000


def summarize_layer(layer: str, geom=None, column: str | None = None) -> dict | None:
    """
    Area-weighted breakdown of `column`'s categories (default: a sensible
    per-layer column, see _SUMMARY_COLUMN) within `geom` (a shapely
    geometry in EPSG:4326 -- e.g. from core.aoi.district_geometry() /
    state_geometry()), or across the whole layer if geom is None.
    Returns {"column": ..., "categories": {value: area_fraction, ...},
    "approximate": bool} (approximate=True means bbox-filtered only, not
    exactly clipped -- see the threshold constants above), or None if the
    layer isn't available.
    """
    gdf = vector_gdf(layer)
    if gdf is None:
        return None
    column = column or _SUMMARY_COLUMN.get(layer)
    if column is None or column not in gdf.columns:
        return None

    subset = gdf
    approximate = False
    if geom is not None:
        minx, miny, maxx, maxy = geom.bounds
        prefiltered = gdf.cx[minx:maxx, miny:maxy]
        expensive = (
            not prefiltered.empty
            and len(prefiltered) > _APPROX_CANDIDATE_THRESHOLD
            and len(geom.wkb) > _APPROX_GEOM_WKB_BYTES_THRESHOLD
        )
        if prefiltered.empty:
            subset = prefiltered
        elif expensive:
            subset = prefiltered
            approximate = True
        else:
            clipped = prefiltered.clip(geom)
            subset = clipped if not clipped.empty else prefiltered

    if subset.empty:
        return {"column": column, "categories": {}, "approximate": approximate}

    # Lines (drainage) don't have a meaningful area -- fall back to count
    # share instead of area share for that geometry type. Also report
    # total length (km) -- computed from the geometry itself in EPSG:32643
    # (an accurate meters-based CRS for Kerala), not the shapefile's own
    # LENGTH attribute, whose values (e.g. 0.005) look like they're in
    # decimal degrees or some other stale unit rather than meters/km.
    if subset.geom_type.iloc[0] in ("LineString", "MultiLineString"):
        counts = subset[column].fillna("(unclassified)").value_counts(normalize=True)
        total_length_km = float(subset.to_crs("EPSG:32643").geometry.length.sum()) / 1000
        return {
            "column": column, "approximate": approximate,
            "categories": {str(k): round(float(v), 4) for k, v in counts.items()},
            "total_length_km": round(total_length_km, 1),
        }

    areas = subset.to_crs("EPSG:32643").geometry.area  # equal-ish local projection for a fair area comparison
    total = areas.sum()
    if total == 0:
        return {"column": column, "categories": {}, "approximate": approximate}
    frac = (
        subset.assign(_area=areas.values)
        .groupby(subset[column].fillna("(unclassified)"))["_area"]
        .sum() / total
    )
    return {
        "column": column, "approximate": approximate,
        "categories": {str(k): round(float(v), 4) for k, v in frac.sort_values(ascending=False).items()},
    }
