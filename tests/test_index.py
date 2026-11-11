import pandas as pd
import pytest

from src.index import SCHEMES, score_exposure


def sample():
    return pd.DataFrame(
        {
            "cell_id": list("abcde"),
            "area_m2": [1, 1, 1, 1, 2],
            "lst_c": [10, 20, 30, 40, 50],
            "no2_mol_m2": [-1, 0, 1, 2, 3],
            "ndvi": [1, 0.5, 0, -0.5, -1],
            "population": [0, 10, 20, 30, 40],
            "coverage_pct": [100] * 5,
        }
    ).set_index("cell_id")


def test_known_scores_robust_quintile_and_correlations():
    cells = sample()
    result = score_exposure(cells)
    scored = result.cells
    assert scored.loc["a", "lst_anomaly_c"] == pytest.approx(10 - 200 / 6)
    assert scored.hazard_equal.tolist() == pytest.approx([0.1, 0.3, 0.5, 0.7, 0.9])
    assert scored.exposure_equal.tolist() == pytest.approx([0, 0.09, 0.25, 0.49, 0.81])
    assert scored.robust_priority.tolist() == [False, False, False, False, True]
    assert result.sensitivity.columns.tolist() == list(SCHEMES)
    assert (result.sensitivity == 1).all().all()
    assert "robust_priority" not in cells
    pd.testing.assert_frame_equal(
        score_exposure(cells.iloc[::-1]).cells.sort_index(), scored
    )


def test_scheme_weights_change_priority_and_sensitivity():
    cells = sample()
    cells["population"] = 20
    cells["ndvi"] = 0.2
    cells["no2_mol_m2"] = cells.no2_mol_m2[::-1].to_numpy()
    result = score_exposure(cells)
    row = result.cells.loc["e"]
    assert row.hazard_heat_forward == pytest.approx((2 * 0.9 + 0.1 + 0.5) / 4)
    assert row.hazard_air_forward == pytest.approx((0.9 + 2 * 0.1 + 0.5) / 4)
    assert row.hazard_green_deficit_forward == pytest.approx(0.5)
    assert not result.cells.robust_priority.any()
    assert result.sensitivity.loc["heat_forward", "air_forward"] == pytest.approx(-1)


def test_masked_inputs_keep_rows_and_unweighted_scores():
    cells = sample()
    cells.loc["a", "lst_c"] = float("nan")
    cells.loc["b", "population"] = float("nan")
    cells.loc["c", "coverage_pct"] = 0
    result = score_exposure(cells).cells
    assert result.index.equals(cells.index)
    assert pd.isna(result.loc["a", "hazard_equal"])
    assert result.loc[["b", "c"], "hazard_equal"].notna().all()
    assert (
        result.loc[["a", "b", "c"], ["exposure_equal", "robust_priority"]]
        .isna()
        .all()
        .all()
    )


def test_ties_empty_and_no_data():
    cells = sample()
    cells.loc[:, :] = 1
    result = score_exposure(cells)
    assert result.cells.hazard_equal.eq(0.5).all()
    assert not result.cells.robust_priority.any()
    assert result.sensitivity.isna().all().all()
    for empty in (cells.iloc[:0], cells.astype(float) * float("nan")):
        result = score_exposure(empty)
        assert len(result.cells) == len(empty)
        assert result.cells.robust_priority.isna().all()
        assert result.sensitivity.isna().all().all()
