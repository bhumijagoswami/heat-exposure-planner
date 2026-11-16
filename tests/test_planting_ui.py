from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.ui import planting

APP = Path(__file__).resolve().parents[1] / "app.py"


def _button(app):
    return next(button for button in app.button if button.label == "Run planting model")


def test_planting_results_persist_and_clear_when_place_changes(monkeypatch):
    calls = []
    real_run = planting.run_planting

    def run(cells):
        calls.append(len(cells))
        return real_run(cells)

    monkeypatch.setattr(planting, "run_planting", run)
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not app.exception and not calls
    assert len(app.latex) == 1
    for city in ("Delhi · central", "Bengaluru · central district"):
        app.selectbox[0].select(city).run()
        app.session_state["last_compute_started"] = -1000
        _button(app).click().run()
        assert not app.exception and not app.warning
        assert len(app.metric) == 6
        assert "story_planting_result" in app.session_state
        assert 1 <= len(app.dataframe[0].value) <= 5
        values = [metric.value for metric in app.metric]
        before = len(calls)
        app.radio[1].set_value("Tree cover").run()
        assert not app.exception and len(calls) == before
        assert [metric.value for metric in app.metric] == values
    assert len(calls) == 2
    app.selectbox[0].select("Delhi · central").run()
    assert len(app.metric) == 3
    assert "story_planting_result" not in app.session_state


def test_interval_spanning_zero_does_not_claim_warming(monkeypatch):
    sites = pd.DataFrame(
        {
            "exposure": [0.8],
            "converted_m2": [100],
            "delta_c": [0.1],
            "lower_c": [-0.2],
            "upper_c": [0.4],
            "land_use_review": ["Check access"],
        },
        index=["site-a"],
    )
    monkeypatch.setattr(
        planting, "run_planting", lambda cells: {"sites": sites, "r2": 0.3, "rmse": 1}
    )
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    _button(app).click().run()
    assert not app.exception
    assert app.metric[-2].value == "Inconclusive"
    assert any(
        "No clear cooling effect here; treat as inconclusive" == item.value
        for item in app.info
    )
    assert app.dataframe[0].value["Estimated change"].tolist() == ["Inconclusive"]


@pytest.mark.parametrize("reason", ["few cells", "few blocks"])
def test_insufficient_model_data_is_friendly(monkeypatch, reason):
    def fail(cells):
        raise planting.InsufficientDriverData(reason)

    monkeypatch.setattr(planting, "fit_drivers", fail)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    _button(app).click().run()
    assert not app.exception
    assert any("150 complete zones and three 2 km" in item.value for item in app.info)


def test_model_failure_is_redacted(monkeypatch):
    def fail(cells):
        raise ValueError("sensitive backend detail")

    monkeypatch.setattr(planting, "run_planting", fail)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    _button(app).click().run()
    assert not app.exception and len(app.warning) == 1
    assert "sensitive" not in app.warning[0].value


def test_zero_or_unknown_effect_is_not_described_as_warming():
    assert planting.change_words(0, 0, 0) == "Inconclusive"
    assert planting.change_words(0.1, -0.1, 0.3) == "Inconclusive"
    assert planting.change_words(np.nan, np.nan, np.nan) == "Insufficient readings"
