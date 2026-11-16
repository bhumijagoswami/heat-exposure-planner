"""Offline heat–pollution findings, drawn with the app's existing Altair library."""

import logging

import altair as alt
import pandas as pd
import streamlit as st

from src.demo import DEMO_DIR
from src.relationships import (
    fit_line,
    heat_drivers,
    month_points,
    risk_breakdown,
    strength_words,
    zone_points,
)
from src.ui.basemap import COLORS
from src.ui.score import render_rank_detail, render_score_formula

CITIES = {"Delhi central": "central_delhi", "Bengaluru central": "bengaluru"}
VIEWS = ["Between neighbourhoods", "Over the months", "Over the months, season removed"]
FACTORS = ["Heat", "Air pollution (NO₂)", "Lack of greenery"]
CELL_COLUMNS = [
    "cell_id",
    "area_m2",
    "coverage_pct",
    "lst_c",
    "no2_mol_m2",
    "ndvi",
    "population",
    "dw_frac_built",
    "dw_frac_trees",
]


@st.cache_data(ttl=86400, max_entries=2, show_spinner=False)
def load_cells(city):
    return pd.read_parquet(
        DEMO_DIR / f"{CITIES[city]}_cells.parquet", columns=CELL_COLUMNS
    )


@st.cache_data(ttl=86400, max_entries=2, show_spinner=False)
def load_monthly(city):
    return pd.read_parquet(
        DEMO_DIR / f"{CITIES[city]}_monthly.parquet", columns=["roi_day_c", "roi_no2"]
    )


def _safe_section(draw, *args):
    try:
        draw(*args)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Equation chart unavailable (%s)", type(exc).__name__
        )
        st.warning("This chart is unavailable right now; try another view or place.")


def _signed(value):
    return f"{'+' if value >= 0 else '−'} {abs(value):.3f}"


