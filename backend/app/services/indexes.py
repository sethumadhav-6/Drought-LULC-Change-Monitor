"""
Spectral index library.

Formulas follow the standard definitions catalogued at the Index
Database (https://www.indexdatabase.de/) and widely used in tropical
drought / land-cover literature. Each entry works on Sentinel-2 (S2)
and, where noted, Landsat 8/9 (L8) surface reflectance band names.

Every function accepts an `ee.Image` (Earth Engine path) OR an
xarray.DataArray stacked on a "band" dimension with band labels
matching BAND_ALIASES (Planetary Computer / local path), and returns
the same type back. This lets services/drought.py and
services/lulc.py stay agnostic to which data backend served the
imagery.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# Sentinel-2 (10-60m, L2A) common-name -> native band mapping.
S2_BANDS = {
    "coastal": "B1", "blue": "B2", "green": "B3", "red": "B4",
    "rededge1": "B5", "rededge2": "B6", "rededge3": "B7",
    "nir": "B8", "nir08": "B8A", "watervapor": "B9",
    "swir16": "B11", "swir22": "B12",
}

# Landsat 8/9 Collection 2 L2 common-name -> native band mapping.
L8_BANDS = {
    "coastal": "SR_B1", "blue": "SR_B2", "green": "SR_B3", "red": "SR_B4",
    "nir": "SR_B5", "swir16": "SR_B6", "swir22": "SR_B7",
    "thermal": "ST_B10",
}


@dataclass(frozen=True)
class IndexDef:
    code: str
    name: str
    formula: str
    bands: tuple[str, ...]
    category: str
    reference: str
    fn: Callable


def _ee_norm(a, b):
    return a.subtract(b).divide(a.add(b))


def _xr_norm(a, b):
    return (a - b) / (a + b)


def _is_ee(img) -> bool:
    return type(img).__module__.startswith("ee.")


def _band(img, common_name: str, sensor_map: dict):
    """Select a band from either an ee.Image or an xarray band-stack."""
    if _is_ee(img):
        return img.select(sensor_map[common_name])
    return img.sel(band=common_name)


def _norm(img, b1, b2, sensor_map):
    a, b = _band(img, b1, sensor_map), _band(img, b2, sensor_map)
    return _ee_norm(a, b) if _is_ee(img) else _xr_norm(a, b)


# ---------------------------------------------------------------- #
# Vegetation
# ---------------------------------------------------------------- #

def ndvi(img, sensor_map=S2_BANDS):
    """NDVI = (NIR - Red) / (NIR + Red)  [Rouse et al. 1974]"""
    return _norm(img, "nir", "red", sensor_map)


def gndvi(img, sensor_map=S2_BANDS):
    """GNDVI = (NIR - Green) / (NIR + Green)  [Gitelson et al. 1996]"""
    return _norm(img, "nir", "green", sensor_map)


def evi(img, sensor_map=S2_BANDS):
    """EVI = 2.5 * (NIR-Red) / (NIR + 6*Red - 7.5*Blue + 1)  [Huete et al. 2002]"""
    nir, red, blue = _band(img, "nir", sensor_map), _band(img, "red", sensor_map), _band(img, "blue", sensor_map)
    if _is_ee(img):
        return nir.subtract(red).multiply(2.5).divide(
            nir.add(red.multiply(6)).subtract(blue.multiply(7.5)).add(1)
        )
    return 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)


def savi(img, sensor_map=S2_BANDS, L: float = 0.5):
    """SAVI = (NIR-Red)*(1+L) / (NIR+Red+L)  [Huete 1988], L=0.5 default"""
    nir, red = _band(img, "nir", sensor_map), _band(img, "red", sensor_map)
    if _is_ee(img):
        return nir.subtract(red).multiply(1 + L).divide(nir.add(red).add(L))
    return (nir - red) * (1 + L) / (nir + red + L)


def ndre(img, sensor_map=S2_BANDS):
    """NDRE = (NIR - RedEdge1) / (NIR + RedEdge1)  [Barnes et al. 2000], S2 only"""
    return _norm(img, "nir", "rededge1", sensor_map)


# ---------------------------------------------------------------- #
# Water / moisture
# ---------------------------------------------------------------- #

def ndwi(img, sensor_map=S2_BANDS):
    """NDWI (McFeeters 1996) = (Green - NIR) / (Green + NIR), open water"""
    return _norm(img, "green", "nir", sensor_map)


def mndwi(img, sensor_map=S2_BANDS):
    """MNDWI (Xu 2006) = (Green - SWIR1) / (Green + SWIR1), water w/ less built-up noise"""
    return _norm(img, "green", "swir16", sensor_map)


def ndmi(img, sensor_map=S2_BANDS):
    """NDMI / NDWI-Gao = (NIR - SWIR1) / (NIR + SWIR1)  [Gao 1996], vegetation moisture"""
    return _norm(img, "nir", "swir16", sensor_map)


def msi(img, sensor_map=S2_BANDS):
    """MSI = SWIR1 / NIR  [Rock et al. 1986], moisture stress (higher = drier canopy)"""
    swir, nir = _band(img, "swir16", sensor_map), _band(img, "nir", sensor_map)
    return swir.divide(nir) if _is_ee(img) else swir / nir


# ---------------------------------------------------------------- #
# Soil / built-up / burn
# ---------------------------------------------------------------- #

def bsi(img, sensor_map=S2_BANDS):
    """BSI (Rikimaru et al. 2002) = ((SWIR1+Red)-(NIR+Blue)) / ((SWIR1+Red)+(NIR+Blue))"""
    swir, red, nir, blue = (_band(img, b, sensor_map) for b in ("swir16", "red", "nir", "blue"))
    if _is_ee(img):
        num = swir.add(red).subtract(nir.add(blue))
        den = swir.add(red).add(nir.add(blue))
        return num.divide(den)
    return ((swir + red) - (nir + blue)) / ((swir + red) + (nir + blue))


def ndbi(img, sensor_map=S2_BANDS):
    """NDBI (Zha et al. 2003) = (SWIR1 - NIR) / (SWIR1 + NIR), built-up"""
    return _norm(img, "swir16", "nir", sensor_map)


def nbr(img, sensor_map=S2_BANDS):
    """NBR (Key & Benson 2006) = (NIR - SWIR2) / (NIR + SWIR2), burn severity"""
    return _norm(img, "nir", "swir22", sensor_map)


# ---------------------------------------------------------------- #
# Composite drought index (see services/drought.py for VCI/TCI/VHI)
# ---------------------------------------------------------------- #

def nddi(img, sensor_map=S2_BANDS):
    """
    NDDI (Gu et al. 2007) = (NDVI - NDWI) / (NDVI + NDWI)
    Sharper agricultural-drought response than NDVI or NDWI alone;
    validated for tropical environments (Gu 2007; MDPI Land 2025,
    'Application of NDDI for Monitoring Agricultural Drought in
    Tropical Environments').
    """
    v = ndvi(img, sensor_map)
    w = ndwi(img, sensor_map)
    return _ee_norm(v, w) if _is_ee(img) else _xr_norm(v, w)


INDEX_CATALOG: list[IndexDef] = [
    IndexDef("NDVI", "Normalized Difference Vegetation Index", "(NIR-Red)/(NIR+Red)", ("nir", "red"), "vegetation", "Rouse et al. 1974", ndvi),
    IndexDef("GNDVI", "Green NDVI", "(NIR-Green)/(NIR+Green)", ("nir", "green"), "vegetation", "Gitelson et al. 1996", gndvi),
    IndexDef("EVI", "Enhanced Vegetation Index", "2.5*(NIR-Red)/(NIR+6Red-7.5Blue+1)", ("nir", "red", "blue"), "vegetation", "Huete et al. 2002", evi),
    IndexDef("SAVI", "Soil Adjusted Vegetation Index", "(NIR-Red)(1+L)/(NIR+Red+L)", ("nir", "red"), "vegetation", "Huete 1988", savi),
    IndexDef("NDRE", "Normalized Difference Red Edge", "(NIR-RE1)/(NIR+RE1)", ("nir", "rededge1"), "vegetation", "Barnes et al. 2000", ndre),
    IndexDef("NDWI", "Normalized Difference Water Index", "(Green-NIR)/(Green+NIR)", ("green", "nir"), "water", "McFeeters 1996", ndwi),
    IndexDef("MNDWI", "Modified NDWI", "(Green-SWIR1)/(Green+SWIR1)", ("green", "swir16"), "water", "Xu 2006", mndwi),
    IndexDef("NDMI", "Normalized Difference Moisture Index", "(NIR-SWIR1)/(NIR+SWIR1)", ("nir", "swir16"), "moisture", "Gao 1996", ndmi),
    IndexDef("MSI", "Moisture Stress Index", "SWIR1/NIR", ("swir16", "nir"), "moisture", "Rock et al. 1986", msi),
    IndexDef("BSI", "Bare Soil Index", "((SWIR1+Red)-(NIR+Blue))/((SWIR1+Red)+(NIR+Blue))", ("swir16", "red", "nir", "blue"), "soil", "Rikimaru et al. 2002", bsi),
    IndexDef("NDBI", "Normalized Difference Built-up Index", "(SWIR1-NIR)/(SWIR1+NIR)", ("swir16", "nir"), "built-up", "Zha et al. 2003", ndbi),
    IndexDef("NBR", "Normalized Burn Ratio", "(NIR-SWIR2)/(NIR+SWIR2)", ("nir", "swir22"), "fire", "Key & Benson 2006", nbr),
    IndexDef("NDDI", "Normalized Difference Drought Index", "(NDVI-NDWI)/(NDVI+NDWI)", ("nir", "red", "green"), "drought", "Gu et al. 2007", nddi),
]

INDEX_BY_CODE = {i.code: i for i in INDEX_CATALOG}
