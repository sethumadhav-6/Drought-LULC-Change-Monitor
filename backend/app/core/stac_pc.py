"""
Microsoft Planetary Computer STAC fallback.

No account / auth required. Used automatically when Google Earth
Engine isn't configured (core/gee.py.is_available() == False), or
when the user explicitly picks "Planetary Computer" as the source in
the UI. Provides Sentinel-2 L2A and Landsat Collection-2 Level-2
search + signed-asset access, read locally with rioxarray/rasterio.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from .config import get_settings

COLLECTIONS = {
    "sentinel-2": "sentinel-2-l2a",
    "landsat": "landsat-c2-l2",
}

# Planetary Computer asset keys are the native band IDs, not common
# names -- translate services/indexes.py's common names (red, nir,
# swir16, ...) to the right asset key per collection.
ASSET_KEYS = {
    "sentinel-2": {
        "coastal": "B01", "blue": "B02", "green": "B03", "red": "B04",
        "rededge1": "B05", "rededge2": "B06", "rededge3": "B07",
        "nir": "B08", "nir08": "B8A", "watervapor": "B09",
        "swir16": "B11", "swir22": "B12",
    },
    "landsat": {
        "coastal": "coastal", "blue": "blue", "green": "green", "red": "red",
        "nir": "nir08", "swir16": "swir16", "swir22": "swir22", "thermal": "lwir11",
    },
}


def search_items(
    bbox: tuple[float, float, float, float],
    start: date,
    end: date,
    collection: str = "sentinel-2",
    max_cloud_cover: float = 30.0,
    limit: int = 50,
):
    """
    Search the Planetary Computer STAC catalog for imagery over `bbox`
    between `start` and `end`. Returns a list of signed pystac Items,
    sorted by increasing cloud cover.
    """
    import planetary_computer
    import pystac_client

    settings = get_settings()
    catalog = pystac_client.Client.open(
        settings.pc_stac_url, modifier=planetary_computer.sign_inplace
    )
    cloud_field = "eo:cloud_cover"
    search = catalog.search(
        collections=[COLLECTIONS.get(collection, collection)],
        bbox=bbox,
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        query={cloud_field: {"lt": max_cloud_cover}},
        limit=limit,
    )
    items = list(search.items())
    items.sort(key=lambda it: it.properties.get(cloud_field, 100))
    return items


def stack_bands(item, bands: Iterable[str], collection: str = "sentinel-2"):
    """
    Open the requested bands of a signed STAC item as an
    (band, y, x) xarray DataArray using rioxarray, reprojected to a
    common grid. `bands` are common names (e.g. ["red", "nir",
    "swir16"]) as used throughout services/indexes.py; translated to
    the collection's native asset keys internally, but the returned
    stack's "band" coordinate stays in common-name form so index
    functions can `.sel(band="red")` regardless of collection.
    """
    import rioxarray  # noqa: F401
    import xarray as xr

    asset_map = ASSET_KEYS.get(collection, ASSET_KEYS["sentinel-2"])
    arrays = []
    for band in bands:
        asset_key = asset_map.get(band, band)
        if asset_key not in item.assets:
            raise KeyError(f"Band '{band}' (asset '{asset_key}') not found on item {item.id}")
        href = item.assets[asset_key].href
        da = rioxarray.open_rasterio(href, masked=True).squeeze("band", drop=True)
        da = da.assign_coords(band=band)
        arrays.append(da)
    ref = arrays[0]
    aligned = [a.rio.reproject_match(ref) if a.shape != ref.shape else a for a in arrays]
    stacked = xr.concat(aligned, dim="band")
    stacked["band"] = list(bands)
    return stacked
