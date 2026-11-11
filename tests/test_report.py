import json
from html.parser import HTMLParser
from io import BytesIO
from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box, shape

from src.extract import FRACTIONS
from src.grid import build_grid
from src.report import Report, build_report
from src.validate import validate_inputs


def request(**overrides):
    args = dict(lat=28.6, lon=77.2, radius_km=1, cell_size_m=500)
    return validate_inputs(**(args | overrides))


def sample():
    table = pd.DataFrame(0.0, index=range(4), columns=FRACTIONS)
    table = table.assign(
        cell_id=["A", "B", "C", "D"],
        area_m2=[10000, 20000, 30000, 40000],
        coverage_pct=[100, 100, 0, 50],
        population=[50, 20, 10, 20],
        exposure_equal=[0.8, 0.8, float("nan"), 0.4],
        robust_priority=pd.array([True, False, None, False], dtype="boolean"),
        dw_frac_bare=0.4,
        dw_frac_trees=0.6,
    )
    return gpd.GeoDataFrame(
        table,
        geometry=[
            box(500000 + i * 150, 3000000, 500100 + i * 150, 3000100) for i in range(4)
        ],
        crs=32643,
    )


class HtmlText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, text):
        self.parts.append(text)


def test_brief_matches_tables_and_escapes_html():
    cells = sample()
    scenario = pd.DataFrame(
        dict(
            converted_m2=[1000.0, 2000.0],
            delta_c=[-0.45, 0.0],
            lower_c=[-0.8, -0.1],
            upper_c=[0.2, 0.15],
        ),
        index=pd.Index(["A", "B"], name="cell_id"),
    )
    model = SimpleNamespace(
        features=cells,
        r2=0.6,
        rmse_c=1.1,
        importance=pd.Series(
            [1.5, 0.2, 0.8, 0.4], index=["ndvi", "test", "slope_deg", "ndbi"]
        ),
    )
    report = build_report(
        cells, request(), "annual", top_n=2, model=model, scenario=scenario
    )
    brief = report.markdown()
    for value in (
        "3 of 4",
        "Joint valid-area coverage is 50.0%",
        "50.0%",
        "50 residents",
        "10 estimated residents",
        "80.0%",
        "3,000 m²",
        "-0.45",
        "+0.20 °C",
        "NDVI (1.500 °C)",
        "RMSE 1.10 °C",
    ):
        assert value in brief
    assert "test (0.200" not in brief
    assert brief.index("1. Cell A") < brief.index("2. Cell B")
    html = HtmlText()
    html.feed(report.html())
    for _, paragraphs in report.sections:
        assert all(p in html.parts for p in paragraphs)
    hostile = Report(cells, [("Safety", ["<img src=x> & notes"])])
    assert "<img" not in hostile.html() and "<img" not in hostile.markdown()
    assert "planner_rank" not in cells


def test_export_round_trip():
    report = build_report(sample(), request(), "annual", top_n=1)
    csv = pd.read_csv(BytesIO(report.csv())).set_index("cell_id")
    raw = report.geojson()
    features = json.loads(raw)["features"]
    assert len(features) == 4 and csv.planner_rank.count() == 1
    assert csv.loc["A", "planner_rank"] == 1
    assert pd.isna(csv.loc["C", "exposure_equal"])
    props = next(f["properties"] for f in features if f["properties"]["cell_id"] == "C")
    assert props["robust_priority"] is None and props["exposure_equal"] is None
    decoded = gpd.read_file(BytesIO(raw)).set_index("cell_id")
    assert decoded.crs.to_epsg() == 4326
    assert decoded.geometry.is_valid.all()
    assert csv.latitude.between(26, 28).all() and csv.longitude.between(74, 76).all()
    assert csv.longitude.loc["A"] == pytest.approx(
        decoded.geometry.loc["A"].centroid.x, abs=1e-6
    )


@pytest.mark.parametrize("lon", [180, -180])
def test_geojson_splits_antimeridian(lon):
    grid = build_grid(request(lat=0, lon=lon)).cells
    features = json.loads(Report(grid, []).geojson())["features"]
    assert len(features) == len(grid)
    for feature in features:
        polygon = shape(feature["geometry"])
        assert polygon.is_valid
        for part in getattr(polygon, "geoms", [polygon]):
            assert part.bounds[2] - part.bounds[0] < 1


def test_unknown_and_zero_population_and_stale_scenario():
    cells = sample()
    assert (
        "share is unavailable"
        in build_report(cells.assign(population=0), request(), "annual").markdown()
    )
    masked = cells.assign(exposure_equal=float("nan"), robust_priority=pd.NA)
    brief = build_report(masked, request(), "annual").markdown()
    assert (
        "No cells have a valid exposure score" in brief
        and "could not be assessed" in brief
    )
    with pytest.raises(ValueError, match="Scenario cells"):
        build_report(cells, request(), "annual", scenario=pd.DataFrame(index=["X"]))


def test_briefing_screen(monkeypatch):
    from streamlit.testing.v1 import AppTest

    cells = sample()
    from src.ui import drivers
    from src.model import InsufficientDriverData

    monkeypatch.setattr(
        drivers,
        "_load_cells",
        lambda *args: cells.assign(lst_c=30, no2_mol_m2=0.0001, ndvi=0.4),
    )

    def no_model(cells):
        raise InsufficientDriverData("Insufficient cells")

    monkeypatch.setattr(drivers, "fit_drivers", no_model)
    app = AppTest.from_file("../app.py", default_timeout=30).run()
    app.sidebar.selectbox[0].select("Custom live analysis").run()
    next(
        button for button in app.button if button.label == "Analyze area"
    ).click().run()
    assert not app.exception
    assert len(app.get("download_button")) == 4
    assert any("driver model is unavailable" in t.value for t in app.text)
