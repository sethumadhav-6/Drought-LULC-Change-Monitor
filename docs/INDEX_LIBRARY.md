# Index Library

Formulas follow the standard definitions catalogued at the
[Index Database](https://www.indexdatabase.de/) and widely used remote-sensing
literature. Implemented in `backend/app/services/indexes.py` (vegetation/water/
soil/burn indices) and `backend/app/services/drought.py` (composite drought
indices). All work on Sentinel-2 L2A or Landsat 8/9 C2L2 surface reflectance.

## Vegetation

| Code | Name | Formula | Reference |
|---|---|---|---|
| NDVI | Normalized Difference Vegetation Index | (NIR−Red)/(NIR+Red) | Rouse et al. 1974 |
| GNDVI | Green NDVI | (NIR−Green)/(NIR+Green) | Gitelson et al. 1996 |
| EVI | Enhanced Vegetation Index | 2.5·(NIR−Red)/(NIR+6·Red−7.5·Blue+1) | Huete et al. 2002 |
| SAVI | Soil Adjusted Vegetation Index | (NIR−Red)(1+L)/(NIR+Red+L), L=0.5 | Huete 1988 |
| NDRE | Normalized Difference Red Edge | (NIR−RedEdge1)/(NIR+RedEdge1) | Barnes et al. 2000 |

## Water / moisture

| Code | Name | Formula | Reference |
|---|---|---|---|
| NDWI | Normalized Difference Water Index | (Green−NIR)/(Green+NIR) | McFeeters 1996 |
| MNDWI | Modified NDWI | (Green−SWIR1)/(Green+SWIR1) | Xu 2006 |
| NDMI | Normalized Difference Moisture Index | (NIR−SWIR1)/(NIR+SWIR1) | Gao 1996 |
| MSI | Moisture Stress Index | SWIR1/NIR | Rock et al. 1986 |

## Soil / built-up / fire

| Code | Name | Formula | Reference |
|---|---|---|---|
| BSI | Bare Soil Index | ((SWIR1+Red)−(NIR+Blue))/((SWIR1+Red)+(NIR+Blue)) | Rikimaru et al. 2002 |
| NDBI | Normalized Difference Built-up Index | (SWIR1−NIR)/(SWIR1+NIR) | Zha et al. 2003 |
| NBR | Normalized Burn Ratio | (NIR−SWIR2)/(NIR+SWIR2) | Key & Benson 2006 |

## Drought (composite / stress indices)

| Code | Name | Formula | Reference |
|---|---|---|---|
| NDDI | Normalized Difference Drought Index | (NDVI−NDWI)/(NDVI+NDWI) | Gu et al. 2007; validated for tropical agricultural drought (MDPI *Land* 2025) |
| VCI | Vegetation Condition Index | 100·(NDVI−NDVI_min)/(NDVI_max−NDVI_min), per-pixel historical range | Kogan 1995 |
| TCI | Temperature Condition Index | 100·(BT_max−BT)/(BT_max−BT_min), Landsat thermal (ST_B10) | Kogan 1995 |
| VHI | Vegetation Health Index | 0.5·VCI + 0.5·TCI | Kogan 1997; NOAA STAR Vegetation Health Product |

**VHI interpretation** (FAO / WMO Integrated Drought Management Programme):

| VHI range | Class |
|---|---|
| < 10 | Extreme drought stress |
| 10–20 | Severe |
| 20–35 | Moderate |
| 35–50 | Mild / watch |
| > 50 | No significant stress |

VCI/TCI need a multi-year climatology (`compute_vci_series` in `drought.py`
defaults to 8 years) of the same calendar window to compute the per-pixel
min/max — accuracy improves with more years of Sentinel-2 (available since
2015-16) or Landsat (available since 1984) history. TCI needs a thermal band,
so it only works on the Landsat path.

## Adding a new index

1. Add a `def my_index(img, sensor_map=S2_BANDS): ...` function to
   `services/indexes.py`, working on both `ee.Image` and the xarray band-stack
   (see `_band`/`_norm` helpers).
2. Register it in `INDEX_CATALOG`.
3. It automatically appears in `/api/catalog/indexes` and the frontend's
   collapsible "Indexes" section — no frontend changes needed.
