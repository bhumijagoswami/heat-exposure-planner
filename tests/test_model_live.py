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
    assert model.validation.block.nunique() >= 3
