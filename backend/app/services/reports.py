"""
Report builder: turns analysis results into the two deliverables an
official can hand off -- an Excel workbook (district-level stats,
drought/LULC change table, flags) and spatial exports (GeoTIFF for
index rasters, GeoPackage/Shapefile for LULC change polygons) -- plus
a print-ready PDF summary combining the cartographic timelapse frame
with the same tables.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill

HEADER_FILL = PatternFill(start_color="1A9850", end_color="1A9850", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def build_excel_report(
    out_xlsx: Path,
    aoi_name: str,
    period_pre: tuple[str, str],
    period_post: tuple[str, str],
    district_stats: list[dict],
    change_matrix_df,
    shrinkage_flags: list[dict],
    generated_on: date | None = None,
) -> Path:
    """
    district_stats: list of dicts like
        {"district": "Idukki", "NDVI_pre": .61, "NDVI_post": .48,
         "NDDI_pre": -.12, "NDDI_post": .05, "VHI_post": 28.4,
         "forest_loss_ha": 340.2}
    """
    generated_on = generated_on or date.today()
    wb = Workbook()

    # --- Summary sheet ---
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Canopy GeoAI - Drought & LULC Change Report"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["AOI", aoi_name])
    ws.append(["Pre-monsoon window", f"{period_pre[0]} to {period_pre[1]}"])
    ws.append(["Post-monsoon window", f"{period_post[0]} to {period_post[1]}"])
    ws.append(["Generated on", generated_on.isoformat()])
    ws.append([])
    ws.append(["Early-warning flags (shrinkage watch list)"])
    ws["A7"].font = Font(bold=True)
    ws.append(["From class", "To class", "Area (ha)", "Note"])
    for cell in ws[8]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for flag in shrinkage_flags:
        ws.append([flag["from"], flag["to"], flag["area_ha"], flag["note"]])
    for col, width in zip("ABCD", (26, 22, 14, 70)):
        ws.column_dimensions[col].width = width

    # --- District stats sheet ---
    ws2 = wb.create_sheet("District Stats")
    if district_stats:
        headers = list(district_stats[0].keys())
        ws2.append(headers)
        for cell in ws2[1]:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
        for row in district_stats:
            ws2.append([row.get(h) for h in headers])
        for i, _ in enumerate(headers, start=1):
            ws2.column_dimensions[ws2.cell(row=1, column=i).column_letter].width = 16

        if "district" in headers and "NDVI_post" in headers:
            chart = BarChart()
            chart.title = "Post-monsoon NDVI by district"
            chart.y_axis.title = "NDVI"
            n = len(district_stats)
            data = Reference(ws2, min_col=headers.index("NDVI_post") + 1, min_row=1, max_row=n + 1)
            cats = Reference(ws2, min_col=headers.index("district") + 1, min_row=2, max_row=n + 1)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(cats)
            ws2.add_chart(chart, "J2")

    # --- Change matrix sheet ---
    ws3 = wb.create_sheet("LULC Change Matrix (ha)")
    ws3.append(["From \\ To"] + list(change_matrix_df.columns))
    for cell in ws3[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for idx, row in change_matrix_df.iterrows():
        ws3.append([idx] + list(row.values))

    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_xlsx)
    return out_xlsx


def export_geotiff(array, transform, crs, out_path: Path, nodata=None) -> Path:
    """Write a single/multi-band numpy array to a GeoTIFF for GIS handoff."""
    import numpy as np
    import rasterio

    arr = np.atleast_3d(array) if array.ndim == 2 else array
    count, height, width = (1, *array.shape) if array.ndim == 2 else array.shape
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path, "w", driver="GTiff", height=height, width=width, count=count,
        dtype=str(array.dtype), crs=crs, transform=transform, nodata=nodata, compress="deflate",
    ) as dst:
        if array.ndim == 2:
            dst.write(array, 1)
        else:
            for i in range(count):
                dst.write(array[i], i + 1)
    return out_path


def export_change_vectors(class_array, transform, crs, out_gpkg: Path, legend: dict) -> Path:
    """Polygonize an LULC/change class raster to a GeoPackage layer for GIS use."""
    import geopandas as gpd
    import numpy as np
    from rasterio.features import shapes
    from shapely.geometry import shape

    mask = ~np.isnan(class_array) if class_array.dtype.kind == "f" else None
    geoms, values = [], []
    for geom, val in shapes(class_array.astype("int32"), mask=mask, transform=transform):
        geoms.append(shape(geom))
        values.append(int(val))
    gdf = gpd.GeoDataFrame(
        {"class_id": values, "label": [legend.get(v, {}).get("label", "unknown") for v in values]},
        geometry=geoms, crs=crs,
    )
    out_gpkg.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_gpkg, driver="GPKG")
    return out_gpkg
