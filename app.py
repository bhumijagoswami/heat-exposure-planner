from pathlib import Path

import streamlit as st

from src.ui.dashboard import (
    LIVE,
    render_map,
    render_methodology,
    render_overview,
    select_area,
)
from src.ui.drivers import render_drivers
from src.ui.planner import render_planner
from src.ui.report import render_report
from src.ui.trends import render_trends

st.set_page_config(page_title="Heat & air pollution exposure planner", layout="wide")
st.html(Path(__file__).parent / "src/ui/theme.css")
source = select_area()
st.title("Heat & air pollution exposure planner")
overview, grid, drivers, trends, planner, report, methods = st.tabs(
    [
        "Overview",
        "Map",
        "Drivers",
        "Trends",
        "Action Plan",
        "Briefing",
        "Methodology & Limits",
    ]
)
with overview:
    render_overview(source)
with grid:
    render_map()
with drivers:
    render_drivers()
with trends:
    render_trends(offline=source != LIVE)
with planner:
    render_planner()
with report:
    render_report()
with methods:
    render_methodology()
