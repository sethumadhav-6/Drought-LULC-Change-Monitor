"""
Admin queue: review dataset requests, approve/reject, and release
validated deliverables (spatial + Excel) to the requester.

MVP-level auth: a single admin account (Settings.admin_username /
admin_password), checked directly against the DB session -- no HTTP
token/session layer needed since this runs in the same Streamlit
process as streamlit_app.py. Change the credentials in backend/.env
before sharing this beyond your own testing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db import crud  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import RequestStatus  # noqa: E402

st.set_page_config(page_title="Canopy GeoAI — Admin", layout="wide")
init_db()

settings = get_settings()

if "admin_user" not in st.session_state:
    st.session_state["admin_user"] = None


def login_view():
    st.title("Admin Login")
    st.caption("Canopy Geospatial Solutions — dataset request review queue.")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
        if submitted:
            if username == settings.admin_username and password == settings.admin_password:
                st.session_state["admin_user"] = username
                st.rerun()
            else:
                st.error("Invalid username or password.")


def queue_view():
    st.title("Admin — Dataset Request Queue")
    col1, col2 = st.columns([5, 1])
    col1.caption(f"Logged in as **{st.session_state['admin_user']}**")
    if col2.button("Log out"):
        st.session_state["admin_user"] = None
        st.rerun()

    status_filter = st.selectbox(
        "Filter by status", ["(all)"] + [s.value for s in RequestStatus], index=0
    )

    db = SessionLocal()
    try:
        reqs = crud.list_requests(db, None if status_filter == "(all)" else status_filter)
        if not reqs:
            st.info("No requests match this filter.")
            return

        for req in reqs:
            with st.expander(
                f"{req.aoi_name} — {req.requester_name} ({req.status.value}) — {req.created_at:%Y-%m-%d %H:%M}"
            ):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**Requester:** {req.requester_name} ({req.requester_email})")
                    st.write(f"**Organization:** {req.organization or '—'}")
                    st.write(f"**AOI:** {req.aoi_name}")
                    st.write(f"**Data source:** {req.data_source}")
                with c2:
                    st.write(f"**Indexes:** {', '.join(req.indexes or [])}")
                    st.write(f"**Window:** {req.date_start} → {req.date_end}")
                    st.write(f"**Purpose:** {req.purpose or '—'}")
                    st.write(f"**Status:** {req.status.value}")
                if req.admin_notes:
                    st.write(f"**Admin notes:** {req.admin_notes}")

                notes = st.text_input("Notes (optional)", key=f"notes_{req.id}")
                bcol1, bcol2, bcol3 = st.columns(3)

                if req.status == RequestStatus.requested or req.status == RequestStatus.under_review:
                    if bcol1.button("Approve", key=f"approve_{req.id}"):
                        crud.set_status(db, req.id, RequestStatus.approved, notes or None, st.session_state["admin_user"])
                        st.rerun()
                    if bcol2.button("Reject", key=f"reject_{req.id}"):
                        crud.set_status(db, req.id, RequestStatus.rejected, notes or None, st.session_state["admin_user"])
                        st.rerun()

                if req.status == RequestStatus.approved:
                    st.markdown("**Release deliverables** (paths to files already generated via the Analysis/Timelapse tools on the main page):")
                    excel_path = st.text_input("Excel report path", key=f"excel_{req.id}")
                    spatial_path = st.text_input("Spatial export path (GeoTIFF/GeoPackage)", key=f"spatial_{req.id}")
                    timelapse_path = st.text_input("Timelapse GIF/MP4 path", key=f"tl_{req.id}")
                    if bcol3.button("Validate & Release", key=f"release_{req.id}"):
                        crud.attach_results(db, req.id, excel_path or None, spatial_path or None, timelapse_path or None)
                        crud.set_status(db, req.id, RequestStatus.released, notes or None, st.session_state["admin_user"])
                        st.success("Released.")
                        st.rerun()

                if req.status == RequestStatus.released:
                    st.success("Released to requester.")
                    if req.result_excel_path:
                        st.write(f"Excel: `{req.result_excel_path}`")
                    if req.result_spatial_path:
                        st.write(f"Spatial: `{req.result_spatial_path}`")
                    if req.result_timelapse_path:
                        st.write(f"Timelapse: `{req.result_timelapse_path}`")
    finally:
        db.close()


if st.session_state["admin_user"]:
    queue_view()
else:
    login_view()
