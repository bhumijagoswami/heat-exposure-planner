"""Monthly observations, seasonal trend estimates and rolling land-cover comparisons."""

import logging

import altair as alt
import pandas as pd
import streamlit as st

from .limits import begin_compute

from src.config import (
    CACHE_MAX_ENTRIES,
    CACHE_TTL_SECONDS,
    FIRST_YEAR,
    LAST_YEAR,
    MIN_RADIUS_KM,
    MAX_RADIUS_KM,
)
from src.gee_auth import EarthEngineAuthError
from src.trends import (
    METRICS,
    TrendExtractionError,
    analyze_trend,
    fetch_monthly,
    rolling_comparison,
)
from src.ui.drivers import initialize_app_earth_engine
from src.validate import validate_inputs


@st.cache_data(ttl=CACHE_TTL_SECONDS, max_entries=CACHE_MAX_ENTRIES, show_spinner=False)
def _load_monthly(request):
    initialize_app_earth_engine()
    return fetch_monthly(request)


def _chart(series, title, unit, source):
    long = (
        series.rename_axis("Month")
        .reset_index()
        .melt(id_vars="Month", var_name="Series", value_name="Value")
    )
    # Disconnected line segments preserve gaps even if a plotting backend drops null rows.
    long["Segment"] = long.Value.isna().groupby(long.Series).cumsum()
    chart = (
        alt.Chart(long.dropna())
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "Month:T",
                title="Month",
                scale=alt.Scale(domain=[series.index.min(), series.index.max()]),
            ),
            y=alt.Y("Value:Q", title=unit, scale=alt.Scale(zero=False)),
            color=alt.Color("Series:N", scale=alt.Scale(range=["#53c7be", "#efa65d"])),
            detail="Segment:N",
            tooltip=[
                "Month:T",
                "Series:N",
                alt.Tooltip("Value:Q", title=unit, format=".5g"),
            ],
        )
    )
    if 2020 in series.index.year:
        span = pd.DataFrame(
            {
                "start": [pd.Timestamp("2020-01-01")],
                "end": [min(pd.Timestamp("2021-01-01"), series.index.max())],
            }
        )
        shade = (
            alt.Chart(span)
            .mark_rect(opacity=0.12, color="#e4bb78")
            .encode(x="start:T", x2="end:T")
        )
        chart = shade + chart
    st.altair_chart(
        chart.properties(title=alt.Title(title, subtitle=source), height=275),
        width="stretch",
    )


def _trend_form():
    active = st.session_state.get("planner_input")
    default = active[0] if active else None
    with st.form("trend_request"):
        left, right = st.columns(2)
        lat = left.number_input(
            "Latitude (°)",
            -90.0,
            90.0,
            default.lat if default else 28.61,
            format="%.4f",
            key="trend_lat",
        )
        lon = right.number_input(
            "Longitude (°)",
            -180.0,
            180.0,
            default.lon if default else 77.21,
            format="%.4f",
            key="trend_lon",
        )
        radius = left.number_input(
            "Radius (km)",
            float(MIN_RADIUS_KM),
            float(MAX_RADIUS_KM),
            default.radius_km if default else 5.0,
            key="trend_radius",
        )
        years = right.slider(
            "Analysis years",
            FIRST_YEAR,
            LAST_YEAR,
            (default.start_year, default.end_year)
            if default
            else (FIRST_YEAR, LAST_YEAR),
            key="trend_years",
        )
        run = st.form_submit_button("Load monthly trends")
    if run:
        try:
            request = validate_inputs(
                lat=lat,
                lon=lon,
                radius_km=radius,
                cell_size_m=1000,
                start_year=years[0],
                end_year=years[1],
            )
        except ValueError as exc:
            st.warning(str(exc))
            return
        if not begin_compute():
            return
        st.session_state.pop("trends_result", None)
        try:
            with st.spinner("Retrieving monthly satellite observations…"):
                monthly = _load_monthly(request)
            st.session_state.trends_result = (request, monthly)
        except (EarthEngineAuthError, TrendExtractionError) as exc:
            st.warning(str(exc))
            return
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Trend extraction failed (%s)", type(exc).__name__
            )
            st.error("Monthly trends could not finish. Please retry.")
            return


def render_trends(offline=False):
    st.header("Monthly exposure trends")
    if not offline:
        _trend_form()
    if "trends_result" not in st.session_state:
        return
    request, monthly = st.session_state.trends_result
    metric = st.selectbox(
        "Measurement", list(METRICS), format_func=lambda m: METRICS[m][0]
    )
    name, unit = METRICS[metric]
    source = "Sentinel-5P OFFL" if metric == "no2" else "Terra MODIS MOD11A2"
    st.caption(
        f"{request.lat:.4f}°, {request.lon:.4f}° · {request.radius_km:g} km · "
        f"{request.start_year}–{request.end_year} · {source}"
    )
    obs = monthly[f"roi_{metric}"]
    if obs.notna().sum() == 0:
        st.info(
            "No valid observations for this measurement in the selected area and years."
        )
        return
    trend = analyze_trend(obs)
    coverage = monthly[f"roi_{metric}_coverage"].fillna(0).mean()
    st.caption(
        f"{obs.count()} of {len(obs)} months observed · mean valid area {coverage:.1f}%"
    )
    if trend.note:
        st.info(trend.note)
    else:
        a, b = st.columns(2)
        a.metric("Sen’s slope", f"{trend.slope_per_year:.4g} {unit}/year")
        b.metric("Mann–Kendall p-value", f"{trend.p_value:.3g}")
    if 2020 in monthly.index.year:
        st.caption(
            "Shading marks 2020 for lockdown context. Local restrictions varied within the year."
        )
    _chart(
        pd.DataFrame({"Observed": obs, "Deseasonalized": trend.adjusted}),
        f"{name} across the area",
        unit,
        source,
    )
    rolling = rolling_comparison(monthly, metric)
    if rolling.notna().any().any():
        _chart(
            rolling,
            f"{name} by land cover · trailing 3-month mean",
            unit,
            f"{source} · Dynamic World",
        )
    else:
        st.info("Neither land-cover group has three consecutive observed months.")
    st.caption(
        "Land-cover groups use the period’s Dynamic World modal class: built for urban core; "
        "trees, grass and shrub for green. Group means sample coarse satellite observations on a "
        "100 m grid. MODIS 8-day composites are assigned to their start month. "
        "STL removes the 12-month seasonal cycle. Short gaps are interpolated only for fitting STL. "
        "The Mann–Kendall p-value assumes independent residual observations; serial correlation can affect it."
    )
