"""A place-based story from exposure to planting candidates."""

import altair as alt
import geopandas as gpd
import pandas as pd
import streamlit as st
from shapely.geometry import mapping
from shapely.geometry.polygon import orient

from src.demo import PRESETS, load_demo
from src.index import score_exposure
from src.model import InsufficientDriverData, fit_drivers
from src.planner import estimate_scenario, rank_sites
from src.ui.comparison import _mean
from src.ui.drivers import render_area_form
from src.zones import hotspot_level

LIVE = "Custom live analysis"
LEVELS = ["Low", "Moderate", "High", "Very high"]
COLORS = ["#367483", "#74b6a0", "#efc16d", "#d66b4c"]


@st.cache_data(max_entries=2, show_spinner=False)
def _preset(name):
    request, cells = load_demo(name)
    return request, "summer", score_exposure(cells)


def _map(cells, sites):
    features = []
    for row in cells.to_crs(4326).itertuples():
        features.append(
            dict(
                type="Feature",
                geometry=mapping(orient(row.geometry, sign=-1)),
                level=hotspot_level(row.exposure_equal),
            )
        )
    polygons = (
        alt.Chart(alt.Data(values=features))
        .mark_geoshape()
        .encode(
            color=alt.Color(
                "level:N",
                title="Relative exposure",
                scale=alt.Scale(
                    domain=LEVELS + ["No data"], range=COLORS + ["#687478"]
                ),
                legend=alt.Legend(orient="bottom", values=LEVELS),
            ),
            tooltip=[alt.Tooltip("level:N", title="Exposure")],
        )
    )
    centers = cells.set_index("cell_id").loc[sites.index].geometry.centroid.to_crs(4326)
    points = pd.DataFrame(
        {"lat": centers.y, "lon": centers.x, "site": range(1, len(centers) + 1)}
    ).reset_index(drop=True)
    markers = alt.Chart(points).encode(longitude="lon:Q", latitude="lat:Q")
    chart = (
        polygons
        + markers.mark_circle(size=270, color="#152c32", opacity=1)
        + markers.mark_text(color="white", fontWeight="bold").encode(text="site:O")
    )
    st.altair_chart(
        chart.project(type="mercator").properties(height=370), width="stretch"
    )
    st.caption(
        "Numbers mark planting candidates in priority order. Grey means missing readings. Source · Landsat, Sentinel-2, Sentinel-5P and WorldPop."
    )


def _reason(cells):
    st.subheader("Why is it hot here?")
    observed = cells.dropna(subset=["dw_frac_trees", "lst_c"]).sort_values(
        "dw_frac_trees"
    )
    if len(observed) < 4 or observed.dw_frac_trees.nunique() < 2:
        st.info(
            "There is too little variation in observed tree cover to compare temperatures."
        )
        return
    low, high = observed.dw_frac_trees.quantile([0.25, 0.75])
    if low == high:
        fewer, more = (
            observed[observed.dw_frac_trees <= low],
            observed[observed.dw_frac_trees > high],
        )
    else:
        fewer, more = (
            observed[observed.dw_frac_trees <= low],
            observed[observed.dw_frac_trees >= high],
        )
    if fewer.empty or more.empty:
        st.info("Tree cover is too similar across sites for a comparison.")
        return
    a, b = (_mean(group, "lst_c") for group in (fewer, more))
    data = pd.DataFrame(
        {"Tree cover": ["Less tree cover", "More tree cover"], "Temperature": [a, b]}
    )
    st.altair_chart(
        alt.Chart(data)
        .mark_bar(color=COLORS[1])
        .encode(
            y=alt.Y("Tree cover:N", title=None),
            x=alt.X(
                "Temperature:Q",
                title="Average surface temperature (°C)",
                axis=alt.Axis(format=".1f"),
            ),
            tooltip=[alt.Tooltip("Temperature:Q", format=".1f", title="Surface °C")],
        ),
        width="stretch",
    )
    st.write(
        f"Surfaces in the group with more trees averaged {b:.1f} °C, compared with {a:.1f} °C in the group with fewer trees."
    )
    st.caption(
        "Local observations from Landsat and Dynamic World. Other differences between sites can also affect their temperature."
    )


@st.cache_data(
    hash_funcs={
        gpd.GeoDataFrame: lambda frame: (
            str(frame.crs),
            pd.util.hash_pandas_object(frame.to_wkb()).values.tobytes(),
        )
    },
    ttl=86400,
    max_entries=50,
    show_spinner="Estimating the effect of planting…",
)
def _cooling(cells, sites):
    try:
        model = fit_drivers(cells)
    except InsufficientDriverData:
        return pd.DataFrame(index=sites.index, columns=["delta_c"], dtype=float)
    return estimate_scenario(model, sites, 25)


def _action(cells, sites):
    st.subheader("What to do first")
    if sites.empty:
        st.info("No sites passed the open-land and water checks.")
        return
    st.write(
        "Check these sites first. Each estimate assumes trees replace a quarter of the existing bare ground."
    )
    first = sites.head(5)
    estimates = _cooling(cells, first)
    centers = cells.set_index("cell_id").loc[first.index].geometry.centroid.to_crs(4326)
    for number, (key, point) in enumerate(centers.items(), 1):
        delta = estimates.at[key, "delta_c"]
        if pd.isna(delta):
            effect = "there are too few complete readings for a cooling estimate"
        elif abs(delta) < 0.05:
            effect = "the estimated temperature change is less than 0.1 °C"
        else:
            effect = f"the surface could be {abs(delta):.1f} °C {'cooler' if delta < 0 else 'warmer'}"
        if pd.notna(delta):
            lower, upper = estimates.loc[key, ["lower_c", "upper_c"]]
            effect += f" (estimated change range {lower:+.1f} to {upper:+.1f} °C)"
        st.markdown(
            f"**{number}.** [Site at {point.y:.4f}°, {point.x:.4f}°](https://www.google.com/maps/search/?api=1&query={point.y:.6f},{point.x:.6f}) · {effect}."
        )
    st.caption(first.land_use_review.iloc[0])


def render_story():
    st.title("Where do heat and air pollution put people most at risk?")
    name = st.selectbox("Choose a place", [*PRESETS, LIVE])
    if name == LIVE:
        render_area_form()
        active = st.session_state.get("planner_input")
        if active is None:
            return
    else:
        active = _preset(name)
    request, season, cells = active
    st.caption(
        f"{request.radius_km:g} km around {request.lat:.3f}°, {request.lon:.3f}° · {season.capitalize()} · {request.start_year}–{request.end_year}"
    )
    scored = cells.dropna(subset=["exposure_equal"])
    if scored.empty:
        st.info("There are too few overlapping readings to identify hotspots here.")
        return
    highest = scored.exposure_equal.ge(0.75)
    st.info(
        f"**{int(highest.sum())} of {len(scored)} measured zones** have very high combined exposure, with an estimated **{scored.loc[highest, 'population'].sum():,.0f} residents** living in them."
    )
    sites = rank_sites(cells, top_n=10)
    st.subheader("Where exposure is highest")
    _map(cells, sites)
    heat, people, coverage = st.columns(3)
    heat.metric("Average surface heat", f"{_mean(cells, 'lst_c'):.1f} °C")
    people.metric("Estimated residents", f"{cells.population.sum():,.0f}")
    coverage.metric("Area with readings", f"{_mean(cells, 'coverage_pct'):.0f}%")
    _reason(cells)
    _action(cells, sites)
