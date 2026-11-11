import streamlit as st

from src.ui.drivers import render_drivers
from src.ui.planner import render_planner
from src.ui.trends import render_trends

st.set_page_config(page_title="Heat & Air Pollution Exposure Planner")
drivers, planner, trends = st.tabs(["Drivers", "Action Plan", "Trends"])
with drivers:
    render_drivers()
with planner:
    render_planner()
with trends:
    render_trends()
