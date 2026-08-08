"""
Canopy GeoAI -- single-process Python web app.

Drought + land-use/land-cover change monitoring for tropical
countries, piloted on Kerala, India. Built on the opengeos/geemap +
leafmap ecosystem (https://github.com/opengeos, https://github.com/giswqs)
for Sentinel-2/Landsat access, index computation, and cartographic
timelapse rendering -- all running in-process via Streamlit, so there's
no separate Node.js frontend, no CORS, and no second server to run.

Run:
    cd backend
    streamlit run streamlit_app.py

Admin queue: see pages/1_Admin.py (Streamlit auto-discovers it in the
sidebar nav).
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core import aoi as aoi_module  # noqa: E402
from app.core import gee  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db import crud  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.services.analysis import run_analysis  # noqa: E402
from app.services.drought import classify_vhi  # noqa: E402
from app.services.indexes import INDEX_CATALOG  # noqa: E402
from app.services.timelapse import generate_timelapse  # noqa: E402

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"

st.set_page_config(
    page_title="Canopy GeoAI",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "\U0001F30F",
    layout="wide",
)

init_db()

KERALA_DISTRICTS_FALLBACK = [
    "Thiruvananthapuram", "Kollam", "Pathanamthitta", "Alappuzha", "Kottayam",
    "Idukki", "Ernakulam", "Thrissur", "Palakkad", "Malappuram",
    "Kozhikode", "Wayanad", "Kannur", "Kasaragod",
]


def district_options() -> list[str]:
    names = aoi_module.district_names()
    return ["Kerala (whole state)"] + (names or KERALA_DISTRICTS_FALLBACK)


def normalize_aoi(choice: str) -> str:
    return "Kerala" if choice.startswith("Kerala") else choice


# --------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------- #
header_left, header_right = st.columns([1, 6])
with header_left:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=64)
with header_right:
    st.markdown(
        "### Canopy Geospatial Solutions\n"
        "**Canopy GeoAI** — Drought & LULC Change Monitor · Kerala Pilot · "
        "[www.canopygs.in](https://www.canopygs.in)"
    )

gee_ok = gee.is_available()
aoi_ok = aoi_module.is_available()
status_cols = st.columns(4)
status_cols[0].metric("Earth Engine", "Connected" if gee_ok else "Not configured")
status_cols[1].metric("Kerala boundary", "Shapefile" if aoi_ok else "Placeholder bbox")
status_cols[2].metric("Data sources", "Sentinel-2 + Landsat")
status_cols[3].metric("Indexes available", str(len(INDEX_CATALOG)))
if not gee_ok:
    st.info(
        "Google Earth Engine isn't configured, so Analysis will use the Microsoft Planetary "
        "Computer fallback and Timelapse generation is unavailable. See README.md to set up GEE.",
        icon="ℹ️",
    )

st.divider()

left, right = st.columns([2, 3])

# --------------------------------------------------------------------- #
# Left column: dataset / index selection + analysis + timelapse + request
# --------------------------------------------------------------------- #
with left:
    with st.expander("Sentinel-2 / Landsat dataset", expanded=True):
        data_source_label = st.radio(
            "Source",
            ["Sentinel-2 (10m, ~5-day revisit, no thermal band)", "Landsat 8/9 (30m, ~16-day revisit, has thermal band)"],
            label_visibility="collapsed",
        )
        data_source = "sentinel-2" if data_source_label.startswith("Sentinel") else "landsat"

    with st.expander("Indexes (indexdatabase.de + literature)", expanded=True):
        st.caption(
            "Standard indices, formulas per the [Index Database](https://www.indexdatabase.de/) "
            "and drought-monitoring literature (Gu 2007; Kogan 1995/1997)."
        )
        by_category: dict[str, list] = {}
        for idx in INDEX_CATALOG:
            by_category.setdefault(idx.category, []).append(idx)
        default_codes = {"NDVI", "NDWI", "NDDI"}
        selected_indexes: list[str] = []
        for cat, items in by_category.items():
            st.caption(cat.upper())
            for idx in items:
                checked = st.checkbox(
                    f"{idx.code} — {idx.name}",
                    value=idx.code in default_codes,
                    help=f"{idx.formula} · {idx.reference}",
                    key=f"idx_{idx.code}",
                )
                if checked:
                    selected_indexes.append(idx.code)

    with st.expander("Analysis (pre- vs post-monsoon)", expanded=False):
        area_choice = st.selectbox("Area", district_options(), key="analysis_area")
        c1, c2 = st.columns(2)
        pre_start = c1.date_input("Pre-monsoon start", date.today() - timedelta(days=365))
        pre_end = c1.date_input("Pre-monsoon end", date.today() - timedelta(days=300))
        post_start = c2.date_input("Post-monsoon start", date.today() - timedelta(days=90))
        post_end = c2.date_input("Post-monsoon end", date.today())

        if st.button("Run analysis", disabled=not selected_indexes):
            with st.spinner("Running analysis..."):
                try:
                    result = run_analysis(
                        aoi_name=normalize_aoi(area_choice),
                        data_source=data_source,
                        pre_start=pre_start,
                        pre_end=pre_end,
                        post_start=post_start,
                        post_end=post_end,
                        indexes=selected_indexes,
                    )
                    st.session_state["last_analysis"] = result
                except ValueError as exc:
                    st.error(str(exc))

        result = st.session_state.get("last_analysis")
        if result:
            st.caption(f"Source used: {result['source_used']}")
            rows = []
            for code, vals in result["stats"].items():
                if code == "drought_summary":
                    continue
                rows.append({
                    "Index": code,
                    "Pre-monsoon mean": round(vals["pre_mean"], 4) if vals["pre_mean"] is not None else None,
                    "Post-monsoon mean": round(vals["post_mean"], 4) if vals["post_mean"] is not None else None,
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
            drought = result["stats"].get("drought_summary")
            if drought:
                st.write(
                    f"**Drought summary** — NDDI: {drought.get('NDDI_mean')}"
                    + (f" · VHI: {drought['VHI_mean']} ({drought['VHI_class']})" if "VHI_mean" in drought else "")
                )

    with st.expander("Timelapse (graticule / north arrow / scale bar / legend)", expanded=False):
        if not gee_ok:
            st.warning("Requires Google Earth Engine credentials (see README.md).")
        tl_area = st.selectbox("Area", district_options(), key="tl_area")
        tl_index = st.selectbox("Index", ["NDVI", "NDDI", "NDWI"], key="tl_index")
        c1, c2, c3 = st.columns(3)
        tl_start = c1.date_input("Start", date(2019, 1, 1), key="tl_start")
        tl_end = c2.date_input("End", date.today(), key="tl_end")
        tl_step = c3.number_input("Step (months)", min_value=1, max_value=12, value=3, key="tl_step")

        if st.button("Generate timelapse", disabled=not gee_ok):
            progress = st.progress(0.0, text="Starting...")

            def on_frame(step, total, frame_path):
                progress.progress(min(step / total, 1.0), text=f"Rendered frame {step}/{total}")

            with st.spinner("Generating timelapse (this can take a while -- each frame is a real Earth Engine render)..."):
                try:
                    tl_result = generate_timelapse(
                        aoi_name=normalize_aoi(tl_area),
                        index_code=tl_index,
                        start=tl_start,
                        end=tl_end,
                        step_months=int(tl_step),
                        fps=1.0,
                        on_frame=on_frame,
                    )
                    st.session_state["last_timelapse"] = tl_result
                    progress.progress(1.0, text="Done")
                except ValueError as exc:
                    st.error(str(exc))

        tl_result = st.session_state.get("last_timelapse")
        if tl_result:
            st.success(f"Generated {tl_result['frame_count']} frames — run {tl_result['run_id']}")

    with st.expander("Need a dataset that isn't here? Request it", expanded=False):
        st.caption(
            "Can't self-serve this dataset? The Canopy technical team will evaluate, validate, "
            "and release both spatial and Excel outputs once confirmed."
        )
        with st.form("request_form", clear_on_submit=True):
            r_name = st.text_input("Your name")
            r_email = st.text_input("Email")
            r_org = st.text_input("Organization / Department")
            r_aoi = st.text_input("AOI (e.g. Idukki district)", value=normalize_aoi(area_choice))
            rc1, rc2 = st.columns(2)
            r_start = rc1.date_input("Window start", date.today(), key="req_start")
            r_end = rc2.date_input("Window end", date.today() + timedelta(days=30), key="req_end")
            r_purpose = st.text_area("Purpose / notes")
            submitted = st.form_submit_button("Request dataset")
            if submitted:
                if not (r_name and r_email and r_aoi):
                    st.error("Name, email, and AOI are required.")
                else:
                    db = SessionLocal()
                    try:
                        req = crud.create_request(db, {
                            "requester_name": r_name,
                            "requester_email": r_email,
                            "organization": r_org or None,
                            "aoi_name": r_aoi,
                            "data_source": data_source,
                            "indexes": selected_indexes,
                            "date_start": str(r_start),
                            "date_end": str(r_end),
                            "purpose": r_purpose or None,
                        })
                        st.success(f"Request {req.id} submitted (status: {req.status.value}). The Canopy technical team will review it.")
                    finally:
                        db.close()

# --------------------------------------------------------------------- #
# Right column: map + timelapse viewer / print view
# --------------------------------------------------------------------- #
with right:
    st.subheader("Map")
    try:
        import geopandas as gpd
        from streamlit_folium import st_folium

        if aoi_module.is_available():
            settings = get_settings()
            gdf = gpd.read_file(settings.kerala_shapefile_path)
            import folium

            centroid = gdf.geometry.union_all().centroid if hasattr(gdf.geometry, "union_all") else gdf.geometry.unary_union.centroid
            fmap = folium.Map(location=[centroid.y, centroid.x], zoom_start=8, tiles="CartoDB positron")
            highlight = normalize_aoi(st.session_state.get("tl_area", "Kerala"))
            for _, row in gdf.iterrows():
                name = str(row.get("NAME_2", ""))
                is_selected = highlight != "Kerala" and name.lower() == highlight.lower()
                folium.GeoJson(
                    row.geometry,
                    style_function=lambda _f, sel=is_selected: {
                        "fillColor": "#1a9850" if sel else "#a6d96a",
                        "color": "#0f5c30",
                        "weight": 2 if sel else 1,
                        "fillOpacity": 0.5 if sel else 0.15,
                    },
                    tooltip=name,
                ).add_to(fmap)
            st_folium(fmap, use_container_width=True, height=420, returned_objects=[])
        else:
            st.info("Kerala shapefile not found at the configured path -- showing a plain basemap. See docs/DATA_SOURCES.md.")
            import folium
            from streamlit_folium import st_folium

            fmap = folium.Map(location=[10.5, 76.2], zoom_start=8, tiles="CartoDB positron")
            st_folium(fmap, use_container_width=True, height=420, returned_objects=[])
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Map unavailable: {exc}")

    st.subheader("Latest timelapse")
    tl_result = st.session_state.get("last_timelapse")
    if tl_result:
        gif_path = Path(tl_result["gif_path"])
        if gif_path.exists():
            st.image(str(gif_path), caption=f"Run {tl_result['run_id']}", use_container_width=True)
            st.download_button("Download GIF", data=gif_path.read_bytes(), file_name=gif_path.name, mime="image/gif")
        frame_paths = [Path(p) for p in tl_result.get("frame_paths", [])]
        if frame_paths:
            last_frame = frame_paths[-1]
            with st.expander("Print view (latest frame, full size)"):
                st.image(str(last_frame), use_container_width=True)
                st.caption("Use your browser's Print (Ctrl/Cmd+P) on this page for a print-ready copy with graticule, north arrow, scale bar, and legend already baked in.")
    else:
        st.caption("Generate a timelapse on the left to see it here.")
