"""Matched two-area comparisons of satellite observations."""

import pandas as pd
from src.ui.limits import begin_compute
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
    st.caption(
        "Both places use summer 2019–2021 readings within 5 km, divided into 500 m zones."
    )
    choices = []
    for index, column in enumerate(st.columns(2)):
        with column:
            choices.append(_choice(("Place A", "Place B")[index], index))
    custom = any(choice[0] == CUSTOM for choice in choices)
    if custom:
        if st.button("Compare places") and begin_compute():
            try:
                st.session_state.comparison = (
                    choices,
                    [_load(choice) for choice in choices],
                )
            except Exception:
                st.error(
                    "Could not load both places. Check the coordinates and live connection."
                )
                return
        saved = st.session_state.get("comparison")
        if not saved or saved[0] != choices:
            return
        pair = saved[1]
    else:
        pair = [_load(choice) for choice in choices]
    temps = [_mean(cells, "lst_c") for cells in pair]
    if all(pd.notna(temps)):
        gap = temps[0] - temps[1]
        st.info(
            "Both places had similar average surface temperatures."
            if abs(gap) < 0.05
            else f"Place {'A' if gap > 0 else 'B'} averaged {abs(gap):.1f} °C hotter at the surface."
        )
    for index, (column, cells) in enumerate(zip(st.columns(2), pair)):
        with column:
            label, lat, lon = choices[index]
            st.subheader(label if label != CUSTOM else f"{lat:.3f}°, {lon:.3f}°")
            for field, title, scale, unit in [
                ("lst_c", "Surface temperature", 1, "°C"),
                ("no2_mol_m2", "Nitrogen dioxide", 1_000_000, "µmol/m²"),
                ("dw_frac_trees", "Tree cover", 100, "%"),
            ]:
                value = _mean(cells, field) * scale
                st.metric(
                    title, f"{value:.1f} {unit}" if pd.notna(value) else "No readings"
                )
    st.caption("Area-weighted averages from Landsat, Sentinel-5P and Dynamic World.")
