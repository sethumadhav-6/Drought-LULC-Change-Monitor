"""
Timelapse + print-ready cartographic frame generator.

GEE path uses geemap's `cartoee` module (built on cartopy), which is
the standard opengeos/giswqs toolkit for exactly this: satellite
timelapses annotated with a graticule, north arrow, scale bar, and
legend, suitable for print/PDF handoff to a state official.

Reference: geemap cartoee docs (https://geemap.org/cartoee/,
"GEE Tutorial #52 - custom projection, scale bar, and north arrow",
https://blog.gishub.org/gee-tutorial-52-...).
"""
from __future__ import annotations

from pathlib import Path

# Force a non-interactive backend before any pyplot import happens anywhere
# in this process. Running behind a web server (no display attached), the
# default matplotlib backend on Windows can try to use an interactive GUI
# toolkit (Tk/Qt), which is unreliable headless and can crash the worker
# mid-request -- which surfaces to the browser as a bare "NetworkError"
# rather than a proper HTTP error.
import matplotlib

matplotlib.use("Agg")


def render_frame_gee(
    ee_image,
    region,
    vis_params: dict,
    out_png: Path,
    title: str,
    legend_dict: dict | None = None,
    scale_km: float = 10,
) -> Path:
    """
    Render one cartographic frame (PNG) from an ee.Image using
    geemap.cartoee: adds gridlines (graticule), a north arrow, a
    scale bar, and an optional legend. This is the print-ready frame
    used both for a single index snapshot and as one frame of a
    timelapse sequence.
    """
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    from geemap import cartoee

    fig = plt.figure(figsize=(10, 8))
    ax = cartoee.get_map(ee_image, region=region, vis_params=vis_params)

    cartoee.add_gridlines(ax, interval=[1, 1], linestyle=":")
    cartoee.add_north_arrow(ax, text="N", xy=(0.92, 0.9), arrow_length=0.08, text_color="black", arrow_color="black", fontsize=16)
    cartoee.add_scale_bar_lite(ax, length=scale_km, xy=(0.05, 0.05), linewidth=3, fontsize=10, color="black", unit="km")

    if legend_dict:
        # The installed geemap version's cartoee.add_legend() takes
        # `legend_elements` (a list of matplotlib legend handles), not a
        # `legend_dict` -- passing legend_dict falls through **kwargs
        # straight into ax.legend(), which doesn't recognize it and raises
        # TypeError. Build the handles ourselves from the label->color dict.
        legend_elements = [
            mpatches.Patch(facecolor=color, edgecolor="black", label=label)
            for label, color in legend_dict.items()
        ]
        cartoee.add_legend(ax, legend_elements=legend_elements, loc="lower right", font_size=9)

    ax.set_title(title, fontsize=14)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_png


def render_frame_local(
    rgb_or_index_array,
    transform,
    crs,
    out_png: Path,
    title: str,
    legend_items: list[tuple[str, str]] | None = None,
    cmap: str = "RdYlGn",
    vmin: float | None = None,
    vmax: float | None = None,
) -> Path:
    """
    Same cartographic frame (graticule + north arrow + scale bar +
    legend), but for the Planetary Computer / local-raster path where
    we have a numpy array + affine transform + CRS instead of an
    ee.Image. Uses matplotlib + cartopy directly.
    """
    import cartopy.crs as ccrs
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    import numpy as np
    import rasterio.plot as rioplot
    from matplotlib.patches import FancyArrow
    from matplotlib_scalebar.scalebar import ScaleBar

    fig, ax = plt.subplots(figsize=(10, 8), subplot_kw={"projection": ccrs.PlateCarree()})

    extent = rioplot.plotting_extent(np.squeeze(rgb_or_index_array), transform)
    im = ax.imshow(
        np.squeeze(rgb_or_index_array), extent=extent, origin="upper",
        cmap=cmap, vmin=vmin, vmax=vmax, transform=ccrs.PlateCarree(),
    )

    gl = ax.gridlines(draw_labels=True, linestyle=":", color="gray", alpha=0.6)
    gl.top_labels = False
    gl.right_labels = False

    ax.add_artist(FancyArrow(0.94, 0.82, 0, 0.08, width=0.01, transform=ax.transAxes, color="black"))
    ax.text(0.94, 0.92, "N", transform=ax.transAxes, ha="center", fontsize=14, fontweight="bold")

    ax.add_artist(ScaleBar(1, units="m", location="lower left", box_alpha=0.6))

    if legend_items:
        handles = [mpatches.Patch(color=c, label=lbl) for lbl, c in legend_items]
        ax.legend(handles=handles, loc="lower right", fontsize=9, framealpha=0.85)

    ax.set_title(title, fontsize=14)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_png


def build_gif(frame_paths: list[Path], out_gif: Path, fps: float = 1.0) -> Path:
    """Assemble rendered PNG frames into an animated GIF timelapse."""
    import imageio.v3 as iio

    frames = [iio.imread(p) for p in frame_paths]
    out_gif.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(out_gif, frames, duration=1000 / fps, loop=0)
    return out_gif


