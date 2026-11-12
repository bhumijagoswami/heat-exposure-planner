import pytest

from src.extract import extract_cells
from src.gee_auth import initialize_earth_engine
from src.index import score_exposure
from src.validate import validate_inputs


@pytest.mark.live
def test_delhi_exposure_scoring():
    initialize_earth_engine()
    request = validate_inputs(
        lat=28.61,
        lon=77.21,
        radius_km=1,
        cell_size_m=500,
        start_year=2023,
        end_year=2023,
    )
    extraction = extract_cells(request, season="summer")
    result = score_exposure(extraction.cells)
    valid = result.dropna(subset=["exposure_equal"])
    assert len(valid) > 5
    assert valid.lst_c.nunique() > 1
    assert valid.population.nunique() > 1
    assert result.crs == extraction.cells.crs
