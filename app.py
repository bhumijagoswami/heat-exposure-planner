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
grid, overview, drivers, trends, planner, report, methods = st.tabs(
    [
        "Map",
        "Overview",
        "Drivers",
        "Trends",
        "Action Plan",
        "Briefing",
        "Methodology & Limits",
    ]
)
with overview:
    st.info(
        "**How to read this** · Start with coverage to see how much of the area could be scored, then look at the highest-scoring zones."
    )
    render_overview(source)
with grid:
    st.info(
        "**How to read this** · Choose a layer and click a zone for its readings and location. Hotspot scores combine heat, pollution, limited greenery and population."
    )
    render_map()
with drivers:
    st.info(
        "**How to read this** · See which landscape features the model associates with warmer or cooler surfaces, then explore one zone."
    )
    render_drivers()
with trends:
    st.info(
        "**How to read this** · Compare monthly readings with the line that removes the usual seasonal cycle. Gaps indicate missing observations."
    )
    render_trends(offline=source != LIVE)
with planner:
    st.info(
        "**How to read this** · Start with the highest-ranked candidates, then explore how adding trees could change surface temperature."
    )
    render_planner()
with report:
    st.info(
        "**How to read this** · Read the findings for the selected area or download the figures behind them."
    )
    render_report()
with methods:
    st.info(
        "**How to read this** · Use this guide to understand the scores, the satellite measurements and their limits."
    )
    render_methodology()
