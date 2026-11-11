from time import monotonic

import pytest

from src.extract import extract_cells
from src.gee_auth import initialize_earth_engine
from src.validate import validate_inputs


@pytest.mark.live
def test_default_delhi_extraction_under_one_minute():
    initialize_earth_engine()
    request = validate_inputs(lat=28.61, lon=77.21, radius_km=5, cell_size_m=500)
    start = monotonic()
    result = extract_cells(request)
    elapsed = monotonic() - start
    assert 0 < len(result.cells) <= 2500
    assert 0 < result.area_coverage_pct <= 100
    assert result.cells.population.sum() > 0
    assert result.cells.lst_c.notna().any()
    assert elapsed < 60, f"Default extraction took {elapsed:.1f} seconds"


@pytest.mark.live
def test_pacific_keeps_unscored_cells():
    from src.index import score_exposure

    initialize_earth_engine()
    request = validate_inputs(
        lat=0, lon=-140, radius_km=1, cell_size_m=500, start_year=2023, end_year=2023
    )
    result = extract_cells(request)
    assert len(result.cells) > 0
    assert result.area_coverage_pct == 0
    assert result.cells.population.isna().all()
    assert score_exposure(result.cells).cells.exposure_equal.isna().all()
