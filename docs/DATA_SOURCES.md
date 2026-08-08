# Data Sources

## Imagery

| Source | Backend | Collection ID | Resolution | Revisit | Notes |
|---|---|---|---|---|---|
| Sentinel-2 L2A | Google Earth Engine | `COPERNICUS/S2_SR_HARMONIZED` | 10 m | ~5 days | Primary source. No thermal band. |
| Sentinel-2 L2A | Planetary Computer | `sentinel-2-l2a` | 10 m | ~5 days | No-auth fallback; local index compute via rioxarray. |
| Landsat 8/9 C2L2 | Google Earth Engine | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` | 30 m | ~16 days (8 combined w/ 9) | Includes thermal (ST_B10) — needed for TCI/VHI. |
| Landsat 8/9 C2L2 | Planetary Computer | `landsat-c2-l2` | 30 m | ~16 days | No-auth fallback. |

## AOI boundaries

- **Planetary Computer path**: uses a real Kerala district boundary layer,
  loaded from a shapefile at `data_store/shapefiles/kerala_districts.shp`
  (GADM level-2 format: `NAME_2` = district name). See `core/aoi.py` —
  `resolve_bbox()` looks up an exact district bbox first, falling back to
  the whole-state bbox, and finally to the coarse placeholder bbox in
  `routes_catalog.py::KERALA_BBOX` only if the shapefile is missing.
  A shapefile is a multi-file format — `.shp` alone won't load; its
  `.dbf`/`.shx`/`.prj` siblings need to sit alongside it in the same folder.
- **GEE path**: still uses `FAO/GAUL/2015/level1` (state) / `level2`
  (district), filtered to `ADM1_NAME == "Kerala"`, since a local shapefile
  isn't directly usable inside Earth Engine without uploading it as an EE
  asset first. Good enough for an MVP; GAUL boundaries are a
  simplified/generalized global dataset, not survey-grade. To upgrade this
  path too: upload the same shapefile as an Earth Engine asset (`earthengine
  upload table ...`) and swap `kerala_boundary()`/`kerala_districts()` in
  `core/gee.py` to read that asset instead of GAUL.

## Reference land-cover layer

`services/lulc.py` currently classifies Sentinel-2 composites directly with
rule-based NDVI/MNDWI/NDBI/BSI thresholds. **ESA WorldCover v200** (10 m,
2021, `ESA/WorldCover/v200` on GEE) is a good reference/validation layer to
compare against, and a source of training points for a future supervised
classifier.

## Extending beyond Kerala

The AOI, index, and drought/LULC engines are not Kerala-specific — only
`routes_catalog.py` and `routes_analysis.py` hardcode the Kerala
boundary/district lookups. To add another tropical country: add its
boundary lookup (FAO GAUL / GADM) alongside `kerala_boundary()` in
`core/gee.py`, and add an AOI entry in `routes_catalog.py`.

## Rate limits / quotas to be aware of

- Google Earth Engine: free tier has per-project compute quotas; state-wide
  `reduceRegion` calls at fine scale can be slow/expensive — the analysis
  endpoint uses `scale=100` and `bestEffort=True` to stay within reasonable
  bounds for an MVP.
- Planetary Computer: no auth, but be considerate of concurrent large-scene
  downloads; signed URLs expire after ~1 hour.
