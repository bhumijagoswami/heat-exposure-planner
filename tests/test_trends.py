import numpy as np
import pandas as pd
import pytest

from src import trends


def observations(n=72):
    t = np.arange(n)
    return pd.Series(
        20 + 0.1 * t + 8 * np.sin(2 * np.pi * t / 12),
        index=pd.date_range("2019-01-01", periods=n, freq="MS"),
    )


def test_annualized_calendar_slope_and_short_gaps():
    obs = observations()
    obs.iloc[[17, 18, 35]] = np.nan
    obs = obs.drop(obs.index[35])
    result = trends.analyze_trend(obs.sample(frac=1, random_state=42))
    assert result.slope_per_year == pytest.approx(1.2, abs=0.04)
    assert result.p_value < 0.01
    assert result.adjusted.isna().sum() == 3
    assert result.adjusted.std() < obs.std()


def test_decreasing_flat_and_all_missing():
    assert trends.analyze_trend(-observations()).slope_per_year == pytest.approx(-1.2)
    flat = observations() * 0 + 15
    result = trends.analyze_trend(flat)
    assert result.slope_per_year == 0 and result.p_value == 1
    assert trends.analyze_trend(flat * np.nan).slope_per_year is None


@pytest.mark.parametrize("gaps", [slice(3, 6), slice(None, None, 3)])
def test_gap_policy_declines_unreliable_fit(gaps):
    obs = observations()
    obs.iloc[gaps] = np.nan
    result = trends.analyze_trend(obs)
    assert result.p_value is None and result.adjusted.isna().all()
    assert result.note
    assert trends.analyze_trend(observations(23)).slope_per_year is None


def test_rolling_requires_three_adjacent_calendar_months():
    obs = observations(12)
    frame = pd.DataFrame({"core_day_c": obs, "green_day_c": obs - 2}).drop(
        index=obs.index[4]
    )
    roll = trends.rolling_comparison(frame, "day_c")
    assert roll.iloc[:2].isna().all().all()
    assert roll.iloc[4:7].isna().all().all()
    assert roll.iloc[7, 0] == pytest.approx(obs.iloc[5:8].mean())
    assert np.allclose(roll.dropna()["Urban core"] - roll.dropna()["Green"], 2)


def test_modis_scale_and_quality():
    from unittest.mock import MagicMock

    for period in ("Day", "Night"):
        dn = MagicMock()
        qc = MagicMock()
        image = MagicMock()
        image.select.side_effect = {
            f"LST_{period}_1km": dn,
            f"QC_{period}": qc,
        }.__getitem__
        trends._modis_temperature(image, period)
        dn.multiply.assert_called_once_with(0.02)
        scaled = dn.multiply.return_value.subtract
        scaled.assert_called_once_with(273.15)
        qc.bitwiseAnd.assert_called_once_with(3)
        scaled.return_value.updateMask.assert_called_once_with(
            qc.bitwiseAnd.return_value.eq.return_value
        )
        dn.gt.assert_called_once_with(0)


def test_trends_screen(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.ui import trends as ui

    obs = observations(36)
    frame = pd.DataFrame(index=obs.index)
    for metric in trends.METRICS:
        for zone in trends.ZONES:
            frame[f"{zone}_{metric}"] = obs
            frame[f"{zone}_{metric}_coverage"] = 90
    monkeypatch.setattr(ui, "_load_monthly", lambda request: frame)
    page = AppTest.from_file("../app.py", default_timeout=30).run()
    page.sidebar.selectbox[0].select("Custom live analysis").run()
    next(
        button for button in page.button if button.label == "Load monthly trends"
    ).click().run()
    assert not page.exception
    assert next(
        m for m in page.metric if m.label == "Estimated yearly change"
    ).value.endswith("°C/year")
    assert any("2020" in cap.value for cap in page.caption)
    assert len(page.get("vega_lite_chart")) == 2
    next(w for w in page.selectbox if w.label == "Measurement").select("no2").run()
    assert not page.exception
    assert next(
        m for m in page.metric if m.label == "Estimated yearly change"
    ).value.endswith("µmol/m²/year")


@pytest.mark.parametrize("failure", [None, "missing", "duplicate", "service"])
def test_monthly_batch_integrity(monkeypatch, failure):
    from unittest.mock import Mock
    from src.validate import validate_inputs

    request = validate_inputs(
        lat=10, lon=30, radius_km=2, cell_size_m=500, start_year=2020, end_year=2021
    )
    sdk = Mock()
    monkeypatch.setattr(trends, "ee", sdk)
    monkeypatch.setattr(trends, "_monthly_features", lambda request: None)
    batches = []
    for year in (2020, 2021):
        rows = [
            {"properties": {"month": f"{year}-{m:02d}", "roi_no2": -0.00001}}
            for m in range(12, 0, -1)
        ]
        batches.append({"features": rows})
    if failure == "missing":
        batches[-1]["features"].pop()
    elif failure == "duplicate":
        batches[-1]["features"][0] = batches[-1]["features"][1]
    elif failure == "service":
        batches[-1] = RuntimeError("sensitive test diagnostic")
    sdk.FeatureCollection.return_value.getInfo.side_effect = batches
    if failure:
        with pytest.raises(trends.TrendExtractionError) as exc:
            trends.fetch_monthly(request)
        assert "sensitive" not in str(exc.value)
    else:
        monthly = trends.fetch_monthly(request)
        assert len(monthly) == 24 and monthly.index.is_monotonic_increasing
        assert monthly.roi_no2.eq(-0.00001).all()
        assert monthly.green_day_c.isna().all()
    assert sdk.FeatureCollection.call_count == 2


def test_demo_no2_seasonal_fit_downweights_2020():
    from src.demo import PRESETS, load_demo

    for name in PRESETS:
        _, _, monthly = load_demo(name)
        observed = monthly.roi_no2
        result = trends.analyze_trend(observed)
        assert observed.count() == 36 and result.low_weight_2020 == 12
        spans = result.adjusted.groupby(result.adjusted.index.year).agg(
            lambda s: s.max() - s.min()
        )
        assert spans[2020] > max(spans[2019], spans[2021])
