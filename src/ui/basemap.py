"""Shared map for locally ranked exposure and comparable surface temperatures."""

import base64
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from shapely.geometry import mapping

from src.index import score_exposure
from src.planner import _land_use_flags

LAYERS = (
    "Overall risk",
    "Surface heat",
    "Tree cover",
    "Built-up share",
    "Land cover type",
    "People",
)
LAND_COLORS = {
    "Built-up": "#888480",
    "Trees": "#23623b",
    "Grass": "#a7ce79",
    "Bare": "#d5b487",
    "Water": "#4085b4",
    "Other (farmland, shrub)": "#aa832e",
}
LAND_NAMES = {
    "built": "Built-up",
    "trees": "Trees",
    "grass": "Grass",
    "bare": "Bare",
    "water": "Water",
    "crops": "Farmland",
    "shrub_and_scrub": "Shrub",
    "flooded_vegetation": "Flooded vegetation",
    "snow_and_ice": "Snow or ice",
}
SCALES = {
    "Surface heat": (
        "lst_c",
        [35, 40, 45],
        "Surface temperature (°C)",
        ["#ffffb2", "#fecc5c", "#fd8d3c", "#bd0026"],
    ),
    "Tree cover": (
        "dw_frac_trees",
        [0.25, 0.5, 0.75],
        "Tree cover (%)",
        ["#edf8e9", "#bae4b3", "#74c476", "#238b45"],
    ),
    "Built-up share": (
        "dw_frac_built",
        [0.25, 0.5, 0.75],
        "Built-up share (%)",
        ["#eeeae5", "#c9bdb2", "#988578", "#614c40"],
    ),
    "People": (
        "population",
        [1000, 5000, 10000],
        "Estimated residents per zone",
        ["#efedf5", "#bcbddc", "#9e9ac8", "#6a51a3"],
    ),
}
COLORS = ["#4688bc", "#fff1ab", "#ee9041", "#952a30", "#949a9e"]


def relative_bands(cells, field):
    # Stable identifiers break ties at percentile boundaries, even if input is shuffled.
    valid = cells[field].dropna().sort_index()
    position = (
        (valid.rank(method="first", ascending=True) - 0.5) / len(valid)
        if len(valid)
        else valid
    )
    bands = pd.cut(position, [-1, 0.4, 0.7, 0.9, 1], labels=False, right=False)
    return bands.reindex(cells.index).fillna(4).astype(int)


def select_markers(cells):
    """Return ranked IDs from a metre-projected grid, with at least 1 km separation."""
    indexed = cells.set_index("cell_id").sort_index()
    flagged = _land_use_flags(indexed).str.startswith("Airport district")
    for field in ("restricted", "airfield"):
        if field in indexed:
            flagged |= indexed[field].fillna(False).astype(bool)
    eligible = (
        indexed.loc[~flagged, "exposure_equal"]
        .dropna()
        .sort_values(ascending=False, kind="stable")
    )
    centers = indexed.geometry.centroid
    chosen = []
    for key in eligible.index:
        if all(centers[key].distance(centers[other]) >= 1000 for other in chosen):
            chosen.append(key)
            if len(chosen) == 5:
                break
    return chosen


def marker_records(indexed, keys):
    centers = indexed.loc[keys].geometry.centroid.to_crs(4326)
    hot = relative_bands(indexed, "lst_c")
    crowded = relative_bands(indexed, "population")
    trees = indexed.dw_frac_trees.median()
    valid = indexed.dropna(subset=["lst_c", "area_m2"])
    average = (
        valid.lst_c.dot(valid.area_m2) / valid.area_m2.sum()
        if valid.area_m2.sum()
        else float("nan")
    )
    types = dominant_types(indexed)
    records = []
    for number, key in enumerate(keys, 1):
        row = indexed.loc[key]
        tag = "Hot"
        if hot[key] in (2, 3):
            if row.dw_frac_trees < trees:
                tag = "Hot and treeless"
            elif crowded[key] in (2, 3):
                tag = "Hot and crowded"
        gap = row.lst_c - average
        heat = f"{row.lst_c:.1f} °C ({abs(gap):.1f} °C {'above' if gap >= 0 else 'below'} average)"
        cover = f"{row.dw_frac_trees:.0%}" if pd.notna(row.dw_frac_trees) else "No data"
        details = f"Zone {number} · {tag}\nSurface temperature: {heat}\nResidents: {row.population:,.0f}\nTree cover: {cover}\nBuilt-up share: {reading(row.dw_frac_built, '.1%')}\nDominant type: {types[key] if pd.notna(types[key]) else 'No data'}"
        records.append(
            dict(
                number=number,
                center=list(centers[key].coords[0]),
                tag=tag,
                details=details,
            )
        )
    return records


