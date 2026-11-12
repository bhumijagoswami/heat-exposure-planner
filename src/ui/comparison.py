"""Matched two-area comparisons of satellite observations."""

import altair as alt
import pandas as pd
import streamlit as st

from src.demo import PRESETS, load_demo
from src.index import score_exposure
from src.ui.basemap import render_grid_map
from src.ui.drivers import _load_cells
from src.ui.limits import begin_compute
from src.ui.trends import _chart, _load_monthly
from src.validate import validate_inputs
from src.zones import NO2_RESOLUTION_NOTE, NO2_TO_MICROMOLES

CUSTOM = "Custom coordinates"
MEASURES = {
    "Surface temperature (°C)": "lst_c",
    "Nitrogen dioxide (µmol/m²)": "no2_mol_m2",
    "Greenness (NDVI)": "ndvi",
    "Residents in priority zones (%)": "priority",
}


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
        _, cells, monthly = load_demo(name)
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
        monthly = _load_monthly(request)
    return score_exposure(cells).cells, monthly


def _mean(cells, field):
    valid = cells.dropna(subset=[field, "area_m2"])
    area = valid.area_m2.sum()
    return (valid[field] * valid.area_m2).sum() / area if area else float("nan")


def _measures(cells):
    total = cells.population.sum()
    priority = cells.loc[cells.robust_priority.fillna(False), "population"].sum()
    return [
        _mean(cells, "lst_c"),
        _mean(cells, "no2_mol_m2") * NO2_TO_MICROMOLES,
        _mean(cells, "ndvi"),
        100 * priority / total if total > 0 else float("nan"),
    ]


def _heat_summary(a, b):
    averages = [_mean(frame, "lst_c") for frame in (a, b)]
    if any(pd.isna(value) for value in averages):
        return "Temperature coverage is insufficient to compare the areas."
    gap = averages[0] - averages[1]
    if abs(gap) < 0.05:
        return "The average surface temperatures differ by less than 0.05 °C."
    hot, cool = ("Area A", "Area B") if gap > 0 else ("Area B", "Area A")
    # Split the observed mean gap into two additive parts around a shared midpoint.
    midpoint = sum(averages) / 2
    upper = [
        _mean(frame.assign(excess=(frame.lst_c - midpoint).clip(lower=0)), "excess")
        for frame in (a, b)
    ]
    warm_share = (upper[0] - upper[1]) / gap
    if abs(warm_share - 0.5) < 0.01:
        reason = "warmer and cooler zones contribute about equally to the gap"
    elif warm_share > 0.5:
        reason = f"zones above {midpoint:.1f} °C contribute more excess heat per unit of study area"
    else:
        reason = f"zones below {midpoint:.1f} °C bring down the average more in {cool}"
    return f"{hot} is hotter by {abs(gap):.1f} °C mainly because {reason}."


