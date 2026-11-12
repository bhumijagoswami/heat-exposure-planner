"""Shared study-area selection, exposure map, overview and scientific limits."""

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from shapely.geometry import mapping

from src.zones import NO2_TO_MICROMOLES, hotspot_level, zone_directory
from src.demo import PRESETS, load_demo
from src.index import score_exposure
from src.model import fit_drivers
from src.ui.basemap import render_grid_map
from src.ui.drivers import render_area_form

LIVE = "Custom live analysis"
LAYERS = {
    "Hotspot score": (
        "exposure_equal",
        "Score (0–1)",
        "Equal-weight index · Landsat, Sentinel-5P, Sentinel-2 and WorldPop",
    ),
    "Surface temperature": (
        "lst_c",
        "LST (°C)",
        "Landsat 8/9 · clear-sky surface temperature",
    ),
    "Nitrogen dioxide": (
        "no2_mol_m2",
        "NO₂ (µmol/m²)",
        "Sentinel-5P OFFL · tropospheric column",
    ),
    "Greenness": ("ndvi", "NDVI (−1 to 1)", "Sentinel-2 · vegetation index"),
    "Robust priority": (
        "robust_priority",
        "Priority",
        "Top quintile under all four population-weighted schemes",
    ),
}


@st.cache_resource(max_entries=2, show_spinner=False)
def _demo_analysis(name):
    request, cells, months = load_demo(name)
    return request, score_exposure(cells).cells, months, fit_drivers(cells)


def select_area():
    with st.sidebar:
        st.header("Study area")
        name = st.selectbox("Data source", [*PRESETS, LIVE])
        if st.session_state.get("active_source") != name:
            for key in (
                "planner_input",
                "driver_result",
                "planner_result",
                "trends_result",
                "plan_scheme",
                "plan_count",
                "plan_percent",
            ):
                st.session_state.pop(key, None)
            st.session_state.active_source = name
        if name == LIVE:
            render_area_form()
        else:
            st.caption("Offline preset · Earth Engine observations")
            try:
                if "planner_input" not in st.session_state:
                    request, scored, months, model = _demo_analysis(name)
                    st.session_state.planner_input = (request, "summer", scored)
                    st.session_state.driver_result = (request, "summer", model)
                    st.session_state.trends_result = (request, months)
            except (OSError, ValueError):
                st.error("The bundled preset could not be loaded.")
            active = st.session_state.get("planner_input")
            if active:
                request = active[0]
                st.write(f"{request.lat:.2f}° N · {request.lon:.2f}° E")
                st.caption("5 km radius · 500 m cells\n\nSummer composites · 2019–2021")
    return name


def _cell_chart(cells, layer):
    field, unit, source = LAYERS[layer]
    zones = zone_directory(cells)
    records = []
    categorical = field == "robust_priority"
    for key, value, geom in cells[["cell_id", field, "geometry"]].itertuples(
        index=False, name=None
    ):
        if pd.isna(value):
            value = None
        elif categorical:
            value = "Priority" if value else "Other"
        else:
            value = float(value)
        records.append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "zone": zones.at[key, "Zone"],
                "level": hotspot_level(value),
                "value": value,
            }
        )
    chart = alt.Chart(alt.Data(values=records)).mark_geoshape(
        stroke="#132a30", strokeWidth=0.4
    )
    if categorical:
        color = alt.Color(
            "value:N",
            title=unit,
            scale=alt.Scale(domain=["Other", "Priority"], range=["#386a77", "#f2d85b"]),
        )
    else:
        color = alt.Color(
            "value:Q",
            title=unit,
            scale=alt.Scale(scheme="inferno" if field == "lst_c" else "viridis"),
            legend=alt.Legend(format=".2g", orient="bottom"),
        )
    chart = chart.encode(
        color=alt.condition("isValid(datum.value)", color, alt.value("#566169")),
        tooltip=[
            alt.Tooltip("zone:N", title="Zone"),
            alt.Tooltip("level:N", title="Hotspot level"),
            alt.Tooltip(
                "value:N" if categorical else "value:Q",
                title=unit,
                **({} if categorical else {"format": ".4g"}),
            ),
        ],
    )
    chart = chart.project(type="identity", reflectY=True).properties(
        title=layer, height=385
    )
    st.altair_chart(chart, width="stretch")
    _map_takeaway(cells, field, unit)
    st.caption(f"{source}. Gray cells have insufficient data.")