def build_mp4(frame_paths: list[Path], out_mp4: Path, fps: float = 1.0) -> Path:
    """Assemble rendered PNG frames into an MP4 timelapse (needs imageio-ffmpeg)."""
    import imageio.v3 as iio

    frames = [iio.imread(p) for p in frame_paths]
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(out_mp4, frames, fps=fps, codec="libx264")
    return out_mp4


# Simple diverging palettes tuned per index category; extend as needed.
VIS_PARAMS = {
    "NDVI": {"min": -0.2, "max": 0.9, "palette": ["#a50026", "#ffffbf", "#1a9850"]},
    "NDDI": {"min": -0.5, "max": 0.5, "palette": ["#1a9850", "#ffffbf", "#a50026"]},
    "NDWI": {"min": -0.5, "max": 0.5, "palette": ["#a50026", "#ffffbf", "#3288bd"]},
}


def _add_months(d, months: int):
    from datetime import date as _date

    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, 28)
    return _date(y, m, day)


def generate_timelapse(
    aoi_name: str,
    index_code: str,
    start,
    end,
    step_months: int = 1,
    fps: float = 1.0,
    on_frame=None,
) -> dict:
    """
    Generate a full cartographic timelapse (GEE path only) for `aoi_name`
    ("Kerala" for the whole state, or an exact Kerala district name) and
    `index_code` between `start` and `end` (datetime.date), stepping by
    `step_months`. Framework-agnostic -- both the FastAPI route
    (api/routes_timelapse.py) and the Streamlit app call this directly,
    so there is exactly one implementation to maintain and debug.

    `on_frame(step, total_estimate, frame_path)` is called after each
    frame renders, if given -- lets a caller show progress (e.g. a
    Streamlit progress bar) without this module knowing about Streamlit.

    Raises ValueError for bad input (unknown index, AOI not found, GEE
    unavailable, or a date range that produces zero frames).
    """
    import uuid

    from ..core import gee
    from ..core.config import TIMELAPSE_DIR
    from .indexes import INDEX_BY_CODE, S2_BANDS

    if index_code not in INDEX_BY_CODE:
        raise ValueError(f"Unknown index: {index_code}")
    if not gee.is_available():
        raise ValueError(
            "Timelapse generation currently requires the Google Earth Engine backend "
            "(geemap/cartoee). Configure GEE credentials, or request an admin-generated "
            "dataset instead."
        )

    ee = gee.ee_module()
    idx_def = INDEX_BY_CODE[index_code]
    aoi_name = aoi_name.strip()
    if aoi_name.lower() in ("kerala", "kerala (state)"):
        aoi = gee.kerala_boundary()
    else:
        aoi = gee.kerala_districts().filter(ee.Filter.eq("ADM2_NAME", aoi_name))
        if aoi.size().getInfo() == 0:
            raise ValueError(
                f"AOI '{aoi_name}' not found among Kerala districts (GEE FAO GAUL names). "
                "Use the exact district name from the AOI catalog, or 'Kerala' for the whole state."
            )
    geom = aoi.geometry()
    # cartoee.get_map() passes `region` straight into ee.Geometry.Rectangle(),
    # which needs a flat [west, south, east, north] bbox -- NOT the nested
    # polygon ring that geom.bounds().getInfo()["coordinates"] returns (a
    # closed 5-point ring: [[[w,s],[w,n],[e,n],[e,s],[w,s]]]). Passing the
    # ring straight through causes `ee.ee_exception.EEException: Invalid
    # geometry.` inside cartoee.add_layer(). Flatten it to a bbox instead.
    bounds_ring = geom.bounds().getInfo()["coordinates"][0]
    lons = [pt[0] for pt in bounds_ring]
    lats = [pt[1] for pt in bounds_ring]
    region = [min(lons), min(lats), max(lons), max(lats)]

    frames: list[Path] = []
    run_id = uuid.uuid4().hex[:10]
    out_dir = TIMELAPSE_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cur = start
    step = 0
    total_estimate = max(1, (end.year - start.year) * 12 // step_months + 1)
    vis = VIS_PARAMS.get(index_code, {"min": -1, "max": 1, "palette": ["#a50026", "#ffffbf", "#1a9850"]})
    legend = {"Low": vis["palette"][0], "Mid": vis["palette"][1], "High": vis["palette"][-1]}

    while cur < end:
        nxt = _add_months(cur, step_months)
        col = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geom)
            .filterDate(str(cur), str(min(nxt, end)))
        )
        img = col.map(lambda i: idx_def.fn(i.divide(10000), S2_BANDS).rename(index_code)).median().clip(geom)
        out_png = out_dir / f"frame_{step:03d}.png"
        render_frame_gee(
            img, region, vis, out_png,
            title=f"{aoi_name} - {index_code} - {cur.isoformat()}",
            legend_dict=legend,
        )
        frames.append(out_png)
        if on_frame:
            on_frame(step + 1, total_estimate, out_png)
        cur = nxt
        step += 1

    if not frames:
        raise ValueError("Date range produced no frames; widen start/end.")

    gif_path = out_dir / "timelapse.gif"
    build_gif(frames, gif_path, fps=fps)
    return {
        "run_id": run_id,
        "frame_count": len(frames),
        "gif_path": gif_path,
        "frame_paths": frames,
    }
