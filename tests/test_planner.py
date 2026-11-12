import numpy as np
import pandas as pd
import pytest

from src import planner
from src.extract import FRACTIONS


def candidates():
    cells = pd.DataFrame(0.0, index=range(8), columns=FRACTIONS)
    cells["cell_id"] = list("hg fedcba".replace(" ", ""))
    cells["area_m2"] = 10000
    cells["dw_frac_bare"] = 0.25
    cells["dw_frac_trees"] = 0.75
    cells["exposure_equal"] = [0.4, 0.4, 1, 0.9, 0.8, 0.7, np.nan, 0.2]
    cells.loc[2, ["dw_frac_built", "dw_frac_trees"]] = [0.5, 0.25]
    cells.loc[3, ["dw_frac_water", "dw_frac_trees"]] = [0.01, 0.74]
    cells.loc[4, "area_m2"] = 9999
    cells.loc[5, ["dw_frac_bare", "dw_frac_trees"]] = [0.24, 0.76]
    cells.loc[7, ["dw_frac_grass", "dw_frac_bare"]] = [0.25, 0]
    cells["exposure_air_forward"] = cells.exposure_equal
    cells.loc[7, "exposure_air_forward"] = 1
    return cells


def test_screening_ranking_ties_and_roi_coverage():
    cells = candidates()
    sites = planner.rank_sites(cells)
    assert list(sites.index) == ["g", "h", "a"]
    assert sites.cumulative_exposure_pct.to_list() == pytest.approx(
        100 * np.array([0.4, 0.8, 1.0]) / cells.exposure_equal.sum()
    )
    pd.testing.assert_frame_equal(sites, planner.rank_sites(cells.iloc[::-1]))
    pd.testing.assert_frame_equal(sites.head(1), planner.rank_sites(cells, top_n=1))
def test_no_sites_bad_classification_or_zero_total():
    cells = candidates()
    assert planner.rank_sites(cells.assign(exposure_equal=np.nan)).empty
    assert planner.rank_sites(cells.assign(dw_frac_grass=np.nan)).empty
    assert planner.rank_sites(cells.assign(dw_frac_grass=-0.1)).empty
    assert (
        planner.rank_sites(cells.assign(exposure_equal=0))
        .cumulative_exposure_pct.isna()
        .all()
    )


@pytest.mark.parametrize("value", ["25", True, -1, 101, float("inf"), float("nan")])
def test_invalid_scenario(value):
    with pytest.raises(ValueError, match="percent"):
        planner.shift_bare_to_trees(candidates(), value)


def test_bounds_for_rank_controls():
    for count in (False, -1, 101, 1.2):
        with pytest.raises(ValueError):
            planner.rank_sites(candidates(), top_n=count)


def test_composition_and_monotonic_converted_area():
    cells = candidates()
    previous = cells.dw_frac_trees
    for percent in (0, 20, 50, 100):
        changed = planner.shift_bare_to_trees(cells, percent)
        assert np.allclose(changed[FRACTIONS].sum(axis=1), 1)
        assert (changed.dw_frac_trees >= previous).all()
        assert np.allclose(
            changed.dw_frac_bare, cells.dw_frac_bare * (1 - percent / 100)
        )
        assert (
            changed[FRACTIONS].ge(0).all().all()
            and changed[FRACTIONS].le(1).all().all()
        )
        previous = changed.dw_frac_trees
        pd.testing.assert_frame_equal(
            changed.drop(columns=["dw_frac_trees", "dw_frac_bare"]),
            cells.drop(columns=["dw_frac_trees", "dw_frac_bare"]),
        )


def test_bootstrap_with_known_response_and_missing_model_cell(monkeypatch):
    from types import SimpleNamespace
    from sklearn.linear_model import LinearRegression

    features = pd.DataFrame(
        {"dw_frac_bare": np.linspace(0, 1, 60)}, index=[str(i) for i in range(60)]
    )
    features["dw_frac_trees"] = 1 - features.dw_frac_bare
    target = 30 + 8 * features.dw_frac_bare
    model = SimpleNamespace(
        forest=LinearRegression().fit(features, target),
        features=features,
        validation=pd.DataFrame(
            {"observed_c": target, "block": np.arange(60) // 10}, index=features.index
        ),
    )
    sites = features.loc[["0", "10", "59"]].assign(area_m2=10000)
    sites.loc["unknown"] = [0.4, 0.6, 10000]
    monkeypatch.setattr(planner, "BOOTSTRAP_REPLICATES", 12)
    previous = None
    for percent in [0, 25, 100]:
        result = planner.estimate_scenario(model, sites, percent)
        expected = -8 * sites.dw_frac_bare.iloc[:3] * percent / 100
        for col in ["delta_c", "lower_c", "upper_c"]:
            assert result[col].iloc[:3].to_numpy() == pytest.approx(expected.to_numpy())
            assert np.isnan(result.at["unknown", col])
        assert result.at["0", "converted_m2"] == 0
        assert result.at["unknown", "converted_m2"] == pytest.approx(
            4000 * percent / 100
        )
        if previous is not None:
            assert (result.converted_m2 >= previous.converted_m2).all()
            assert (result.delta_c.iloc[:3] <= previous.delta_c.iloc[:3]).all()
        previous = result


def test_airport_district_and_mixed_use_flags():
    import geopandas as gpd
    from shapely.geometry import Point

    rows = candidates().iloc[:2].copy()
    rows.iloc[1, rows.columns.get_loc("dw_frac_trees")] -= 0.1
    rows.iloc[1, rows.columns.get_loc("dw_frac_crops")] = 0.1
    cells = gpd.GeoDataFrame(
        rows, geometry=[Point(77.10, 28.55), Point(77.59, 12.97)], crs=4326
    )
    flags = planner.rank_sites(cells).land_use_review
    assert "Airport district" in flags["h"]
    assert "Airport district" not in flags["g"] and "crops" in flags["g"]
