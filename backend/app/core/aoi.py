"""
Precise Kerala district boundaries, loaded from a local shapefile --
replaces the FAO GAUL / bounding-box placeholders that were used as a
stand-in before a real boundary layer was available (see
docs/DATA_SOURCES.md).

Expects a GADM-format shapefile (NAME_0 = country, NAME_1 = state,
NAME_2 = district) at Settings.kerala_shapefile_path, e.g.
data_store/shapefiles/kerala_districts.shp -- with its .dbf/.shx/.prj
siblings alongside it (a .shp alone is not a valid shapefile).

If the file isn't present, every function here degrades gracefully
(returns None / empty) and callers fall back to their existing
FAO GAUL / bbox behavior -- this module is additive, not a hard
dependency.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .config import get_settings

# Common district-name column conventions, checked in priority order.
# GADM level-2 layers (like the one this app expects) use NAME_2.
_NAME_COLUMN_CANDIDATES = ("NAME_2", "DISTRICT", "District", "district", "DIST_NAME", "dtname")


@lru_cache
def _load():
    import geopandas as gpd

    settings = get_settings()
    path = Path(settings.kerala_shapefile_path)
    if not path.exists():
        return None
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    return gdf


def is_available() -> bool:
    return _load() is not None


def _name_column(gdf) -> str:
    for col in _NAME_COLUMN_CANDIDATES:
        if col in gdf.columns:
            return col
    for col in gdf.columns:
        if col != "geometry" and gdf[col].dtype == object:
            return col
    raise ValueError("Could not find a district-name column in the Kerala shapefile.")


def district_names() -> list[str]:
    gdf = _load()
    if gdf is None:
        return []
    col = _name_column(gdf)
    return sorted(gdf[col].astype(str).unique().tolist())


def _bbox(gdf) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = gdf.total_bounds
    return (float(minx), float(miny), float(maxx), float(maxy))


def state_bbox() -> tuple[float, float, float, float] | None:
    gdf = _load()
    return _bbox(gdf) if gdf is not None else None


def district_bbox(name: str) -> tuple[float, float, float, float] | None:
    gdf = _load()
    if gdf is None:
        return None
    col = _name_column(gdf)
    match = gdf[gdf[col].astype(str).str.lower() == name.strip().lower()]
    return _bbox(match) if not match.empty else None


def district_geometry(name: str):
    """Shapely geometry (EPSG:4326) for the named district, or None if not found."""
    gdf = _load()
    if gdf is None:
        return None
    col = _name_column(gdf)
    match = gdf[gdf[col].astype(str).str.lower() == name.strip().lower()]
    if match.empty:
        return None
    return match.union_all() if hasattr(match, "union_all") else match.unary_union


def state_geometry():
    """Dissolved geometry (EPSG:4326) of all districts, i.e. the Kerala state boundary."""
    gdf = _load()
    if gdf is None:
        return None
    return gdf.union_all() if hasattr(gdf, "union_all") else gdf.unary_union


def resolve_bbox(aoi_name: str, fallback: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """
    Best-effort bbox lookup for an AOI name: tries an exact district
    match first, then falls back to the whole state, then to the
    caller-supplied placeholder (e.g. routes_catalog.KERALA_BBOX) if
    the shapefile isn't loaded at all.
    """
    if not is_available():
        return fallback
    if aoi_name.strip().lower() not in ("kerala", "kerala (state)"):
        bbox = district_bbox(aoi_name)
        if bbox:
            return bbox
    return state_bbox() or fallback
