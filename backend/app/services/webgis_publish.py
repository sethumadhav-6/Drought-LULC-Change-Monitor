"""
"Publish for web" -- packages a computed layer or a finished timelapse
into a self-contained, static WebGIS bundle under WEBGIS_DIR/<publish_id>/
that the Canopy team can copy/upload as-is to a real website (e.g.
canopygs.in), with no dependency on this backend, GEE, or a database at
view time.

Why this is a separate thing from the live Map Layers panel: those layers
use ee.Image.getMapId() tile URLs, which are session/token-bound and not
meant for permanent public embedding (they can expire). This module
instead bakes a fixed snapshot plus a small standalone Leaflet
viewer.html that loads Leaflet from a CDN. Open viewer.html directly as a
file, or drop the whole folder onto any static web host -- it just works.

Two viewer modes, because the two source images are fundamentally
different:
  - "overlay" (analysis layers): a *raw* GEE thumbnail -- fetched via
    ee.Image.getThumbUrl() directly, bypassing matplotlib entirely -- so
    its pixel extent exactly matches the geographic `region` it was
    requested for, with masked/clipped-out areas left transparent. That's
    what makes a pixel-accurate image overlay possible. (Earlier versions
    of this module reused the annotated cartoee figure -- title/legend/
    north arrow baked in, cropped via bbox_inches='tight' -- as the overlay
    source; its cropped extent didn't match the bounds passed to the
    overlay, which showed up as a visible rectangular "box" misaligned
    against the real map. Title/legend are now rendered as HTML/CSS in the
    viewer instead of baked into the image.) The map itself is built with
    **folium** (github.com/python-visualization/folium) -- it wraps
    Leaflet.js server-side and produces a standalone HTML file with no
    runtime dependency on this backend, which is exactly what a published,
    permanently-hosted viewer needs. (folium's sibling libraries
    ipyleaflet/ipywidgets are Jupyter-kernel-dependent -- they need a live
    Python kernel talking to the page over a websocket -- so they can't
    produce a static file like this and aren't used here or anywhere else
    in this Flask app.)
  - "framed" (timelapse): the existing annotated cartoee frame (which
    *is* the intended deliverable -- a print-ready framed map) shown as a
    plain image, not forced into a geo-aligned overlay it was never
    rendered to fit exactly.
"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .geo_utils import flatten_bounds_ring, render_scale_for_region
from .indexes import INDEX_BY_CODE, S2_BANDS, default_vis_params

# Shared page chrome (dark theme matching the main dashboard) + the footer
# the branding now lives in -- moved out of a floating on-map overlay per
# explicit request; it sits in normal document flow below the map/frame,
# not on top of it.
_FOOTER_HTML = """
<footer style="background:#0d1319;color:#a8bcc4;text-align:center;
  padding:10px 14px;font-size:0.78rem;border-top:1px solid rgba(255,255,255,0.08);
  font-family:'Segoe UI',Arial,sans-serif;">
  Published by <strong style="color:#eef6f8;">Canopy Geospatial Solutions</strong>
  &middot; <a href="https://www.canopygs.in" style="color:#4ba3ff;">canopygs.in</a>
</footer>"""


def _fetch_raw_thumbnail(ee_image, region: list[float], dims: int, out_png: Path) -> None:
    """
    Fetch a GEE thumbnail directly via ee.Image.getThumbUrl() and save
    the raw bytes -- no matplotlib/cartoee involved, so nothing crops or
    resizes it after the fact. Its pixel extent exactly matches `region`
    (GEE's official getThumbURL region param accepts a flat
    [west, south, east, north] list directly), and masked/clipped pixels
    come back transparent (alpha channel), so overlaying it at the same
    `region` as an L.imageOverlay bounds is pixel-accurate.
    """
    import requests

    args = {"format": "png", "crs": "EPSG:4326", "region": region, "dimensions": dims}
    url = ee_image.getThumbUrl(args)
    resp = requests.get(url, timeout=90)
    if resp.status_code != 200:
        try:
            error = resp.json().get("error", resp.text)
        except Exception:  # noqa: BLE001
            error = resp.text
        raise ValueError(f"Earth Engine thumbnail request failed: {error}")
    out_png.write_bytes(resp.content)


def _legend_html(vis: dict) -> str:
    palette = ",".join(vis.get("palette", ["#a50026", "#ffffbf", "#1a9850"]))
    vmin, vmax = vis.get("min", -1), vis.get("max", 1)
    return f"""
    <div class="legend-ramp" style="background:linear-gradient(to right, {palette})"></div>
    <div class="legend-scale"><span>{vmin}</span><span>{vmax}</span></div>"""


def _title_box_html(title: str, legend_html: str, gif_note: str) -> str:
    return f"""
