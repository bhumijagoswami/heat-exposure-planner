"""Public zone names, map links and display units for the active study area."""

import pandas as pd

NO2_RESOLUTION_NOTE = "NO₂ is the amount in the air column above each square metre. The satellite footprint spans several kilometres, so nearby zones can share a reading. Street-level differences cannot be resolved."
NO2_TO_MICROMOLES = 1_000_000


def zone_directory(cells):
    centers = cells.set_index("cell_id").geometry.centroid.to_crs(4326).sort_index()
    return pd.DataFrame(
        {
            "Zone": [f"Zone {i}" for i in range(1, len(centers) + 1)],
            "Google Maps": [
                f"https://www.google.com/maps/search/?api=1&query={p.y:.6f},{p.x:.6f}"
                for p in centers
            ],
        },
        index=centers.index,
    )


def hotspot_level(score):
    if pd.isna(score):
        return "No data"
    return ("Low", "Moderate", "High", "Very high")[min(3, int(score * 4))]
