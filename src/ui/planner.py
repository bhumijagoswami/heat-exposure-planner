"""Action Plan tab for the current analysis area."""

import logging

import streamlit as st

from .limits import begin_compute

from src.zones import zone_directory, hotspot_level
from src.index import SCHEMES
from src.planner import MAX_SITES, estimate_scenario, rank_sites


def render_planner():
    st.header("Intervention planner")
    if "planner_input" not in st.session_state:
        st.info("Analyze a study area to rank planting sites.")
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
        key="plan_scheme",
        format_func=lambda name: name.replace("_", " ").title(),
    )
    count = st.number_input("Number of sites", 1, MAX_SITES, 10, key="plan_count")
    sites = rank_sites(cells, scheme, count)
    if sites.empty:
        st.info("No scored cells in this area meet the planting criteria.")
        return
    st.caption(
        "Cumulative coverage is the share of summed hotspot scores across all scored cells in the area."
    )
    zones = zone_directory(cells)
    display_sites = zones.loc[sites.index].join(sites)
    display_sites["Level"] = display_sites.exposure.map(hotspot_level)
    links = {"Google Maps": st.column_config.LinkColumn(display_text="Open map")}
    st.dataframe(
        display_sites.rename(
            columns={
                "area_m2": "Cell area (m²)",
                "dw_frac_bare": "Bare fraction",
                "dw_frac_trees": "Tree fraction",
                "open_fraction": "Plantable cover fraction",
                "exposure": "Hotspot score",
                "cumulative_exposure_pct": "Cumulative exposure covered (%)",
            }
        ),
        hide_index=True,
        column_config=links,
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
        "Share of existing bare cover converted to trees (%)",
        0,
        100,
        25,
        key="plan_percent",
    )
    key = (scheme, count, percent)
    saved = st.session_state.get("planner_result")
    if st.button("Estimate temperature change") and (saved is None or saved[0] != key):
        if not begin_compute():
            return
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
            zones.loc[saved[1].index]
            .join(saved[1])
            .rename(
                columns={
                    "converted_m2": "Converted area (m²)",
                    "delta_c": "ΔLST (°C)",
                    "lower_c": "95% lower (°C)",
                    "upper_c": "95% upper (°C)",
                }
            ),
            hide_index=True,
            column_config=links,
        )
        if saved[1].delta_c.isna().any():
            st.caption(
                "Blank temperature estimates indicate missing driver inputs for that cell."
            )
