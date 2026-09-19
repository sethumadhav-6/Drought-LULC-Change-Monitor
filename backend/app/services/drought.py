"""
Composite drought-stress engine: VCI, TCI, VHI, plus NDDI from
services/indexes.py. These are the "standard equations" widely used
for tropical agricultural-drought monitoring (FAO ASIS, NOAA STAR
Vegetation Health product, Kogan 1995/1997).

    VCI = 100 * (NDVI - NDVI_min) / (NDVI_max - NDVI_min)
    TCI = 100 * (BT_max - BT) / (BT_max - BT_min)
    VHI = 0.5*VCI + 0.5*TCI

NDVI_min/max and BT_min/max are the pixel-wise historical range over
a reference climatology period (recommended: same calendar
dekad/month across >= 5-10 years). BT (brightness/land-surface
temperature) comes from Landsat thermal (ST_B10) when using the GEE
backend, since Sentinel-2 carries no thermal band.

Interpretation (Kogan 1997, FAO/WMO Integrated Drought Management
Programme):
    VHI < 10   Extreme drought stress
    10-20      Severe
    20-35      Moderate
    35-50      Mild / warning
    > 50       No significant stress
"""
from __future__ import annotations

from .indexes import ndvi, nddi

VHI_BREAKS = [
    (0, 10, "Extreme"),
    (10, 20, "Severe"),
    (20, 35, "Moderate"),
    (35, 50, "Mild / Watch"),
    (50, 100.0001, "No significant stress"),
]


def classify_vhi(value: float) -> str:
    for lo, hi, label in VHI_BREAKS:
        if lo <= value < hi:
            return label
    return "No data"


def vci_ee(ndvi_current, ndvi_min, ndvi_max):
    """Vegetation Condition Index on ee.Images (per-pixel historical min/max)."""
    return ndvi_current.subtract(ndvi_min).divide(ndvi_max.subtract(ndvi_min)).multiply(100).rename("VCI")


def tci_ee(bt_current, bt_min, bt_max):
    """Temperature Condition Index on ee.Images (Landsat ST_B10, Kelvin)."""
    return bt_max.subtract(bt_current).divide(bt_max.subtract(bt_min)).multiply(100).rename("TCI")


def vhi_ee(vci_img, tci_img, w_vci: float = 0.5):
    return vci_img.multiply(w_vci).add(tci_img.multiply(1 - w_vci)).rename("VHI")


def compute_vci_series(ee, s2_collection, aoi, band_map, current_start, current_end, climatology_years: int = 8):
    """
    Build a per-pixel VCI image for `aoi` over [current_start, current_end]
    against an `climatology_years`-year NDVI min/max climatology for the
    same calendar window. `s2_collection` is e.g. 'COPERNICUS/S2_SR_HARMONIZED'.
    Returns (vci_image, ndvi_current_image).
    """
    from datetime import date

    cs, ce = date.fromisoformat(current_start), date.fromisoformat(current_end)

    def _clean(col):
        return col.map(lambda img: img.divide(10000).copyProperties(img, img.propertyNames()))

    current = ee.ImageCollection(s2_collection).filterBounds(aoi).filterDate(current_start, current_end)
    current_ndvi = _clean(current).map(lambda img: ndvi(img, band_map).rename("NDVI")).median()

    hist_imgs = []
    for k in range(1, climatology_years + 1):
        y_start = date(cs.year - k, cs.month, cs.day).isoformat()
        y_end = date(ce.year - k, ce.month, ce.day).isoformat()
        col = ee.ImageCollection(s2_collection).filterBounds(aoi).filterDate(y_start, y_end)
        hist_imgs.append(_clean(col).map(lambda img: ndvi(img, band_map).rename("NDVI")).median())

    hist_col = ee.ImageCollection(hist_imgs)
    ndvi_min = hist_col.min()
    ndvi_max = hist_col.max()
    vci = vci_ee(current_ndvi, ndvi_min, ndvi_max).clip(aoi)
    return vci, current_ndvi.clip(aoi)


def drought_summary(ndvi_val: float, ndwi_val: float, vhi_val: float | None = None) -> dict:
    """Small helper used by the report builder to turn raw pixel-mean
    stats into a human-readable drought-stress record for one AOI/date."""
    nddi_val = (ndvi_val - ndwi_val) / (ndvi_val + ndwi_val) if (ndvi_val + ndwi_val) != 0 else None
    record = {
        "NDVI_mean": ndvi_val,
        "NDWI_mean": ndwi_val,
        "NDDI_mean": nddi_val,
    }
    if vhi_val is not None:
        record["VHI_mean"] = vhi_val
        record["VHI_class"] = classify_vhi(vhi_val)
    return record


# NDVI/NDBI value ranges used to normalize each into 0..1 before weighting
# -- same ranges as indexes.py's DEFAULT_VIS_PARAMS for these two
# categories ("vegetation": -0.2..0.9, "built-up": -0.5..0.5), so the
# score stays consistent with how these indexes are visualized elsewhere.
_NDVI_RANGE = (-0.2, 0.9)
_NDBI_RANGE = (-0.5, 0.5)

LAND_STRESS_BREAKS = [
    (0, 0.25, "Low"),
    (0.25, 0.45, "Moderate"),
    (0.45, 0.65, "High"),
    (0.65, 1.0001, "Severe"),
]


def classify_land_stress(score: float) -> str:
    for lo, hi, label in LAND_STRESS_BREAKS:
        if lo <= score < hi:
            return label
    return "No data"


def land_stress_index(ndvi_val: float, ndbi_val: float, w_ndvi: float = 0.6, w_ndbi: float = 0.4) -> dict:
    """
    Weighted NDVI + NDBI composite land-degradation-stress score, used in
    place of a discrete LULC classification (per project direction: skip
    the rule-based LULC change-matrix in services/lulc.py, weight the two
    continuous indices directly instead). Higher score = more stressed
    (less vegetation, more bare/built-up surface).

        score = w_ndvi * (1 - NDVI_norm) + w_ndbi * NDBI_norm

    where NDVI_norm and NDBI_norm are each min-max normalized against
    typical Kerala Sentinel-2 ranges (see _NDVI_RANGE/_NDBI_RANGE above)
    and clamped to [0, 1] so an outlier pixel-mean can't blow the score
    outside its intended 0..1 range.

    Default weights (0.6 NDVI / 0.4 NDBI) treat vegetation loss as the
    primary drought/degradation signal and NDBI as a secondary,
    corroborating one -- e.g. helping distinguish "vegetation dropped
    because of new construction" from "vegetation dropped because of
    drought stress with no built-up increase". These are a reasonable
    starting point, not a validated calibration -- pass different
    w_ndvi/w_ndbi if a different balance is wanted.
    """
    def _norm(v, lo, hi):
        return max(0.0, min(1.0, (v - lo) / (hi - lo)))

    ndvi_norm = _norm(ndvi_val, *_NDVI_RANGE)
    ndbi_norm = _norm(ndbi_val, *_NDBI_RANGE)
    score = w_ndvi * (1 - ndvi_norm) + w_ndbi * ndbi_norm
    return {
        "score": round(score, 4),
        "class": classify_land_stress(score),
        "ndvi_mean": ndvi_val,
        "ndbi_mean": ndbi_val,
        "weights": {"ndvi": w_ndvi, "ndbi": w_ndbi},
    }
