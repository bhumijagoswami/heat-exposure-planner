import pytest

from src.demo import PRESETS, load_demo


@pytest.mark.parametrize("name", PRESETS)
def test_bundled_snapshots(name):
    _, cells = load_demo(name)
    assert cells.cell_id.is_unique and len(cells) >= 150
    assert cells.crs.is_projected and cells.geometry.is_valid.all()
    assert cells.lst_c.notna().any() and cells.population.sum() > 0


def test_story_and_comparison():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("../app.py", default_timeout=60).run()
    assert not app.exception
    assert len(app.metric) == 3
    assert any("What to do first" == item.value for item in app.subheader)
    assert len([item for item in app.markdown if "maps/search" in item.value]) == 5
    app.radio[0].set_value("Compare two places").run()
    assert not app.exception
    assert len(app.metric) == 6


def test_compare_custom_place_with_missing_observations(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.ui import comparison

    _, cells = load_demo(next(iter(PRESETS)))
    calls = []

    def load(request, season):
        calls.append((request, season))
        return cells.assign(lst_c=float("nan"))

    monkeypatch.setattr(comparison, "_load_cells", load)
    page = AppTest.from_string(
        "from src.ui.comparison import render_comparison\nrender_comparison()"
    ).run()
    page.selectbox[1].select(comparison.CUSTOM).run()
    page.button[0].click().run()
    assert not page.exception
    assert calls[0][0].start_year == 2019 and calls[0][1] == "summer"
    assert any(item.value == "No readings" for item in page.metric)
