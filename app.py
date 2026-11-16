from pathlib import Path

import streamlit as st

from src.ui.about import render_about
from src.ui.dashboard import render_story
from src.ui.comparison import render_comparison
from src.ui.equations import render_equations

st.set_page_config(page_title="Heat and air pollution planner", layout="wide")
st.html(Path(__file__).parent / "src/ui/theme.css")
page = st.radio(
    "Explore",
    ["Place story", "Compare two places", "Heat vs pollution"],
    horizontal=True,
    label_visibility="collapsed",
)
if page == "Heat vs pollution":
    render_equations()
else:
    place = render_story() if page == "Place story" else render_comparison()
    render_about(include_score=page == "Compare two places")
