"""Bundled Earth Engine snapshots for offline exploration."""

from pathlib import Path

import geopandas as gpd

from .validate import validate_inputs

DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"
PRESETS = {
    "Delhi · central": ("central_delhi", 28.62, 77.23),
    "Bengaluru · central district": ("bengaluru", 12.97, 77.59),
}


def demo_request(name):
    _, lat, lon = PRESETS[name]
    return validate_inputs(
        lat=lat, lon=lon, radius_km=5, cell_size_m=500, start_year=2019, end_year=2021
    )


def load_demo(name):
    prefix = PRESETS[name][0]
    cells = gpd.read_parquet(DEMO_DIR / f"{prefix}_cells.parquet")
    return demo_request(name), cells
