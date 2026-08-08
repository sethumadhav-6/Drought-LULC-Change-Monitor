"""Read-only catalog endpoints: index library, Kerala AOIs, data-source status."""
from __future__ import annotations

from fastapi import APIRouter

from ..core import aoi, gee
from ..services.indexes import INDEX_CATALOG

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

KERALA_DISTRICTS = [
    "Thiruvananthapuram", "Kollam", "Pathanamthitta", "Alappuzha", "Kottayam",
    "Idukki", "Ernakulam", "Thrissur", "Palakkad", "Malappuram",
    "Kozhikode", "Wayanad", "Kannur", "Kasaragod",
]

# Kerala state bounding box (lon_min, lat_min, lon_max, lat_max) -- used as the
# default AOI for the Planetary Computer path / before a precise boundary
# (GADM/Survey of India) is loaded. See docs/DATA_SOURCES.md.
KERALA_BBOX = (74.86, 8.29, 77.42, 12.82)

DATA_SOURCES = {
    "sentinel-2": {
        "label": "Sentinel-2 (10m, L2A surface reflectance)",
        "gee_collection": "COPERNICUS/S2_SR_HARMONIZED",
        "pc_collection": "sentinel-2-l2a",
        "revisit_days": 5,
        "notes": "Primary source. No thermal band -- pair with Landsat for TCI/VHI.",
    },
    "landsat": {
        "label": "Landsat 8/9 (30m, Collection 2 Level-2)",
        "gee_collection": "LANDSAT/LC08/C02/T1_L2 + LANDSAT/LC09/C02/T1_L2",
        "pc_collection": "landsat-c2-l2",
        "revisit_days": 16,
        "notes": "Includes thermal band (ST_B10) required for TCI / VHI.",
    },
}


@router.get("/indexes")
def list_indexes():
    return [
        {"code": i.code, "name": i.name, "formula": i.formula, "category": i.category, "reference": i.reference}
        for i in INDEX_CATALOG
    ]


@router.get("/aoi/kerala")
def kerala_aoi():
    if aoi.is_available():
        return {
            "state": "Kerala",
            "districts": aoi.district_names(),
            "bbox": aoi.state_bbox(),
            "boundary_source": "shapefile",
        }
    return {
        "state": "Kerala",
        "districts": KERALA_DISTRICTS,
        "bbox": KERALA_BBOX,
        "boundary_source": "bbox-placeholder",
    }


@router.get("/data-sources")
def data_sources():
    return {
        **DATA_SOURCES,
        "gee_available": gee.is_available(),
    }
