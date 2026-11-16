import numpy as np
import pandas as pd
import pytest

from src.index import score_exposure
from src.relationships import (
    fit_line,
    heat_drivers,
    month_points,
    risk_breakdown,
    strength_words,
    zone_points,
)


def test_breakdown_matches_map_with_ties_missing_data_and_zero_residents():
    cells = pd.DataFrame(
        {
            "cell_id": list("abcde"),
            "area_m2": [100] * 5,
            "coverage_pct": [100] * 5,
            "lst_c": [30, 30, 40, 50, np.nan],
            "no2_mol_m2": [1, 2, 3, 4, 5],
            "ndvi": [0.1, 0.2, 0.3, 0.4, 0.5],
            "population": [0, 10, 20, np.nan, 50],
        }
    )
    top = risk_breakdown(cells).set_index("cell_id")
    map_scores = score_exposure(cells).set_index("cell_id")
    assert top.index.tolist() == ["c", "b", "a"]
    assert top.loc["a", "exposure_equal"] == 0
    assert top.loc["a", "heat_rank"] == top.loc["b", "heat_rank"] == 0.25
    assert top["exposure_equal"].tolist() == pytest.approx(
        map_scores.loc[top.index, "exposure_equal"]
    )
    assert top[["Heat", "Air pollution (NO₂)", "Lack of greenery"]].sum(
        axis=1
    ).tolist() == pytest.approx(top.hazard_equal)


def test_ols_recovers_coefficients_and_percentage_point_effects():
    x = np.array([0, 1, 2, 3, 4, np.inf])
    fit = fit_line(pd.DataFrame({"x": x, "y": 4 - 2 * x}))
    assert (fit["a"], fit["b"], fit["r2"], fit["n"]) == pytest.approx((4, -2, 1, 5))
    built, trees = (
        np.array([0, 0.2, 0.4, 0.2, 0.5]),
        np.array([0.1, 0.2, 0.1, 0.5, 0.3]),
    )
    fit = heat_drivers(
        pd.DataFrame(
            {
                "lst_c": 30 + 3 * built - 2 * trees,
                "dw_frac_built": built,
                "dw_frac_trees": trees,
            }
        )
    )
    assert (fit["a"], fit["built"] / 10, fit["trees"] / 10, fit["r2"]) == pytest.approx(
        (30, 0.3, -0.2, 1)
    )


def test_constant_or_singular_data_cannot_support_a_fit():
    assert fit_line(pd.DataFrame({"x": [1] * 5, "y": range(5)})) is None
    assert fit_line(pd.DataFrame({"x": range(5), "y": [1] * 5})) is None
    assert fit_line(pd.DataFrame({"x": [1, 2], "y": [3, 4]})) is None
    assert (
        heat_drivers(
            pd.DataFrame(
                {
                    "lst_c": range(5),
                    "dw_frac_built": range(5),
                    "dw_frac_trees": range(5),
                }
            )
        )
        is None
    )


def test_season_removal_uses_paired_calendar_months_and_drops_singletons():
    monthly = pd.DataFrame(
        {
            "roi_day_c": [10, 14, 20, 24, 50, 70, np.inf],
            "roi_no2": np.array([1, 5, 2, 8, 50, 70, 90]) / 1e6,
        },
        index=[
            "2019-01-01",
            "2020-01-01",
            "2019-02-01",
            "2021-02-01",
            "2019-03-01",
            "bad date",
            "2020-03-01",
        ],
    )
    monthly.index.name = "month"
    raw = month_points(monthly)
    assert len(raw) == 5
    adjusted = month_points(monthly, True)
    assert adjusted.x.tolist() == [-2, 2, -2, 2]
    assert adjusted.y.tolist() == pytest.approx([-2, 2, -3, 3])
    assert month_points(monthly.iloc[:1], True).empty


@pytest.mark.parametrize(
    "r2,word", [(0, "almost no"), (0.05, "weak"), (0.2, "moderate"), (0.5, "strong")]
)
def test_strength_boundaries(r2, word):
    assert word in strength_words(r2)


@pytest.mark.parametrize(
    "city,zone,monthly,drivers",
    [
        (
            "Delhi central",
            (91.62, 0.387, 0.032, 353),
            (-8.536, 0.598, 29),
            (38.65, 2.76, -2.47, 0.370, 353),
        ),
        (
            "Bengaluru central",
            (44.26, -0.251, 0.039, 355),
            (-1.734, 0.043, 23),
            (30.72, 3.44, -1.73, 0.295, 322),
        ),
    ],
)
def test_bundled_equation_sanity_values(city, zone, monthly, drivers):
    from src.ui.equations import load_cells, load_monthly

    cells = load_cells(city)
    fit = fit_line(zone_points(cells))
    assert [fit[k] for k in ("a", "b", "r2", "n")] == pytest.approx(zone, abs=0.005)
    fit = fit_line(month_points(load_monthly(city)))
    assert [fit[k] for k in ("b", "r2", "n")] == pytest.approx(monthly, abs=0.001)
    fit = heat_drivers(cells)
    assert [fit[k] for k in ("a", "built", "trees", "r2", "n")] == pytest.approx(
        drivers, abs=0.005
    )
