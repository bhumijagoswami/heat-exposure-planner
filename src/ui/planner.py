"""Action Plan tab for the current analysis area."""

import logging
from time import monotonic

import streamlit as st

from src.index import SCHEMES
from src.planner import MAX_SITES, estimate_scenario, rank_sites


def render_planner():
    st.header("Intervention planner")
    if "planner_input" not in st.session_state:
        st.info("Run an area analysis in Drivers to rank planting sites.")
        return
    request, season, cells = st.session_state.planner_input
    st.caption(
        f"{request.lat:.4f}°, {request.lon:.4f}° · {request.radius_km:g} km radius · "
        f"{season}, {request.start_year}–{request.end_year}"
    )
    st.write(
        "Screening requires at least 1 ha of cell area, at least 25% bare, shrub or grass cover, "
        "zero classified water and less than 50% built cover."
    )
    scheme = st.selectbox(
        "Exposure weighting",
        list(SCHEMES),
        format_func=lambda name: name.replace("_", " ").title(),
    )
    count = st.number_input("Number of sites", 1, MAX_SITES, 10)
    sites = rank_sites(cells, scheme, count)
    if sites.empty:
        st.info("No scored cells in this area meet the planting criteria.")
        return
    st.caption(
        "Cumulative coverage is the share of summed exposure scores across all scored cells in the area."
    )
    st.dataframe(
        sites.rename(
            columns={
                "area_m2": "Cell area (m²)",
                "dw_frac_bare": "Bare fraction",
                "dw_frac_trees": "Tree fraction",
                "open_fraction": "Plantable cover fraction",
                "exposure": "Exposure score",
                "cumulative_exposure_pct": "Cumulative exposure covered (%)",
            }
        )
    )
    if "driver_result" not in st.session_state:
        st.info("Temperature scenarios require a fitted driver model for this area.")
        return
    st.subheader("Bare-to-tree scenario")
    st.caption(
        "Model-based, indicative, not causal. Other predictors stay fixed. "
        "Negative ΔLST indicates lower predicted surface temperature. "
        "The 95% interval comes from 100 spatial block bootstrap refits."
    )
    percent = st.slider(
        "Share of existing bare cover converted to trees (%)", 0, 100, 25
    )
    key = (scheme, count, percent)
    saved = st.session_state.get("planner_result")
    if st.button("Estimate temperature change") and (saved is None or saved[0] != key):
        now = monotonic()
        last = st.session_state.get("scenario_last_run")
        if last is not None and now - last < 10:
            st.warning("Allow 10 seconds between scenario estimates.")
            return
        st.session_state.scenario_last_run = now
        try:
            with st.spinner("Estimating temperature changes and bootstrap intervals…"):
                result = estimate_scenario(
                    st.session_state.driver_result[2], sites, percent
                )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Scenario estimation failed (%s)", type(exc).__name__
            )
            st.error("The temperature scenario could not finish. Please retry.")
            return
        saved = (key, result)
        st.session_state.planner_result = saved
    if saved is not None and saved[0] == key:
        st.dataframe(
            saved[1].rename(
                columns={
                    "converted_m2": "Converted area (m²)",
                    "delta_c": "ΔLST (°C)",
                    "lower_c": "95% lower (°C)",
                    "upper_c": "95% upper (°C)",
                }
            )
        )
        if saved[1].delta_c.isna().any():
            st.caption(
                "Blank temperature estimates indicate missing driver inputs for that cell."
            )