def _charts(pair):
    cells = [item[0] for item in pair]
    names = ["Area A", "Area B"]
    st.subheader(_heat_summary(*cells))
    st.caption(
        "This comparison describes where the measured temperature gap comes from. It cannot establish its physical cause."
    )
    metrics = pd.DataFrame(
        dict(zip(names, map(_measures, cells), strict=True)), index=list(MEASURES)
    )
    long = (
        metrics.rename_axis("Measure")
        .reset_index()
        .melt("Measure", var_name="Area", value_name="Reading")
    )
    bars = (
        alt.Chart(long)
        .mark_bar()
        .encode(
            x=alt.X("Area:N", title=None),
            y="Reading:Q",
            color="Area:N",
            tooltip=["Area", "Measure", "Reading"],
        )
    )
    st.altair_chart(
        bars.properties(width=125)
        .facet(column=alt.Column("Measure:N", title=None, sort=list(MEASURES)))
        .resolve_scale(y="independent")
        .properties(title="Summer readings and residents in priority zones"),
        width="stretch",
    )
    for label, row in metrics.iterrows():
        if row.notna().all():
            st.caption(
                f"{label} averages {row.iloc[0]:.2f} in Area A and {row.iloc[1]:.2f} in Area B."
            )
    st.caption(
        "Sources · Landsat, Sentinel-5P, Sentinel-2 and WorldPop. Priority uses each area's own rankings. The population denominator includes all known residents."
    )
    st.caption(NO2_RESOLUTION_NOTE)
    cover = pd.DataFrame(
        {
            name: {
                field.removeprefix("dw_frac_").replace("_", " "): 100
                * _mean(frame, field)
                for field in frame
                if field.startswith("dw_frac_")
            }
            for name, frame in zip(names, cells, strict=True)
        }
    )
    land = (
        cover.rename_axis("Cover")
        .reset_index()
        .melt("Cover", var_name="Area", value_name="Percent")
        .dropna()
    )
    if not land.empty:
        st.altair_chart(
            alt.Chart(land)
            .mark_bar()
            .encode(
                y="Area:N",
                x=alt.X("sum(Percent):Q", title="Share of classified land (%)"),
                color="Cover:N",
                tooltip=["Area", "Cover", alt.Tooltip("Percent:Q", format=".1f")],
            )
            .properties(title="Land cover · Dynamic World"),
            width="stretch",
        )
        largest = [
            col.idxmax() if col.notna().any() else "unknown" for _, col in cover.items()
        ]
        st.caption(
            f"The most widespread classified cover is {largest[0]} in Area A and {largest[1]} in Area B."
        )
    else:
        st.info("Neither area has classified land-cover observations.")
    for column, name, frame in zip(st.columns(2), names, cells, strict=True):
        with column:
            st.subheader(name)
            render_grid_map(
                frame, "exposure_equal", "Hotspot score (0–1)", "OpenStreetMap"
            )
            st.caption(
                f"{int(frame.robust_priority.sum())} zones consistently rank in the top fifth here."
            )
    metric = st.selectbox(
        "Monthly comparison",
        [
            "Daytime surface temperature",
            "Nighttime surface temperature",
            "Nitrogen dioxide",
        ],
    )
    field = {
        "Daytime surface temperature": "day_c",
        "Nighttime surface temperature": "night_c",
        "Nitrogen dioxide": "no2",
    }[metric]
    series = pd.concat(
        [
            months[f"roi_{field}"].rename(name)
            for name, (_, months) in zip(names, pair, strict=True)
        ],
        axis=1,
    )
    unit, source = (
        ("µmol/m²", "Sentinel-5P") if field == "no2" else ("°C", "Terra MODIS")
    )
    if field == "no2":
        series *= NO2_TO_MICROMOLES
    if series.notna().any().any():
        _chart(series, f"Monthly {metric.lower()} · both areas", unit, source)
    shared = series.dropna()
    st.caption(
        f"The mean monthly difference (Area A minus Area B) is {(shared.iloc[:, 0] - shared.iloc[:, 1]).mean():+.2f} {unit} across {len(shared)} shared months."
        if len(shared)
        else "The areas have no overlapping monthly readings."
    )


def render_comparison():
    st.header("Compare two areas")
    st.info(
        "**How to read this** · Compare each pair of bars in its own units. Both areas use a 5 km radius, 500 m zones and summer readings from 2019–2021. The monthly chart includes all seasons."
    )
    choices = []
    for index, column in enumerate(st.columns(2)):
        with column:
            choices.append(_choice(("Area A", "Area B")[index], index))
    key = tuple(choices)
    if st.button("Compare areas"):
        if any(choice[0] == CUSTOM for choice in choices) and not begin_compute():
            return
        try:
            with st.spinner("Loading both areas…"):
                pair = [_load(choice) for choice in choices]
        except Exception:
            st.error(
                "The comparison could not load both areas. Check the coordinates and Earth Engine connection, then retry."
            )
            return
        st.session_state.compared_areas = key, pair
    saved = st.session_state.get("compared_areas")
    if saved and saved[0] == key:
        _charts(saved[1])
