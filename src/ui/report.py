"""Briefing and exports derived from the active area and planner controls."""

import streamlit as st

from src.report import build_report


def render_report():
    st.header("Exposure briefing")
    if "planner_input" not in st.session_state:
        st.info(
            "Analyze a study area to prepare the briefing and downloads."
        )
        return
    request, season, cells = st.session_state.planner_input
    scheme = st.session_state.get("plan_scheme", "equal")
    count = st.session_state.get("plan_count", 10)
    percent = st.session_state.get("plan_percent", 25)
    saved = st.session_state.get("planner_result")
    scenario = (
        saved[1] if saved is not None and saved[0] == (scheme, count, percent) else None
    )
    drivers = st.session_state.get("driver_result")
    report = build_report(
        cells,
        request,
        season,
        scheme=scheme,
        top_n=count,
        percent=percent,
        model=drivers[2] if drivers else None,
        scenario=scenario,
    )
    for heading, paragraphs in report.sections:
        st.subheader(heading)
        for paragraph in paragraphs:
            st.text(paragraph)
    st.subheader("Downloads")
    for label, data, filename, mime in [
        ("Cell data (CSV)", report.csv, "exposure-cells.csv", "text/csv"),
        (
            "Cell polygons (GeoJSON)",
            report.geojson,
            "exposure-cells.geojson",
            "application/geo+json",
        ),
        ("Briefing (Markdown)", report.markdown, "exposure-brief.md", "text/markdown"),
        ("Briefing (HTML)", report.html, "exposure-brief.html", "text/html"),
    ]:
        st.download_button(
            label, data=data, file_name=filename, mime=mime, on_click="ignore"
        )
