"""Relative exposure within one ROI and analysis period."""

from dataclasses import dataclass

import pandas as pd

# Order is heat, tropospheric NO2, green deficit.
SCHEMES = {
    "equal": (1, 1, 1),
    "heat_forward": (2, 1, 1),
    "air_forward": (1, 2, 1),
    "green_deficit_forward": (1, 1, 2),
}


@dataclass
class ExposureResult:
    cells: pd.DataFrame
    sensitivity: pd.DataFrame


def _percentiles(values):
    """Empirical mid-percentiles: tied values share the midpoint of their ranks."""
    count = values.count()
    if not count:
        return values.astype(float)
    return (values.rank(method="average") - 0.5) / count


def score_exposure(cells: pd.DataFrame) -> ExposureResult:
    """Add scores without dropping cells. Correlations compare population-weighted scores.

    Hazard factors share a reference set of cells with all three observations.
    Population weights use cells with a valid hazard, population and joint coverage.
    Zero residents receive zero weight. Missing scores have unknown priority.
    """
    scored = cells.copy()
    factors = cells[["lst_c", "no2_mol_m2", "ndvi"]].replace(
        [float("inf"), -float("inf")], float("nan")
    )
    area = cells["area_m2"]
    valid_area = area.gt(0) & area.lt(float("inf"))
    valid_lst = valid_area & factors.lst_c.notna()
    area_total = area[valid_lst].sum()
    mean_lst = (
        (factors.lst_c[valid_lst] * area[valid_lst]).sum() / area_total
        if area_total
        else float("nan")
    )
    scored["lst_anomaly_c"] = (factors.lst_c - mean_lst).where(valid_area)
    observed = valid_area & factors.notna().all(axis=1)
    ranks = pd.DataFrame(
        {
            "heat_rank": _percentiles(scored.lst_anomaly_c.where(observed)),
            "no2_rank": _percentiles(factors.no2_mol_m2.where(observed)),
            "green_deficit": 1 - _percentiles(factors.ndvi.where(observed)),
        },
        index=cells.index,
    )
    scored[ranks.columns] = ranks

    population = cells.population
    eligible = (
        observed
        & population.ge(0)
        & population.lt(float("inf"))
        & cells.coverage_pct.gt(0)
    )
    weight = _percentiles(population.where(eligible)).mask(
        eligible & population.eq(0), 0
    )
    scored["population_rank"] = weight
    exposures = pd.DataFrame(index=cells.index)
    priority = eligible.copy()
    for scheme, weights in SCHEMES.items():
        hazard = ranks.mul(list(weights), axis="columns").sum(axis=1, min_count=3) / sum(
            weights
        )
        scored[f"hazard_{scheme}"] = hazard
        exposures[scheme] = hazard * weight
        scored[f"exposure_{scheme}"] = exposures[scheme]
        priority &= _percentiles(exposures[scheme]).ge(0.8)
    scored["robust_priority"] = priority.astype("boolean").where(eligible)
    # Pearson correlation of average ranks is Spearman correlation, including ties.
    sensitivity = exposures.rank().corr(min_periods=2)
    return ExposureResult(scored, sensitivity)