<style>
  .title-box {{
    position: absolute; top: 12px; left: 54px; z-index: 1000;
    background: rgba(16, 24, 32, 0.88); color: #eef6f8; padding: 8px 14px;
    border-radius: 6px; font-weight: 700; font-size: 0.95rem;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3); max-width: 260px;
    font-family: "Segoe UI", Arial, sans-serif;
  }}
  .title-box p {{ margin: 4px 0 0; font-weight: 400; font-size: 0.8rem; }}
  .title-box a {{ color: #4ba3ff; }}
  .legend-ramp {{ height: 10px; border-radius: 4px; margin: 6px 0 2px; border: 1px solid rgba(255,255,255,0.25); }}
  .legend-scale {{ display: flex; justify-content: space-between; font-size: 0.72rem; color: #a8bcc4; }}
</style>
<div class="title-box">{title}{legend_html}{gif_note}</div>"""


def _write_viewer_html_overlay(
    out_dir: Path, title: str, bounds: list[float], vis: dict | None, has_boundary: bool,
) -> None:
    """
    Geo-aligned analysis-layer viewer, built with folium (a real,
    actively-maintained wrapper around Leaflet.js that renders server-side
    to a standalone HTML file -- see module docstring for why folium and
    not ipyleaflet/ipywidgets here). bounds is [south, west, north, east].
    The PNG is embedded as a base64 data URI (folium's own behavior for a
    local file path) so viewer.html has no relative-file dependency even
    if someone moves it on its own -- map.png is still written alongside
    it too, for reference/manifest purposes.
    """
    import folium

    south, west, north, east = bounds
    center = [(south + north) / 2, (west + east) / 2]
    m = folium.Map(
        location=center, tiles="CartoDB positron", height="92vh", width="100%",
        control_scale=True, zoom_control=True,
    )
    folium.raster_layers.ImageOverlay(
        image=str(out_dir / "map.png"),
        bounds=[[south, west], [north, east]],
        opacity=0.85,
        name=title,
    ).add_to(m)
    if has_boundary:
        try:
            boundary_geojson = json.loads((out_dir / "boundary.geojson").read_text(encoding="utf-8"))
            folium.GeoJson(
                boundary_geojson, name="AOI boundary",
                style_function=lambda _f: {"color": "#0f5c30", "weight": 2, "fillOpacity": 0},
            ).add_to(m)
        except Exception:  # noqa: BLE001
            pass  # best-effort, same as before
    m.fit_bounds([[south, west], [north, east]])
    folium.LayerControl().add_to(m)

    legend_html = _legend_html(vis) if vis else ""
    m.get_root().html.add_child(folium.Element(_title_box_html(title, legend_html, "")))
    m.get_root().header.add_child(folium.Element(
        f'<title>{title} — Canopy GeoAI</title>'
        '<style>body{margin:0;background:#101820;}</style>'
    ))

    m.save(str(out_dir / "viewer.html"))
    # folium always puts its own map <div> last in <body>, so the footer
    # has to be spliced in after the fact to land *below* the map in
    # normal document flow rather than floating on top of it.
    html = (out_dir / "viewer.html").read_text(encoding="utf-8")
    html = html.replace("</body>", _FOOTER_HTML + "\n</body>")
    (out_dir / "viewer.html").write_text(html, encoding="utf-8")


def _write_viewer_html_framed(
    out_dir: Path, title: str, has_gif: bool,
) -> None:
    """Plain-image viewer for an already-framed/annotated timelapse PNG --
    not a georeferenced overlay (see module docstring)."""
    gif_note = '<p>An animated version is also included: <a href="timelapse.gif" target="_blank">timelapse.gif</a></p>' if has_gif else ""
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} — Canopy GeoAI</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body {{ margin: 0; height: 100%; font-family: "Segoe UI", Arial, sans-serif; background: #101820; color: #eef6f8; }}
  .page {{ display: flex; flex-direction: column; min-height: 100vh; }}
  .title-box {{
    position: absolute; top: 12px; left: 12px; z-index: 10;
    background: rgba(16, 24, 32, 0.88); padding: 8px 14px;
    border-radius: 6px; font-weight: 700; font-size: 0.95rem;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3); max-width: 260px;
  }}
  .title-box p {{ margin: 4px 0 0; font-weight: 400; font-size: 0.8rem; }}
  .title-box a {{ color: #4ba3ff; }}
  .framed-wrap {{ flex: 1; display: flex; align-items: center; justify-content: center; padding: 20px; box-sizing: border-box; }}
  .framed-wrap img {{ max-width: 100%; max-height: calc(100vh - 90px); box-shadow: 0 4px 24px rgba(0,0,0,0.4); border-radius: 4px; }}
</style>
</head>
<body>
<div class="page">
  <div class="title-box">{title}{gif_note}</div>
  <div class="framed-wrap"><img src="map.png" alt="{title}"></div>
  {_FOOTER_HTML}
</div>
</body>
</html>
"""
    (out_dir / "viewer.html").write_text(html, encoding="utf-8")


def _write_viewer_html(
    out_dir: Path, title: str, mode: str,
    bounds: list[float] | None = None, vis: dict | None = None,
    has_gif: bool = False, has_boundary: bool = False,
) -> None:
    """
    bounds is [south, west, north, east] or None. mode is "overlay"
    (geo-aligned, built with folium, needs bounds) or "framed" (plain
    image, bounds not used). Both write a self-contained viewer.html with
    no dependency on this backend/Flask/GEE at view time, and both put the
    "Canopy Geospatial Solutions" credit in a real footer below the
    content, not floating on top of the map/frame.
    """
    if mode == "overlay":
        _write_viewer_html_overlay(out_dir, title, bounds, vis, has_boundary)
    else:  # "framed"
        _write_viewer_html_framed(out_dir, title, has_gif)


def _write_manifest(out_dir: Path, **fields) -> None:
    fields["published_at"] = datetime.now(timezone.utc).isoformat()
    (out_dir / "manifest.json").write_text(json.dumps(fields, indent=2), encoding="utf-8")


def publish_analysis_layer(
    aoi_name: str,
    index_code: str,
    period: str,
    pre_start,
    pre_end,
    post_start,
    post_end,
    vis: dict | None = None,
) -> dict:
    """
    Render one Pre/Post composite (same computation as analysis.py's
    get_layer_tile) as a static, publishable WebGIS package instead of a
    live tile URL. Returns paths under WEBGIS_DIR/<publish_id>/.
    """
    from ..core import gee

    if not gee.is_available():
        raise ValueError("Publishing a layer requires the Google Earth Engine backend.")
    if index_code not in INDEX_BY_CODE:
        raise ValueError(f"Unknown index: {index_code}")
    if period not in ("pre", "post"):
        raise ValueError("period must be 'pre' or 'post'")

    from ..core.config import WEBGIS_DIR

    ee = gee.ee_module()
    idx_def = INDEX_BY_CODE[index_code]
    aoi = gee.kerala_boundary() if aoi_name.lower() == "kerala" else gee.kerala_districts().filter(
        ee.Filter.eq("ADM2_NAME", aoi_name)
    )
    geom = aoi.geometry()
    region = flatten_bounds_ring(geom.bounds().getInfo()["coordinates"][0])
    render_scale = render_scale_for_region(region)

    start, end = (pre_start, pre_end) if period == "pre" else (post_start, post_end)
    col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geom).filterDate(str(start), str(end))
    img = (
        col.map(lambda i: idx_def.fn(i.divide(10000), S2_BANDS).rename(index_code))
        .median()
        .clip(geom)
        .reproject(crs="EPSG:4326", scale=render_scale)
        .visualize(**(vis or default_vis_params(idx_def)))
    )

    vis = vis or default_vis_params(idx_def)
    title = f"{aoi_name} — {index_code} ({period}-monsoon)"

    publish_id = uuid.uuid4().hex[:10]
    out_dir = WEBGIS_DIR / publish_id
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        _fetch_raw_thumbnail(img, region, dims=1024, out_png=out_dir / "map.png")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "memory capacity exceeded" in msg.lower() or "503" in msg:
            raise ValueError(
                "Earth Engine ran out of memory rendering this layer. Try a smaller AOI "
                "(a single district instead of the whole state)."
            ) from exc
        raise ValueError(f"Could not render this layer for publishing: {msg}") from exc

    has_boundary = False
    try:
        boundary_geojson = geom.getInfo()
        (out_dir / "boundary.geojson").write_text(json.dumps(boundary_geojson), encoding="utf-8")
        has_boundary = True
    except Exception:  # noqa: BLE001
        pass  # best-effort -- missing the outline overlay shouldn't fail the publish

    west, south, east, north = region
    bounds = [south, west, north, east]
    _write_viewer_html(out_dir, title, mode="overlay", bounds=bounds, vis=vis, has_boundary=has_boundary)
    _write_manifest(
        out_dir, publish_id=publish_id, kind="analysis_layer", aoi_name=aoi_name,
        index_code=index_code, period=period, vis=vis, bounds=bounds, title=title,
    )

    return {
        "publish_id": publish_id,
        "dir": str(out_dir),
        "viewer_path": str(out_dir / "viewer.html"),
        "png_path": str(out_dir / "map.png"),
    }


def publish_timelapse(run_id: str, aoi_name: str | None = None) -> dict:
    """
    Package an already-generated timelapse run (see timelapse.py's
    generate_timelapse, which writes frames under
    TIMELAPSE_DIR/<run_id>/) into a static, publishable WebGIS bundle:
    the last frame as the map image, the GIF alongside it, and a
    standalone viewer.

    Bounds are approximated from the Kerala shapefile/AOI catalog (via
    core/aoi.py) rather than the exact GEE render region, since
    generate_timelapse doesn't currently return that -- close enough for
    a published overview map, called out in the manifest for transparency.
    """
    from ..core import aoi as aoi_module
    from ..core.config import TIMELAPSE_DIR, WEBGIS_DIR

    src_dir = TIMELAPSE_DIR / run_id
    if not src_dir.exists():
        raise ValueError(f"Timelapse run '{run_id}' not found.")
    frames = sorted(src_dir.glob("frame_*.png"))
    if not frames:
        raise ValueError(f"No frames found for timelapse run '{run_id}'.")
    last_frame = frames[-1]
    gif_path = src_dir / "timelapse.gif"

    out_dir = WEBGIS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(last_frame, out_dir / "map.png")
    has_gif = gif_path.exists()
    if has_gif:
        shutil.copy(gif_path, out_dir / "timelapse.gif")

    bounds = None
    if aoi_name:
        KERALA_BBOX = (74.86, 8.29, 77.42, 12.82)
        west, south, east, north = aoi_module.resolve_bbox(aoi_name, fallback=KERALA_BBOX)
        bounds = [south, west, north, east]

    title = f"Timelapse — {aoi_name}" if aoi_name else "Timelapse"
    # "framed" mode: the frame PNG already includes its own title/legend/
    # north-arrow/scale-bar (baked in by timelapse.py's render_frame_gee)
    # and was never rendered to fit an exact geographic bbox, so it's shown
    # as a plain image rather than forced into an L.imageOverlay -- avoids
    # the same box-misalignment issue publish_analysis_layer had.
    _write_viewer_html(out_dir, title, mode="framed", bounds=bounds, has_gif=has_gif, has_boundary=False)
    _write_manifest(
        out_dir, publish_id=run_id, kind="timelapse", aoi_name=aoi_name,
        bounds=bounds, title=title, source_frame=str(last_frame),
        bounds_note="approximated from the AOI catalog, not the exact GEE render region",
    )

    return {"publish_id": run_id, "dir": str(out_dir), "viewer_path": str(out_dir / "viewer.html")}
