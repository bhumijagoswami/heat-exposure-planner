import streamlit as st

from src.ui.drivers import render_drivers

st.set_page_config(page_title="Heat & Air Pollution Exposure Planner")
with st.tabs(["Drivers"])[0]:
    render_drivers()