def render_overview(name):
    active = st.session_state.get("planner_input")
    if active is None:
        st.info(
            "Choose an offline preset or analyze a custom study area in the sidebar."
        )
        return
    req, season, cells = active
    st.header(name if name != LIVE else "Custom study area")
    st.caption(
        f"{req.lat:.3f}°, {req.lon:.3f}° · {req.radius_km:g} km radius · {len(cells)} cells at {req.cell_size_m} m · {season.capitalize()} {req.start_year}–{req.end_year}"
    )
    coverage = float(np.average(cells.coverage_pct.fillna(0), weights=cells.area_m2))
    with st.container(key="overview_kpis"):
        cols = st.columns(3)
    cols[0].metric(
        "Scored cells",
        f"{cells.exposure_equal.count():,}",
        border=True,
    )
    cols[1].metric(
        "Coverage",
        f"{coverage:.1f}%",
        border=True,
        help="Share of study area with valid heat, NO₂, vegetation and population observations.",
    )
    cols[2].metric(
        "Robust-priority cells",
        str(int(cells.robust_priority.sum()))
        if cells.robust_priority.notna().any()
        else "—",
        border=True,
    )
    map_col, table_col = st.columns([1.1, 1], gap="medium")
    with map_col.container(border=True):
        _cell_chart(cells, "Hotspot score")
    with table_col.container(border=True):
        st.subheader("Highest hotspot scores")
        top = (
            cells.dropna(subset=["exposure_equal"])
            .sort_values(["exposure_equal", "cell_id"], ascending=[False, True])
            .head(5)
        )
        if top.empty:
            st.info("No cells have all four exposure inputs.")
        else:
            zones = zone_directory(cells).loc[top.cell_id]
            st.dataframe(
                pd.DataFrame(
                    {
                        "Zone": zones.Zone.tolist(),
                        "Google Maps": zones["Google Maps"].tolist(),
                        "Level": top.exposure_equal.map(hotspot_level).tolist(),
                        "LST (°C)": [f"{v:.1f}" for v in top.lst_c],
                        "Hotspot score": [f"{v:.3f}" for v in top.exposure_equal],
                    }
                ),
                column_config={
                    "Google Maps": st.column_config.LinkColumn(display_text="Open map")
                },
                hide_index=True,
            )
            st.caption("Ranked by Hotspot score within this area.")


def _map_takeaway(cells, field, unit):
    valid = cells.dropna(subset=[field])
    if valid.empty:
        st.caption("There are too few observations to compare zones on this layer.")
    elif field == "robust_priority":
        st.caption(
            f"{int(valid[field].sum())} zones rank among the highest under every weighting scheme."
        )
    else:
        high = valid.sort_values([field, "cell_id"], ascending=[False, True]).iloc[0]
        zone = zone_directory(cells).at[high.cell_id, "Zone"]
        value = high[field] * (NO2_TO_MICROMOLES if field == "no2_mol_m2" else 1)
        st.caption(f"The highest reading is {value:.3g} ({unit}) in {zone}.")


def render_map():
    st.header("Zone map")
    active = st.session_state.get("planner_input")
    if active is None:
        st.info("Choose a study area to explore its cells.")
        return
    cells = active[2]
    layer = st.selectbox("Map layer", list(LAYERS))
    st.caption("Select a zone on the map to inspect its observations.")
    basemap = st.radio("Basemap", ["OpenStreetMap", "Satellite"], horizontal=True)
    field, unit, source = LAYERS[layer]
    render_grid_map(cells, field, unit, basemap)
    _map_takeaway(cells, field, unit)
    st.caption(
        f"{source}. Gray means insufficient data. Background imagery requires internet."
    )


def render_methodology():
    st.header("Methodology & limits")
    st.subheader("How a cell is scored")
    st.write(
        "Within the selected area, we rank land-surface temperature anomalies, tropospheric NO₂ and vegetation deficit. The equal scheme averages those ranks. Each forward scheme doubles one factor. Multiplying hazard by population rank gives exposure. A robust-priority cell reaches the top quintile under all four schemes."
    )
    st.write(
        "Hotspot scores use a 0–1 scale. Low is below 0.25, Moderate starts at 0.25, High at 0.50 and Very high at 0.75. These bands describe relative scores within the study area."
    )
    st.subheader("What the satellites measure")
    st.write(
        "Landsat measures surface temperature; air temperature can differ. Thermal observations are native to about 100 m even when delivered on a 30 m grid. Sentinel-5P measures the atmospheric NO₂ column, not ground-level concentration. Its footprint spans multiple planner cells."
    )
    st.write(
        "Sentinel-2 provides vegetation, built-up and water indices. Dynamic World supplies probabilistic land-cover classes. WorldPop provides a fixed 2020 population estimate, and SRTM provides terrain."
    )
    st.subheader("Time windows and missing data")
    st.write(
        "Time-varying exposure layers use the same years and season. Summer is June–August in the north and December–February in the south. Clouds and data gaps can bias the composites. Coverage is the area-weighted share with all four exposure inputs. Trends use all calendar months and the coarser Terra MODIS temperature record."
    )
    st.subheader("Interpreting model results")
    st.write(
        "Spatial cross-validation holds out whole 2 km blocks. SHAP contributions describe associations. Planting estimates are model-based, indicative, not causal. Local suitability and access need separate assessment."
    )
