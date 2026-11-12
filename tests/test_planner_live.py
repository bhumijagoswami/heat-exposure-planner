import pytest

from src.extract import extract_cells
from src.gee_auth import initialize_earth_engine
from src.index import score_exposure
from src.model import fit_drivers
from src.planner import estimate_scenario, rank_sites
from src.validate import validate_inputs


@pytest.mark.live
def test_delhi_planting_scenario():
    initialize_earth_engine()
    request = validate_inputs(
        lat=28.55,
        lon=77.10,
        radius_km=5,
        cell_size_m=500,
        start_year=2023,
        end_year=2023,
    )
    cells = extract_cells(request, season="summer").cells
    sites = rank_sites(score_exposure(cells))
    assert 0 < len(sites) <= 10
    assert sites.exposure.is_monotonic_decreasing
    assert sites.cumulative_exposure_pct.is_monotonic_increasing
    estimates = estimate_scenario(fit_drivers(cells), sites, 25)
    assert (estimates.converted_m2 > 0).any()
    assert estimates.delta_c.notna().all()
    assert (estimates.lower_c <= estimates.upper_c).all()
