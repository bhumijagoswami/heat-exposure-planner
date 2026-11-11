import pytest

from src.extract import extract_cells
from src.gee_auth import initialize_earth_engine
from src.model import fit_drivers
from src.validate import validate_inputs


@pytest.mark.live
def test_delhi_spatial_driver_model():
    initialize_earth_engine()
    request = validate_inputs(
        lat=28.61,
        lon=77.21,
        radius_km=5,
        cell_size_m=500,
        start_year=2023,
        end_year=2023,
    )
    model = fit_drivers(extract_cells(request, season="summer").cells)
    assert model.validation.groupby("block").fold.nunique().max() == 1
    assert model.validation.fold.nunique() == 5
    assert model.rmse_c > 0
    assert model.r2 <= 1
    row = model.features.iloc[[0]]
    estimated = model.baseline_c + model.explain_cell(row.index[0]).sum()
    assert estimated == pytest.approx(model.forest.predict(row)[0])
