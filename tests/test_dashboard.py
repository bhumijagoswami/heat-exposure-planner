import pytest
from streamlit.testing.v1 import AppTest

from src.demo import PRESETS, load_demo


@pytest.mark.parametrize("name", PRESETS)
def test_bundled_snapshots(name):
    request, cells, months = load_demo(name)
    assert cells.cell_id.is_unique and len(cells) >= 150
    assert cells.crs.is_projected and cells.geometry.is_valid.all()
    assert cells.lst_c.notna().any() and cells.population.sum() > 0
    assert len(months) == 12 * (request.end_year - request.start_year + 1)
    assert (
        months.index[0].year == request.start_year
        and months.index[-1].year == request.end_year
    )


def test_switch_presets_and_layers_without_earth_engine(monkeypatch):
    import ee

    def unexpected_call(*args, **kwargs):
        pytest.fail("Offline presets must not call Earth Engine")

    monkeypatch.setattr(ee, "Initialize", unexpected_call)
    monkeypatch.setattr(ee.data, "computeValue", unexpected_call)
    page = AppTest.from_file("../app.py", default_timeout=30).run()
    assert not page.exception
    assert [t.label for t in page.tabs] == [
        "Map",
        "Overview",
        "Drivers",
        "Trends",
        "Action Plan",
        "Briefing",
        "Methodology & Limits",
        "Comparison",
    ]
    assert all(
        any("How to read this" in box.value for box in tab.info) for tab in page.tabs
    )
    for name in PRESETS:
        page.sidebar.selectbox[0].select(name).run()
        request, _, scored = page.session_state.planner_input
        assert request.lat == PRESETS[name][1] and len(scored) >= 150
        assert page.session_state.trends_result[0] == request
        assert len(page.get("download_button")) == 4
    layer = next(item for item in page.selectbox if item.label == "Map layer")
    for name in layer.options:
        layer.select(name).run()
        assert not page.exception
    page.sidebar.selectbox[0].select("Custom live analysis").run()
    assert (
        "planner_input" not in page.session_state
        and "trends_result" not in page.session_state
    )


def test_compare_presets_and_custom_coordinates(monkeypatch):
    from src.ui import comparison

    _, cells, months = load_demo(next(iter(PRESETS)))
    calls = []

    def load(request, season):
        calls.append((request.lat, request.lon, season))
        return cells

    monkeypatch.setattr(comparison, "_load_cells", load)
    monkeypatch.setattr(comparison, "_load_monthly", lambda request: months)
    page = AppTest.from_file("../app.py", default_timeout=30).run()
    def compare():
        return next(b for b in page.button if b.label == "Compare areas")
    compare().click().run()
    tab = page.tabs[-1]
    assert not page.exception and len(tab.get("vega_lite_chart")) == 3
    assert any("hotter by" in h.value for h in tab.subheader)
    tab.selectbox[-1].select("Nitrogen dioxide").run()
    assert not page.exception
    tab.selectbox[0].select(comparison.CUSTOM).run()
    compare().click().run()
    assert not page.exception and calls == [(0.0, 0.0, "summer")]
