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
    import matplotlib.pyplot as plt
    from geemap import cartoee

    fig = plt.figure(figsize=(10, 8))
    ax = cartoee.get_map(ee_image, region=region, vis_params=vis_params)

    cartoee.add_gridlines(ax, interval=[1, 1], linestyle=":")
    cartoee.add_north_arrow(ax, text="N", xy=(0.92, 0.9), arrow_length=0.08, text_color="black", arrow_color="black", fontsize=16)
    cartoee.add_scale_bar_lite(ax, length=scale_km, xy=(0.05, 0.05), linewidth=3, fontsize=10, color="black", unit="km")

    if legend_dict:
        cartoee.add_legend(ax, legend_dict=legend_dict, loc="lower right", fontsize=9)

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
