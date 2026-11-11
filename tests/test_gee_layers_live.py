import ee
import pytest

from src.gee_auth import initialize_earth_engine
from src.gee_layers import DW_CLASSES, build_layers
from src.validate import validate_inputs


@pytest.mark.live
def test_summer_layer_values_at_delhi_point():
    initialize_earth_engine()
    request = validate_inputs(
        lat=28.61,
        lon=77.21,
        radius_km=1,
        cell_size_m=250,
        start_year=2023,
        end_year=2023,
    )
    point = ee.Geometry.Point([request.lon, request.lat])
    image = build_layers(point.buffer(1000), request, season="summer")
    values = image.reduceRegion(
        ee.Reducer.first(), point, scale=30, crs="EPSG:32643"
    ).getInfo()
    bounds = {
        "lst_c": (0, 75),
        "no2_mol_m2": (-0.001, 0.01),
        "ndvi": (-1, 1),
        "ndbi": (-1, 1),
        "mndwi": (-1, 1),
        "dw_label": (0, 8),
        "elevation_m": (100, 500),
        "slope_deg": (0, 90),
        "population": (0, 30000),
    }
    for name in DW_CLASSES:
        bounds[f"dw_frac_{name}"] = bounds[f"dw_prob_{name}"] = (0, 1)
    assert values.keys() == bounds.keys()
    for band, (low, high) in bounds.items():
        assert values[band] is not None and low <= values[band] <= high, band
    assert sum(values[f"dw_frac_{name}"] for name in DW_CLASSES) == 1
    assert sum(values[f"dw_prob_{name}"] for name in DW_CLASSES) == pytest.approx(
        1, abs=0.01
    )