def _risk_chart(city):
    top = risk_breakdown(load_cells(city))
    if top.empty:
        st.info("There are too few overlapping readings to rank these zones.")
        return
    data = top.melt(
        id_vars=["Zone", "cell_id", "exposure_equal"],
        value_vars=FACTORS,
        var_name="Factor",
        value_name="Contribution",
    )
    chart = (
        alt.Chart(data)
        .mark_bar()
        .encode(
            y=alt.Y("Zone:N", sort=top.Zone.tolist(), title="Zones ordered by risk"),
            x=alt.X(
                "Contribution:Q",
                title="Hazard score before population weighting (0–1)",
                scale=alt.Scale(domain=[0, 1]),
            ),
            color=alt.Color(
                "Factor:N",
                scale=alt.Scale(
                    domain=FACTORS, range=["#d95c59", "#a0a4ab", "#74b6a0"]
                ),
                legend=alt.Legend(title=None, orient="bottom", columns=1),
            ),
            tooltip=[
                "Zone:N",
                "cell_id:N",
                "Factor:N",
                alt.Tooltip("Contribution:Q", format=".3f"),
                alt.Tooltip("exposure_equal:Q", title="Risk", format=".3f"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, width="stretch")
    st.caption(
        "Each colour adds one third of its factor to hazard in the ten highest-risk zones; "
        "ranks here may differ slightly from the numbered map markers · Landsat · Sentinel-5P · Sentinel-2 · WorldPop."
    )


def _drivers_chart():
    rows = []
    for city in CITIES:
        fit = heat_drivers(load_cells(city))
        if fit is None:
            st.info(
                f"{city}: too few independent land-cover readings to fit an equation."
            )
            continue
        st.write(
            f"**{city}:** Temp = {fit['a']:.2f} {_signed(fit['built'])} × Built-up "
            f"{_signed(fit['trees'])} × Trees; R² = {fit['r2']:.3f}, n = {fit['n']}."
        )
        rows.extend(
            [
                {
                    "Place": city,
                    "Effect": "+10 points built-up",
                    "Change": fit["built"] / 10,
                },
                {
                    "Place": city,
                    "Effect": "+10 points trees",
                    "Change": fit["trees"] / 10,
                },
            ]
        )
    if not rows:
        return
    chart = (
        alt.Chart(pd.DataFrame(rows))
        .mark_bar()
        .encode(
            y=alt.Y("Effect:N", title=None),
            yOffset="Place:N",
            x=alt.X(
                "Change:Q",
                title=[
                    "Surface-temperature change (°C)",
                    "+10 percentage points of cover",
                ],
            ),
            color=alt.Color(
                "Place:N",
                scale=alt.Scale(range=[COLORS[2], COLORS[0]]),
                legend=alt.Legend(title=None, orient="bottom", columns=1),
            ),
            tooltip=["Place:N", "Effect:N", alt.Tooltip("Change:Q", format="+.2f")],
        )
        .properties(height=210)
    )
    st.altair_chart(chart, width="stretch")
    st.caption(
        "Bars show the fitted change when one cover share rises by 10 percentage points with the other fixed; "
        "these are associations, not proof of cause · Landsat · Dynamic World · summer 2019–21."
    )


def _relationship_chart(city, view):
    spatial = view == VIEWS[0]
    adjusted = view == VIEWS[2]
    points = (
        zone_points(load_cells(city))
        if spatial
        else month_points(load_monthly(city), adjusted)
    )
    fit = fit_line(points)
    if fit is None:
        st.info("There are too few varying, paired readings to draw this relationship.")
        return
    st.subheader(f"{city} shows {strength_words(fit['r2'])}")
    response, predictor = (
        ("NO₂ departure", "Temp departure") if adjusted else ("NO₂", "Temp")
    )
    st.write(
        f"**{response} = {fit['a']:.2f} {_signed(fit['b'])} × {predictor}**; "
        f"R² = {fit['r2']:.3f}, n = {fit['n']}."
    )
    x_title = "Temperature departure (°C)" if adjusted else "Surface temperature (°C)"
    y_title = "NO₂ departure (µmol/m²)" if adjusted else "NO₂ column (µmol/m²)"
    dots = (
        alt.Chart(fit["points"])
        .mark_circle(color=COLORS[0], size=45, opacity=0.6)
        .encode(
            x=alt.X("x:Q", title=x_title, scale=alt.Scale(zero=False)),
            y=alt.Y("y:Q", title=y_title, scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("x:Q", title=x_title, format=".2f"),
                alt.Tooltip("y:Q", title=y_title, format=".2f"),
            ],
        )
    )
    xs = [points.x.min(), points.x.max()]
    line = (
        alt.Chart(pd.DataFrame({"x": xs, "y": [fit["a"] + fit["b"] * x for x in xs]}))
        .mark_line(color=COLORS[2], strokeWidth=3)
        .encode(x="x:Q", y="y:Q")
    )
    st.altair_chart((dots + line).properties(height=320), width="stretch")
    if spatial:
        note = "Each dot is a zone; NO₂ pixels are several km wide, so readings barely vary between zones"
        source = "Landsat · Sentinel-5P · summer 2019–21"
    elif adjusted:
        note = "Each dot subtracts its calendar-month mean from both readings, using months with at least two paired observations"
        source = "MODIS · Sentinel-5P · 2019–21"
    else:
        note = "Each dot is a month; heat and NO₂ both follow seasons, so a monthly link can come from the season (the season-removed view checks this)"
        source = "MODIS · Sentinel-5P · 2019–21"
    st.caption(f"{note} · {source}.")


def render_equations():
    st.title("Heat vs pollution")
    st.write(
        "See what builds the risk score and whether hotter places also have more NO₂."
    )
    city = st.radio("City", list(CITIES), horizontal=True, key="eq_city")
    st.subheader("Heat, air pollution and missing greenery share the score")
    render_score_formula()
    with st.expander("More detail"):
        render_rank_detail()
    _safe_section(_risk_chart, city)
    st.subheader("More built-up cover links to heat; more trees link to cooler ground")
    st.write(
        "The fitted equation uses built-up and tree shares from 0 to 1; R² is the share of temperature variation it explains."
    )
    _safe_section(_drivers_chart)
    st.subheader("Do hotter places have more air pollution?")
    view = st.radio("Look at", VIEWS, horizontal=True, key="eq_view")
    _safe_section(_relationship_chart, city, view)
