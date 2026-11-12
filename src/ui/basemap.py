"""Render clipped grid polygons and raster tiles in the same Web Mercator view."""

import base64
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from shapely.geometry import mapping


def render_grid_map(cells, field, unit, basemap):
    rows = []
    for row in cells.to_crs(4326).itertuples():
        values = [
            getattr(row, key)
            for key in (field, "lst_c", "no2_mol_m2", "ndvi", "exposure_equal")
        ]
        rows.append(
            {
                "id": str(row.cell_id),
                "geometry": mapping(row.geometry),
                "values": [float(v) if pd.notna(v) else None for v in values],
            }
        )
    payload = {
        "rows": rows,
        "unit": unit,
        "satellite": basemap == "Satellite",
        "priority": field == "robust_priority",
    }
    # Only base64 enters the HTML template. All display strings use textContent.
    data = base64.b64encode(json.dumps(payload, allow_nan=False).encode()).decode()
    template = Path(__file__).with_name("basemap.html").read_text()
    st.iframe(
        template.replace("__DATA__", data), height=485, alt="Interactive study area map"
    )
