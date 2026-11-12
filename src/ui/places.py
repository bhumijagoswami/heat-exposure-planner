"""Matched observation windows and plain-language chart helpers."""

import calendar
import logging
from dataclasses import dataclass

import altair as alt
import pandas as pd
import streamlit as st

from src.config import summer_months
from src.demo import PRESETS, DEMO_DIR, load_demo
from src.validate import validate_inputs
from src.ui import drivers
from src.ui.basemap import COLORS
from src.ui.limits import begin_compute

HEAT = "ground surface temperature, hotter than air temperature"
AIR = "coarse pixels several km wide, so shown per area, not per zone"
LAND = {
    "built": "Built-up",
    "bare": "Bare ground",
    "grass": "Grass",
    "trees": "Trees",
    "water": "Water",
    "crops": "Farmland",
    "shrub_and_scrub": "Shrub",
}


@dataclass
class Place:
    name: str
    request: object
    cells: object
    months: pd.DataFrame

    @property
    def window(self):
        months = ", ".join(
            calendar.month_name[m] for m in summer_months(self.request.lat)
        )
        return f"{months} 2019–2021 · 500 m zones within {self.request.radius_km:g} km"


@st.cache_data(max_entries=2, show_spinner=False)
def preset(name):
    request, cells = load_demo(name)
    months = pd.read_parquet(DEMO_DIR / f"{PRESETS[name][0]}_monthly.parquet")
    return Place(name, request, cells, months)


def choose_place(label, index, key, custom_radius=False):
    name = st.selectbox(label, list(PRESETS), index=index, key=key + "_preset")
    with st.expander("Custom coordinates"):
        enabled = st.checkbox("Use custom coordinates", key=key + "_custom")
        lat = st.number_input(
            "Latitude", -90.0, 90.0, 28.62, format="%.4f", key=key + "_lat"
        )
        lon = st.number_input(
            "Longitude", -180.0, 180.0, 77.23, format="%.4f", key=key + "_lon"
        )
        radius = (
            st.number_input("Radius (km)", 1.0, 15.0, 5.0, key=key + "_radius")
            if custom_radius
            else 5
        )
        if enabled:
            try:
                request = validate_inputs(
                    lat=lat,
                    lon=lon,
                    radius_km=radius,
                    cell_size_m=500,
                    start_year=2019,
                    end_year=2021,
                )
            except ValueError as exc:
                st.warning(str(exc))
                return None
            saved = st.session_state.get(key + "_result")
            if st.button("Analyze area", key=key + "_run") and begin_compute():
                try:
                    with st.spinner("Loading satellite observations…"):
                        result = Place(
                            f"{lat:.2f}°, {lon:.2f}°",
                            request,
                            drivers._load_cells(request, "summer"),
                            drivers._load_monthly(request),
                        )
                    st.session_state[key + "_result"] = result
                    saved = result
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Live request failed (%s)", type(exc).__name__
                    )
                    st.warning(
                        "Live Earth Engine data is unavailable. Choose a saved place or try again later."
                    )
                    return None
            return saved if saved and saved.request == request else None
    try:
        return preset(name)
    except OSError:
        st.warning(f"The saved observations for {name} are unavailable.")
        return None


def mean(cells, field):
    valid = cells.dropna(subset=[field, "area_m2"])
    total = valid.area_m2.sum()
    return valid[field].dot(valid.area_m2) / total if total else float("nan")


def monthly_line(places, field):
    heat = field == "roi_day_c"
    axis = "Surface temperature (°C)" if heat else "Nitrogen dioxide (µmol/m²)"
    frames = []
    for i, place in enumerate(places):
        values = place.months[field].reindex(
            pd.date_range("2019-01-01", "2021-12-01", freq="MS")
        ) * (1 if heat else 1_000_000)
        frames.append(
            pd.DataFrame(
                {
                    "Month": values.index,
                    "Reading": values,
                    "Place": place.name
                    if len(places) == 1
                    else f"{'AB'[i]} · {place.name}",
                    "Segment": values.isna().cumsum(),
                }
            )
        )
    data = pd.concat(frames)
    if data.Reading.notna().any():
        lo, hi = data.Reading.min(), data.Reading.max()
        st.subheader(
            f"Monthly {'surface temperature' if heat else 'nitrogen dioxide'} ranged from {lo:.1f} to {hi:.1f}"
        )
    else:
        st.info(f"No monthly readings for {axis}.")
        return
    year = (
        alt.Chart(
            pd.DataFrame(
                {
                    "start": [pd.Timestamp("2020-01-01")],
                    "end": [pd.Timestamp("2021-01-01")],
                }
            )
        )
        .mark_rect(color="#949a9e", opacity=0.18)
        .encode(x="start:T", x2="end:T")
    )
    line = (
        alt.Chart(data.dropna())
        .mark_line(color=COLORS[0], point=True)
        .encode(
            x=alt.X("Month:T", title="Month", axis=alt.Axis(format="%b %y")),
            y=alt.Y(
                "Reading:Q",
                title=axis,
                scale=alt.Scale(zero=False),
                axis=alt.Axis(format=".1f"),
            ),
            strokeDash=alt.StrokeDash(
                "Place:N",
                legend=alt.Legend(title=None, orient="bottom")
                if len(places) > 1
                else None,
            ),
            detail="Segment:N",
            tooltip=[
                alt.Tooltip("Month:T", format="%b %Y"),
                "Place:N",
                alt.Tooltip("Reading:Q", format=".1f"),
            ],
        )
    )
    st.altair_chart(year + line, width="stretch")
    st.caption(
        f"Monthly area averages · {'MODIS · ' + HEAT if heat else 'Sentinel-5P · ' + AIR} · January 2019–December 2021 · shaded 2020: Lockdown year: pollution fell sharply."
    )
