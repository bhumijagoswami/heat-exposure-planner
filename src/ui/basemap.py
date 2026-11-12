"""Render clipped grid polygons and raster tiles in the same Web Mercator view."""

import base64
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from shapely.geometry import mapping


from src.zones import NO2_TO_MICROMOLES, hotspot_level, zone_directory


def render_grid_map(cells, field, unit, basemap):
    zones = zone_directory(cells)
    rows = []
    for row in cells.to_crs(4326).itertuples():
        values = [
            (
                row.no2_mol_m2 * NO2_TO_MICROMOLES
                if key == "no2_mol_m2"
                else getattr(row, key)
            )
            for key in (field, "lst_c", "no2_mol_m2", "ndvi", "exposure_equal")
        ]
        rows.append(
            {
                "id": zones.at[row.cell_id, "Zone"],
                "url": zones.at[row.cell_id, "Google Maps"],
                "level": hotspot_level(row.exposure_equal),
                "geometry": mapping(row.geometry),
                "values": [float(v) if pd.notna(v) else None for v in values],
            }
        )
    payload = {
        "rows": rows,
        "unit": unit,
        "satellite": basemap == "Satellite",
        "hotspot": field == "exposure_equal",
        "priority": field == "robust_priority",
    }
    # Only base64 enters the HTML template. All display strings use textContent.
    data = base64.b64encode(json.dumps(payload, allow_nan=False).encode()).decode()
    template = Path(__file__).with_name("basemap.html").read_text()
    st.iframe(
        template.replace("__DATA__", data), height=485, alt="Interactive study area map"
    )
