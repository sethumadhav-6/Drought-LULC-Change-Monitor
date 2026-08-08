"""
Land use / land cover (LULC) change detection for pre- vs
post-monsoon comparisons (the core "shrinkage" signal the app is
built to flag: e.g. large forest/wetland loss before monsoon onset
that increases runoff + landslide/flood risk during the monsoon).

Two paths:
  1. GEE path: pulls ESA WorldCover v200 (10 m, 2021) as a reference
     layer AND runs a lightweight Random Forest classifier on the
     Sentinel-2 bands for the two target dates, so change isn't
     limited to WorldCover's single fixed epoch.
  2. Local/Planetary Computer path: unsupervised KMeans clustering on
     the stacked index bands (NDVI, NDWI, NDBI, BSI) as a fallback
     classifier when GEE is unavailable.

Both paths return a class raster with the same legend:
    0 water, 1 forest/dense vegetation, 2 cropland/sparse vegetation,
    3 built-up, 4 bare/other
"""
from __future__ import annotations

LULC_LEGEND = {
    0: {"label": "Water", "color": "#3288bd"},
    1: {"label": "Forest / Dense Vegetation", "color": "#1a9850"},
    2: {"label": "Cropland / Sparse Vegetation", "color": "#a6d96a"},
    3: {"label": "Built-up", "color": "#d73027"},
    4: {"label": "Bare / Other", "color": "#bdbdbd"},
}


def classify_gee(ee, image, band_map):
    """
    Rule-based classification on ee.Image index bands (fast, explainable,
    no training-data dependency -- appropriate for an MVP where a
    labelled Kerala training set isn't available yet). Threshold-based
    on NDVI/MNDWI/NDBI/BSI, tuned for humid-tropical Kerala land cover.
    Swap in a supervised ee.Classifier.smileRandomForest once training
    points are collected (see docs/DATA_SOURCES.md).
    """
    from .indexes import ndvi, mndwi, ndbi, bsi

    v, w, b_, s = ndvi(image, band_map), mndwi(image, band_map), ndbi(image, band_map), bsi(image, band_map)

    water = w.gt(0.0)
    built = b_.gt(0.0).And(w.lte(0.0))
    forest = v.gt(0.5).And(water.Not()).And(built.Not())
    crop = v.gt(0.2).And(v.lte(0.5)).And(water.Not()).And(built.Not())
    bare = s.gt(0.1).And(water.Not()).And(built.Not()).And(forest.Not()).And(crop.Not())

    out = (
        ee.Image(4)
        .where(crop, 2)
        .where(forest, 1)
        .where(built, 3)
        .where(water, 0)
        .where(bare, 4)
        .rename("lulc")
    )
    return out


def classify_local(index_stack):
    """
    Fallback for the Planetary Computer path: rule-based thresholds on
    an xarray stack that has NDVI/MNDWI/NDBI/BSI bands already computed
    (see services/indexes.py). Returns a numpy uint8 class array.
    """
    import numpy as np

    ndvi_, mndwi_, ndbi_, bsi_ = (index_stack.sel(band=b).values for b in ("NDVI", "MNDWI", "NDBI", "BSI"))
    out = np.full(ndvi_.shape, 4, dtype=np.uint8)
    water = mndwi_ > 0.0
    built = (ndbi_ > 0.0) & ~water
    forest = (ndvi_ > 0.5) & ~water & ~built
    crop = (ndvi_ > 0.2) & (ndvi_ <= 0.5) & ~water & ~built
    bare = (bsi_ > 0.1) & ~water & ~built & ~forest & ~crop
    out[crop] = 2
    out[forest] = 1
    out[built] = 3
    out[water] = 0
    out[bare] = 4
    return out


def change_matrix(pre_classes, post_classes, pixel_area_m2: float):
    """
    Build a from->to change-area matrix (hectares) between two class
    rasters of identical shape (numpy arrays). Used to quantify e.g.
    "forest -> bare" shrinkage between pre- and post-monsoon dates.
    """
    import numpy as np
    import pandas as pd

    classes = sorted(LULC_LEGEND.keys())
    labels = [LULC_LEGEND[c]["label"] for c in classes]
    matrix = np.zeros((len(classes), len(classes)), dtype=np.int64)
    pre_flat, post_flat = pre_classes.ravel(), post_classes.ravel()
    valid = ~(np.isnan(pre_flat) | np.isnan(post_flat)) if pre_flat.dtype.kind == "f" else slice(None)
    pre_v, post_v = pre_flat[valid], post_flat[valid]
    for i, c_from in enumerate(classes):
        for j, c_to in enumerate(classes):
            matrix[i, j] = int(np.sum((pre_v == c_from) & (post_v == c_to)))

    ha_per_pixel = pixel_area_m2 / 10_000.0
    df = pd.DataFrame(matrix * ha_per_pixel, index=labels, columns=labels)
    df.index.name = "From \\ To (ha)"
    return df


def shrinkage_flags(change_df, threshold_ha: float = 50.0) -> list[dict]:
    """
    Flag from->to transitions that represent likely ecological
    "shrinkage" (forest/water loss to bare/built-up) above
    `threshold_ha`, for the pre-monsoon early-warning use case.
    """
    watch_pairs = [
        ("Forest / Dense Vegetation", "Bare / Other"),
        ("Forest / Dense Vegetation", "Built-up"),
        ("Water", "Bare / Other"),
        ("Cropland / Sparse Vegetation", "Bare / Other"),
    ]
    flags = []
    for src, dst in watch_pairs:
        if src in change_df.index and dst in change_df.columns:
            area = float(change_df.loc[src, dst])
            if area >= threshold_ha:
                flags.append({
                    "from": src, "to": dst, "area_ha": round(area, 1),
                    "note": f"{area:,.1f} ha converted from {src} to {dst}; "
                            f"review before monsoon onset for runoff/landslide risk.",
                })
    return flags
