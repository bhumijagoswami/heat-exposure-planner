import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point
from sklearn.metrics import r2_score, root_mean_squared_error

from src import model


@pytest.fixture
def cells():
    rows = []
    for i in range(180):
        x, y = i % 15, i // 15
        tree = ((11 * i) % 31) / 30
        row = dict.fromkeys(model.FEATURES, 0.0)
        row.update(
            area_m2=166000.0,
            coverage_pct=100.0,
            population=200 + i,
            cell_id=f"cell-{i:03d}",
            dw_frac_trees=tree,
            dw_frac_built=1 - tree,
            ndvi=tree * 0.8,
            ndbi=(1 - tree) * 0.7,
            mndwi=-0.2,
            elevation_m=y,
            slope_deg=x / 4,
            lst_c=40 - 7 * tree + y / 10,
            geometry=Point(x * 500, y * 500).buffer(230),
            no2_mol_m2=40 - 7 * tree + y / 10,
        )
        rows.append(row)
    return gpd.GeoDataFrame(rows, crs=32643)


def test_spatial_validation_and_local_explanations(cells, monkeypatch):
    monkeypatch.setattr(model, "MAX_SHAP_CELLS", 20)
    cells.loc[0, "slope_deg"] = float("inf")
    cells.loc[1, "lst_c"] = float("nan")
    result = model.fit_drivers(cells)
    assert result.excluded_cells == 2
    assert len(result.features) == 178
    assert set(result.features.columns) == set(model.FEATURES)
    assert {"no2_mol_m2", "lst_c", "population", "cell_id"}.isdisjoint(result.features)
    held_out = result.validation
    assert held_out.held_out_c.notna().all()
    assert held_out.fold.nunique() == 5
    assert held_out.groupby("block").fold.nunique().max() == 1
    assert result.r2 == pytest.approx(
        r2_score(held_out.observed_c, held_out.held_out_c)
    )
    assert result.rmse_c == pytest.approx(
        root_mean_squared_error(held_out.observed_c, held_out.held_out_c)
    )
    assert result.r2 > 0.8
    assert len(result.contributions) == 20
    assert result.importance.is_monotonic_decreasing
    pd.testing.assert_series_equal(
        result.importance.sort_index(), result.contributions.abs().mean().sort_index()
    )
    sample = result.contributions.index[0]
    outside = result.features.index.difference(result.contributions.index)[0]
    for cell in [sample, outside]:
        estimate = result.baseline_c + result.explain_cell(cell).sum()
        assert estimate == pytest.approx(
            result.forest.predict(result.features.loc[[cell]])[0]
        )
    shuffled = model.fit_drivers(cells.sample(frac=1, random_state=27))
    pd.testing.assert_frame_equal(shuffled.validation, result.validation)
    pd.testing.assert_frame_equal(shuffled.contributions, result.contributions)


def test_skip_small_or_masked_area(cells):
    with pytest.raises(model.InsufficientDriverData, match="149"):
        model.fit_drivers(cells.iloc[:149])
    cells.loc[:40, "ndvi"] = float("nan")
    with pytest.raises(model.InsufficientDriverData, match="139"):
        model.fit_drivers(cells)


def test_skip_degenerate_area(cells):
    with pytest.raises(ValueError, match="metres"):
        model.fit_drivers(cells.to_crs(4326))
    with pytest.raises(model.InsufficientDriverData, match="constant"):
        model.fit_drivers(cells.assign(lst_c=20))
    cells = cells.set_geometry([cells.geometry.iloc[0]] * len(cells))
    with pytest.raises(model.InsufficientDriverData, match="three"):
        model.fit_drivers(cells)


def test_drivers_screen(cells, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.ui import drivers

    monkeypatch.setattr(drivers, "_load_cells", lambda request, season: cells)
    page = AppTest.from_file("../app.py", default_timeout=40).run()
    page.sidebar.selectbox[0].select("Custom live analysis").run()
    assert not page.exception
    next(b for b in page.button if b.label == "Analyze area").click().run()
    assert not page.exception
    assert not page.warning
    assert {metric.label for metric in page.tabs[2].metric} == {
        "Spatial CV R²",
        "Spatial CV RMSE (°C)",
    }
    assert len(page.dataframe) == 2
    next(widget for widget in page.selectbox if widget.label == "Cell ID").select(
        "cell-150"
    ).run()
    assert not page.exception
    assert len(page.dataframe[-1].value) == len(model.FEATURES)
