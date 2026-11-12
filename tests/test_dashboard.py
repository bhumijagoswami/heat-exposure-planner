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
