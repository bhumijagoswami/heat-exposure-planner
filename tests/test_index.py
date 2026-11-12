import pandas as pd
import pytest

from src.index import score_exposure


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
    scored = result
    assert scored.loc["a", "lst_anomaly_c"] == pytest.approx(10 - 200 / 6)
    assert scored.hazard_equal.tolist() == pytest.approx([0.1, 0.3, 0.5, 0.7, 0.9])
    assert scored.exposure_equal.tolist() == pytest.approx([0, 0.09, 0.25, 0.49, 0.81])
    pd.testing.assert_frame_equal(
        score_exposure(cells.iloc[::-1]).sort_index(), scored
    )


def test_masked_inputs_keep_rows_and_unweighted_scores():
    cells = sample()
    cells.loc["a", "lst_c"] = float("nan")
    cells.loc["b", "population"] = float("nan")
    cells.loc["c", "coverage_pct"] = 0
    result = score_exposure(cells)
    assert result.index.equals(cells.index)
    assert pd.isna(result.loc["a", "hazard_equal"])
    assert result.loc[["b", "c"], "hazard_equal"].notna().all()
    assert (
        result.loc[["a", "b", "c"], ["exposure_equal"]]
        .isna()
        .all()
        .all()
    )


def test_ties_empty_and_no_data():
    cells = sample()
    cells.loc[:, :] = 1
    result = score_exposure(cells)
    assert result.hazard_equal.eq(0.5).all()
    for empty in (cells.iloc[:0], cells.astype(float) * float("nan")):
        result = score_exposure(empty)
        assert len(result) == len(empty)
