"""Matched two-area comparisons of satellite observations."""

import streamlit as st

from src.demo import PRESETS, load_demo
from src.ui.drivers import _load_cells
from src.validate import validate_inputs

CUSTOM = "Custom coordinates"
def _choice(area, index):
    name = st.selectbox(area, [*PRESETS, CUSTOM], index=index)
    if name != CUSTOM:
        return name, *PRESETS[name][1:]
    lat = st.number_input(f"{area} latitude", -90.0, 90.0, 0.0, format="%.4f")
    lon = st.number_input(f"{area} longitude", -180.0, 180.0, 0.0, format="%.4f")
    return name, lat, lon


def _load(choice):
    name, lat, lon = choice
    if name in PRESETS:
        _, cells = load_demo(name)
    else:
        request = validate_inputs(
            lat=lat,
            lon=lon,
            radius_km=5,
            cell_size_m=500,
            start_year=2019,
            end_year=2021,
        )
        cells = _load_cells(request, "summer")
    return cells


def _mean(cells, field):
    valid = cells.dropna(subset=[field, "area_m2"])
    area = valid.area_m2.sum()
    return (valid[field] * valid.area_m2).sum() / area if area else float("nan")


def render_comparison():
    st.header("Compare two areas")