def pooled_risk(frames):
    fields = ["lst_c", "no2_mol_m2", "ndvi", "population", "coverage_pct", "area_m2"]
    pooled = pd.concat([frame[fields] for frame in frames], ignore_index=True)
    risk = score_exposure(pooled).exposure_equal
    ranks = (risk.rank(method="average") - 0.5) / max(1, risk.count())
    bands = (
        pd.cut(ranks, [-1, 0.4, 0.7, 0.9, 1], labels=False, right=False)
        .fillna(4)
        .astype(int)
    )
    split = len(frames[0])
    return bands.iloc[:split].to_numpy(), bands.iloc[split:].to_numpy()


def dominant_types(cells):
    fractions = cells.filter(regex="^dw_frac_")
    return (
        fractions.fillna(-1)
        .idxmax(axis=1)
        .str.removeprefix("dw_frac_")
        .map(LAND_NAMES)
        .where(fractions.max(axis=1) > 0)
    )


def reading(value, fmt, unit=""):
    return f"{value:{fmt}}{unit}" if pd.notna(value) else "No data"


def zone_details(row, land):
    return "\n".join(
        [
            f"Surface temperature: {reading(row.lst_c, '.1f', ' °C')}",
            f"Tree cover: {reading(row.dw_frac_trees, '.1%')}",
            f"Built-up share: {reading(row.dw_frac_built, '.1%')}",
            f"Dominant type: {land if pd.notna(land) else 'No data'}",
            f"Residents: {reading(row.population, ',.0f')}",
        ]
    )


def render_map(cells, *, caption, layer, keys=(), pooled=None):
    indexed = cells.set_index("cell_id")
    types = dominant_types(indexed)
    if layer in SCALES:
        field, edges, legend, palette = SCALES[layer]
        bands = (
            pd.cut(
                indexed[field],
                [-float("inf"), *edges, float("inf")],
                right=False,
                labels=False,
            )
            .fillna(4)
            .astype(int)
        )
        t = [f"{v * 100 if field.startswith('dw_frac') else v:,.0f}" for v in edges]
        labels = [f"<{t[0]}", f"{t[0]}–<{t[1]}", f"{t[1]}–<{t[2]}", f"≥{t[2]}"]
    elif layer == "Land cover type":
        legend = "Dominant land cover · Dynamic World"
        labels = list(LAND_COLORS)
        palette = list(LAND_COLORS.values())
        grouped = types.where(types.isin(labels), labels[-1]).where(types.notna())
        bands = (
            grouped.map({label: i for i, label in enumerate(labels)})
            .fillna(len(labels))
            .astype(int)
        )
    else:
        bands = (
            relative_bands(indexed, "exposure_equal")
            if pooled is None
            else pd.Series(pooled, index=indexed.index)
        )
        legend = (
            "Overall risk · rank within this place"
            if pooled is None
            else "Combined risk · rank across both places pooled"
        )
        labels = ["Bottom 40%", "40–70%", "70–90%", "Top 10%"]
        palette = COLORS[:4]
    rows = []
    for row in indexed.to_crs(4326).itertuples():
        rows.append(
            dict(
                geometry=mapping(row.geometry),
                band=int(bands[row.Index]),
                details=zone_details(row, types[row.Index]),
            )
        )
    payload = dict(
        rows=rows,
        markers=marker_records(indexed, keys) if keys else [],
        colors=[*palette, COLORS[-1]],
        legend=legend,
        labels=[*labels, "No data"],
        satellite=False,
    )
    encoded = base64.b64encode(json.dumps(payload, allow_nan=False).encode()).decode()
    template = Path(__file__).with_suffix(".html").read_text()
    st.iframe(
        template.replace("__DATA__", encoded),
        height=485,
        alt="Study area street or satellite map",
    )
    st.caption(caption)
