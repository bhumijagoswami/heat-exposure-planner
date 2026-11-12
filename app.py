from pathlib import Path

import streamlit as st

from src.ui.dashboard import render_story
from src.ui.comparison import render_comparison

st.set_page_config(page_title="Heat and air pollution planner", layout="wide")
st.html(Path(__file__).parent / "src/ui/theme.css")
page = st.radio(
    "Explore",
    ["Place story", "Compare two places"],
    horizontal=True,
    label_visibility="collapsed",
)
if page == "Place story":
    render_story()
else:
    render_comparison()
with st.expander("About and limits"):
    st.write(
        "We give surface heat, air pollution and lack of greenery equal weight, then give more weight to places with more residents. The four colours split the local score into quarters. Very high starts at 0.75 on a scale of 0 to 1."
    )
    st.write(
        "Satellites measure ground surface temperature. The air you feel can be cooler or warmer. Nitrogen dioxide readings cover several kilometres and describe the whole column of air above the ground. Clouds can leave gaps, and population estimates date to 2020."
    )
    st.write(
        "Planting estimates are not guarantees. Airport grounds, runways and roads can look open from space. Check land use, safety boundaries and permission before planting."
    )
