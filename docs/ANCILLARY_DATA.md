# Ancillary data (DEM, soil, drainage, geomorphology, geology)

Five layers, loaded and queryable via `app/core/ancillary.py`, exposed at
`GET /api/catalog/ancillary?aoi_name=<name>`. The dashboard now shows
these alongside the index results with a plain-language "Terrain context
for these results" paragraph (`buildTerrainNarrative()` in `static/main.js`)
that ties the dominant soil drainage class / geomorphology unit / geology
group / elevation to the land-stress score's direction -- but this is
descriptive, **not yet a numeric input into the score itself**. See
"What's next" below.

## What's actually in the data (verified against the real files)

| Layer | File | Format | CRS | Notes |
|---|---|---|---|---|
| DEM | `data_store/dem/kl_dem.tif` | GeoTIFF, int16, ~30m | EPSG:4326 | nodata=-32768, covers the full Kerala extent, elevation -48 to 2685m |
| Soil | `data_store/shapefiles/soil.shp` | Polygon, 615 features | EPSG:32643 | `DEPTH`, `TEXTURE`, `SLOPE`, `DRAINAGE` columns |
| Drainage | `data_store/shapefiles/drainage.shp` | Line, ~158,749 features | EPSG:32643 | `ORDER_` (stream order), `LENGTH` (unreliable units -- see below) |
| Geomorphology | `data_store/shapefiles/geomorphology.shp` | Polygon, 12,781 features | EPSG:32643 | `DISCR_L1/L2/L3` (e.g. Plateau, Pediplain, Denudational Hills) |
| Geology | `data_store/shapefiles/geology.shp` | Polygon, 2,886 features | EPSG:32643 | `ROCK_TYPE`, `ROCK_GROUP` (e.g. Metamorphic, Laterite) |

Config in `backend/.env` (`DEM_PATH`, `SOIL_SHAPEFILE_PATH`,
`DRAINAGE_SHAPEFILE_PATH`, `GEOMORPHOLOGY_SHAPEFILE_PATH`,
`GEOLOGY_SHAPEFILE_PATH`) already defaults to these paths -- only
override if you move the files somewhere else (any local path works,
including a different drive, since Flask runs on your machine).

Vector layers get reprojected to EPSG:4326 on load so they line up with
everything else (GEE geometries, Leaflet, the DEM). The `drainage.shp`
`LENGTH` attribute looks like it's in decimal-degrees or some other
stale unit (values like `0.005` for what should be real distances), so
`summarize_layer()` computes length itself from the geometry in
EPSG:32643 (an accurate meters-based CRS for Kerala) instead of trusting
that column.

## The `/api/catalog/ancillary` endpoint

```
GET /api/catalog/ancillary?aoi_name=Kerala
GET /api/catalog/ancillary?aoi_name=Idukki
```
Returns elevation stats (min/max/mean) and, per vector layer, an
area-weighted (or count-weighted, for drainage) category breakdown of
that layer's default summary column (`DRAINAGE` for soil, `DISCR_L1` for
geomorphology, `ROCK_GROUP` for geology, `ORDER_` for drainage) plus
total drainage length in km. This is a *summary*, not raw features --
`drainage.shp` alone has ~159k lines; sending that as GeoJSON per
request would be tens of MB.

**Performance note, worth knowing if you touch this code:** exactly
clipping a large polygon/line layer against the whole Kerala state
boundary (a complex 14-district dissolved multipolygon) is slow --
`geomorphology.shp` took 47+ seconds in testing before the fix below.
`summarize_layer()` now does a fast bounding-box pre-filter first (via
the geopandas spatial index), and only falls through to an exact
`.clip()` when both the candidate count and the AOI geometry's
complexity are low enough for that to stay fast (a few seconds); above
that it uses the bbox-filtered result directly and marks the response
`"approximate": true`. District-level queries are always exact (a single
district's polygon is simple enough to clip quickly regardless of layer
size).

## What's next

`core/ancillary.py` gives you loading + AOI-level summaries, and the
dashboard now surfaces them as descriptive context next to the index
results (see above). What it deliberately does *not* do yet: feed any of
this into `land_stress_index()`'s actual score (see `services/drought.py`)
as a number, or render these layers as map tiles. Exactly how slope
(derivable from the DEM), soil drainage class, geomorphology unit, and
rock type should be *weighted* into a vulnerability/stress score is a
methodology call worth making together rather than guessing at -- flag it
whenever you're ready to define that (e.g. "poor drainage adds +0.1 to
the score", "slope >15% adds +0.15") and we can wire it in.
