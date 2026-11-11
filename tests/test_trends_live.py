import pytest

from src.gee_auth import initialize_earth_engine
from src.trends import METRICS, analyze_trend, fetch_monthly, rolling_comparison
from src.validate import validate_inputs


@pytest.mark.live
def test_delhi_monthly_trends():
    initialize_earth_engine()
    request = validate_inputs(
        lat=28.61,
        lon=77.21,
        radius_km=5,
        cell_size_m=500,
        start_year=2019,
        end_year=2021,
    )
    monthly = fetch_monthly(request)
    assert len(monthly) == 36 and monthly.index.is_unique
    for metric in METRICS:
        values = monthly[f"roi_{metric}"]
        trend = analyze_trend(values)
        assert trend.slope_per_year is not None and 0 <= trend.p_value <= 1
        assert monthly[f"roi_{metric}_coverage"].dropna().between(0, 100.000001).all()
        assert rolling_comparison(monthly, metric).dropna().shape[0] > 0
    assert monthly.roi_day_c.dropna().between(0, 65).all()
    assert monthly.roi_night_c.dropna().between(-10, 55).all()
