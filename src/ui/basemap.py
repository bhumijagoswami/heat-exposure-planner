"""Shared map for locally ranked exposure and comparable surface temperatures."""

import base64
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from shapely.geometry import mapping

from src.planner import _land_use_flags

LAYERS = {
    "Overall risk": "exposure_equal",
    "Surface heat": "lst_c",
    "Tree cover": "dw_frac_trees",
    "People": "population",
}
COLORS = ["#4688bc", "#fff1ab", "#ee9041", "#952a30", "#949a9e"]


def relative_bands(cells, field):
    # Stable identifiers break ties at percentile boundaries, even if input is shuffled.
    valid = cells[field].dropna().sort_index()
    position = (
        (valid.rank(method="first", ascending=field != "dw_frac_trees") - 0.5)
        / len(valid)
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
        details = f"Zone {number} · {tag}\nSurface temperature: {heat}\nResidents: {row.population:,.0f}\nTree cover: {cover}"
        records.append(
            dict(
                number=number,
                center=list(centers[key].coords[0]),
                tag=tag,
                details=details,
            )
        )
    return records


def render_map(cells, *, caption, layer=None, keys=()):
    """Omitting the layer selects the shared absolute temperature scale."""
    indexed = cells.set_index("cell_id")
    if layer is None:
        bands = (
            pd.cut(
                indexed.lst_c,
                [-float("inf"), 35, 40, 45, float("inf")],
                labels=False,
                right=False,
            )
            .fillna(4)
            .astype(int)
        )
        labels = ["Below 35", "35–under 40", "40–under 45", "45 and above", "No data"]
        legend = "Surface temperature (°C) · shared 30–50 scale"
    else:
        bands = relative_bands(indexed, LAYERS[layer])
        labels = ["Low", "Moderate", "High", "Very high", "No data"]
        legend = (
            "Lack of tree cover" if layer == "Tree cover" else layer
        ) + " compared with the rest of this area"
    rows = [
        dict(geometry=mapping(geometry), band=int(bands[key]))
        for key, geometry in indexed.geometry.to_crs(4326).items()
    ]
    payload = dict(
        rows=rows,
        markers=marker_records(indexed, keys) if keys else [],
        colors=COLORS,
        legend=legend,
        labels=labels,
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
