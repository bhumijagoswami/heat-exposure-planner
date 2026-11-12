import pytest

from src.demo import PRESETS, load_demo


@pytest.mark.parametrize("name", PRESETS)
def test_bundled_snapshots(name):
    _, cells = load_demo(name)
    assert cells.cell_id.is_unique and len(cells) >= 150
    assert cells.crs.is_projected and cells.geometry.is_valid.all()
    assert cells.lst_c.notna().any() and cells.population.sum() > 0


def test_story():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("../app.py", default_timeout=30).run()
    app.selectbox[0].select("Bengaluru · central district").run()
    assert not app.exception
    assert len(app.metric) == 3
    assert len(app.get("iframe")) == 1
    assert sum("Monthly area averages" in c.value for c in app.caption) == 2
    assert any("5 zones to check first" == item.value for item in app.subheader)


def test_compare_custom_place_with_missing_observations(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.ui import drivers
    from src.ui.places import preset

    saved = preset(next(iter(PRESETS)))
    calls = []

    def load(request, season):
        calls.append((request, season))
        return saved.cells.assign(lst_c=float("nan"))

    monkeypatch.setattr(drivers, "_load_cells", load)
    monkeypatch.setattr(drivers, "_load_monthly", lambda request: saved.months)
    page = AppTest.from_file("../app.py").run()
    page.radio[0].set_value("Compare two places").run()
    assert not page.exception and len(page.get("iframe")) == 2
    assert any("7.5 °C apart" in item.value for item in page.caption)
    assert any("7.5 °C apart" in item.value for item in page.expander[-1].caption)
    page.radio[1].set_value("Combined risk").run()
    assert not page.exception and len(page.get("iframe")) == 2
    assert page.table[0].value.shape == (6, 2)
    page.checkbox[1].check().run()
    page.button[0].click().run()
    assert not page.exception
    assert calls[0][0].start_year == 2019 and calls[0][1] == "summer"
    assert "No readings" in page.table[0].value.iloc[0].tolist()


def test_compare_temperature_is_centered_within_each_place(monkeypatch):
    from src.ui import places

    selected = [places.preset(name) for name in PRESETS]
    charts = []
    monkeypatch.setattr(
        places.st, "altair_chart", lambda chart, **kwargs: charts.append(chart)
    )
    places.monthly_line(selected, "roi_day_c")
    points = charts[0].layer[1].data
    for (_, observed), place in zip(points.groupby("Place"), selected):
        raw = place.months.roi_day_c.dropna()
        assert observed.Reading.tolist() == pytest.approx((raw - raw.mean()).tolist())
        assert observed.Month.tolist() == raw.index.tolist()
