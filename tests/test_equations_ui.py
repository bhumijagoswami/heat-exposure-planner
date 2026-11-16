from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.ui import drivers, equations

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_third_page_both_cities_and_all_views_offline(monkeypatch):
    monkeypatch.setattr(
        drivers,
        "initialize_app_earth_engine",
        lambda: pytest.fail("Requested credentials"),
    )
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    app.radio[0].set_value("Heat vs pollution").run()
    for city in equations.CITIES:
        app.radio(key="eq_city").set_value(city).run()
        for view in equations.VIEWS:
            app.radio(key="eq_view").set_value(view).run()
            assert not app.exception and not app.error and not app.warning
            assert len(app.get("vega_lite_chart")) == 3
            assert len(app.latex) == 1
            assert any("R² =" in item.value for item in app.markdown)


def test_chart_failure_is_friendly_and_other_sections_render(monkeypatch):
    app = AppTest.from_file(str(APP), default_timeout=30).run()

    def fail(*args, **kwargs):
        raise ValueError("sensitive backend detail")

    monkeypatch.setattr(equations, "_risk_chart", fail)
    app.radio[0].set_value("Heat vs pollution").run()
    assert not app.exception
    assert len(app.warning) == 1 and "sensitive" not in app.warning[0].value
    assert len(app.get("vega_lite_chart")) == 2
