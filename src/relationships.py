"""Descriptive equations for the bundled observations; no causal interpretation."""

import numpy as np
import pandas as pd

from src.index import score_exposure


def _finite(frame):
    return frame.apply(pd.to_numeric, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )


def risk_breakdown(cells):
    """Use the map's reference sets, coverage rules and equal-weight score."""
    scored = score_exposure(cells)
    top = (
        scored.dropna(subset=["exposure_equal"])
        .sort_values(
            ["exposure_equal", "cell_id"], ascending=[False, True], kind="stable"
        )
        .head(10)
        .copy()
    )
    for name, field in (
        ("Heat", "heat_rank"),
        ("Air pollution (NO₂)", "no2_rank"),
        ("Lack of greenery", "green_deficit"),
    ):
        top[name] = top[field] / 3
    top["Zone"] = [f"#{i + 1}" for i in range(len(top))]
    return top


def _ols(frame, target, predictors):
    data = _finite(frame[[target, *predictors]]).dropna()
    if len(data) <= len(predictors) + 1 or data[target].nunique() < 2:
        return None
    x = np.column_stack([np.ones(len(data)), data[predictors].to_numpy()])
    y = data[target].to_numpy()
    coefficients, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if rank != x.shape[1]:
        return None
    residual = y - x @ coefficients
    r2 = 1 - residual @ residual / np.square(y - y.mean()).sum()
    return coefficients, float(np.clip(r2, 0, 1)), data


def heat_drivers(cells):
    result = _ols(cells, "lst_c", ["dw_frac_built", "dw_frac_trees"])
    if result is None:
        return None
    coef, r2, data = result
    return {"a": coef[0], "built": coef[1], "trees": coef[2], "r2": r2, "n": len(data)}


def fit_line(points):
    result = _ols(points, "y", ["x"])
    if result is None:
        return None
    coef, r2, data = result
    return {"a": coef[0], "b": coef[1], "r2": r2, "n": len(data), "points": data}


def strength_words(r2):
    if r2 < 0.05:
        return "almost no relationship"
    if r2 < 0.2:
        return "a weak relationship"
    if r2 < 0.5:
        return "a moderate relationship"
    return "a strong relationship"


def zone_points(cells):
    data = _finite(cells[["lst_c", "no2_mol_m2"]]).dropna()
    return pd.DataFrame({"x": data.lst_c, "y": data.no2_mol_m2 * 1e6})


def month_points(monthly, remove_season=False):
    dates = pd.to_datetime(monthly.index, errors="coerce")
    data = _finite(monthly[["roi_day_c", "roi_no2"]]).rename(
        columns={"roi_day_c": "x", "roi_no2": "y"}
    )
    data["y"] *= 1e6
    data = data.rename_axis(None)
    data["month"] = dates.month
    data = data.dropna()
    if remove_season:
        data = data.loc[data.groupby("month").x.transform("count") >= 2].copy()
        data[["x", "y"]] -= data.groupby("month")[["x", "y"]].transform("mean")
    return data[["x", "y"]]
