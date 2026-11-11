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


@pytest.mark.live
def test_no2_mean_weights_observations_across_years_with_gaps():
    from src.gee_layers import _no2_composite

    initialize_earth_engine()
    images = [
        ee.Image.constant([column, cloud])
        .toDouble()
        .rename(["tropospheric_NO2_column_number_density", "cloud_fraction"])
        .set("system:time_start", ee.Date(date).millis())
        for date, column, cloud in [
            ("2019-01-01", 0.00001, 0),
            ("2019-02-01", 0.00003, 0),
            ("2021-01-01", 0.00008, 0),
            ("2021-02-01", 0.00010, 0.5),
        ]
    ]
    request = validate_inputs(
        lat=28, lon=77, radius_km=1, cell_size_m=500, start_year=2019, end_year=2021
    )
    image = _no2_composite(ee.ImageCollection.fromImages(images), request)
    result = image.reduceRegion(
        ee.Reducer.first(), ee.Geometry.Point([77, 28]), 1000
    ).getInfo()
    assert result["no2_mol_m2"] == pytest.approx(0.00004)
