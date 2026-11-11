import streamlit as st

from src.ui.drivers import render_drivers
from src.ui.planner import render_planner

st.set_page_config(page_title="Heat & Air Pollution Exposure Planner")
drivers, planner = st.tabs(["Drivers", "Action Plan"])
with drivers:
    render_drivers()
with planner:
    render_planner()
