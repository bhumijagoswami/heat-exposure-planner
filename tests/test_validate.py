import pytest

from src.validate import AnalysisRequest, validate_inputs


def request(**changes):
    defaults = dict(lat=37, lon=-122, radius_km=5, cell_size_m=500)
    return validate_inputs(**(defaults | changes))


@pytest.mark.parametrize(
    ("field", "bad", "message"),
    [
        ("lat", float("nan"), "Latitude"),
        ("lat", float("inf"), "Latitude"),
        ("lon", -float("inf"), "Longitude"),
        ("lon", 181, "Longitude"),
        ("lat", "37", "Latitude"),
        ("lon", "<script>", "Longitude"),
        ("lat", True, "Latitude"),
        ("radius_km", float("nan"), "Radius"),
        ("radius_km", float("inf"), "Radius"),
        ("radius_km", "5", "Radius"),
        ("radius_km", -1, "Radius"),
        ("radius_km", 0.9, "Radius"),
        ("radius_km", 10**1000, "Radius"),
        ("cell_size_m", 501, "Cell size"),
        ("cell_size_m", 500.0, "Cell size"),
        ("cell_size_m", "500", "Cell size"),
        ("start_year", 2018, "Start year"),
        ("end_year", 2026, "End year"),
        ("start_year", 2021.5, "Start year"),
        ("end_year", float("nan"), "End year"),
        ("start_year", "2020", "Start year"),
    ],
)
def test_invalid_field(field, bad, message):
    with pytest.raises(ValueError, match=message):
        request(**{field: bad})


def test_detectable_coordinate_swap():
    with pytest.raises(ValueError, match="Latitude"):
        request(lat=-122, lon=37)


def test_in_range_coordinate_order_is_preserved():
    result = request(lat=77, lon=28)
    assert (result.lat, result.lon) == (77, 28)


@pytest.mark.parametrize(("lat", "lon"), [(-90, -180), (90, 180)])
def test_inclusive_limits(lat, lon):
    assert request(lat=lat, lon=lon, radius_km=15, cell_size_m=1000) == AnalysisRequest(
        lat, lon, 15, 1000, 2019, 2025
    )


def test_minimum_radius_and_single_year():
    assert (
        request(radius_km=1, cell_size_m=250, start_year=2020, end_year=2020).radius_km
        == 1
    )


def test_reversed_years():
    with pytest.raises(ValueError, match="Start year"):
        request(start_year=2025, end_year=2019)


def test_grid_budget_depends_on_resolution():
    with pytest.raises(ValueError, match="2500 cells"):
        request(radius_km=8, cell_size_m=250)
    assert request(radius_km=8, cell_size_m=500).cell_size_m == 500
