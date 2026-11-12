import geopandas as gpd
import pytest
from shapely.geometry import Point

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


