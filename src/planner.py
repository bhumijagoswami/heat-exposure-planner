"""Planting-site screening, exposure ranking and indicative LST scenarios."""

from numbers import Integral, Real

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from sklearn.base import clone

from .demo import PRESETS
from .extract import FRACTIONS
from .index import SCHEMES
from .model import DriverModel

MIN_AREA_M2 = 10_000
MIN_OPEN_FRACTION = 0.25
DENSE_BUILT_FRACTION = 0.5
MAX_SITES = 100
BOOTSTRAP_REPLICATES = 100
_OPEN = ["dw_frac_bare", "dw_frac_shrub_and_scrub", "dw_frac_grass"]


def _land_use_flags(data):
    flags = pd.Series("Verify airfields, roads and restricted land", index=data.index)
    mixed = (
        data[["dw_frac_crops", "dw_frac_flooded_vegetation", "dw_frac_snow_and_ice"]]
        .gt(0)
        .any(axis=1)
    )
    flags.loc[mixed] += " · crops, wetland or snow/ice present"
    if isinstance(data, gpd.GeoDataFrame) and not data.empty:
        # Flag the whole known airport study district; this is not a surveyed airfield boundary.
        _, lat, lon = PRESETS["Delhi · airport district"]
        district = (
            gpd.GeoSeries([Point(lon, lat)], crs=4326)
            .to_crs(32643)
            .buffer(5000)
            .to_crs(4326)
            .iloc[0]
        )
        nearby = data.geometry.to_crs(4326).intersects(district)
        flags.loc[nearby] = (
            "Airport district · check runway and safety boundaries. "
            + flags.loc[nearby]
        )
    return flags


def rank_sites(
    cells: pd.DataFrame, scheme: str = "equal", top_n: int = 10
) -> pd.DataFrame:
    """Rank eligible cells. Coverage uses the sum of all valid ROI exposure scores."""
    if scheme not in SCHEMES:
        raise ValueError("Choose a supported exposure weighting scheme.")
    if (
        isinstance(top_n, bool)
        or not isinstance(top_n, Integral)
        or not 1 <= top_n <= MAX_SITES
    ):
        raise ValueError(f"Choose between 1 and {MAX_SITES} sites.")
    data = cells.set_index("cell_id")
    exposure = data[f"exposure_{scheme}"]
    scored = np.isfinite(exposure) & exposure.ge(0)
    fractions = data[FRACTIONS]
    valid = (
        fractions.notna().all(axis=1)
        & fractions.ge(0).all(axis=1)
        & fractions.le(1).all(axis=1)
        & np.isclose(fractions.sum(axis=1), 1, atol=1e-5, rtol=0)
    )
    open_fraction = data[_OPEN].sum(axis=1)
    eligible = (
        scored
        & valid
        & np.isfinite(data.area_m2)
        & data.area_m2.ge(MIN_AREA_M2)
        & open_fraction.ge(MIN_OPEN_FRACTION)
        & data.dw_frac_water.eq(0)
        & data.dw_frac_built.lt(DENSE_BUILT_FRACTION)
    )
    sites = data.loc[eligible, ["area_m2", "dw_frac_bare", "dw_frac_trees"]].copy()
    sites["open_fraction"] = open_fraction.loc[eligible]
    sites["exposure"] = exposure.loc[eligible]
    sites = sites.sort_values(["exposure", "cell_id"], ascending=[False, True]).head(
        top_n
    )
    total = exposure[scored].sum()
    sites["cumulative_exposure_pct"] = (
        100 * sites.exposure.cumsum() / total if total > 0 else np.nan
    )
    sites["land_use_review"] = _land_use_flags(data.loc[sites.index])
    return sites


def shift_bare_to_trees(features: pd.DataFrame, percent: float) -> pd.DataFrame:
    """Transfer a percentage of existing bare cover, conserving total cover."""
    if (
        isinstance(percent, bool)
        or not isinstance(percent, Real)
        or not 0 <= percent <= 100
    ):
        raise ValueError("Bare-to-tree conversion must be between 0 and 100 percent.")
    changed = features.copy()
    transfer = np.minimum(
        features.dw_frac_bare * (percent / 100),
        (1 - features.dw_frac_trees).clip(lower=0),
    )
    changed["dw_frac_bare"] = (features.dw_frac_bare - transfer).clip(0, 1)
    changed["dw_frac_trees"] = (features.dw_frac_trees + transfer).clip(0, 1)
    return changed


def estimate_scenario(
    model: DriverModel, sites: pd.DataFrame, percent: float
) -> pd.DataFrame:
    """Paired scenario minus baseline predictions and a 95% spatial block bootstrap interval."""
    ids = sites.index.intersection(model.features.index, sort=False)
    before = model.features.loc[ids]
    after = shift_bare_to_trees(before, percent)
    results = pd.DataFrame(
        np.nan,
        index=sites.index,
        columns=["converted_m2", "delta_c", "lower_c", "upper_c"],
    )
    changed_sites = shift_bare_to_trees(sites, percent)
    results["converted_m2"] = sites.area_m2 * (
        sites.dw_frac_bare - changed_sites.dw_frac_bare
    )
    if before.empty:
        return results
    results.loc[ids, "delta_c"] = model.forest.predict(after) - model.forest.predict(
        before
    )
    if after.equals(before):
        results.loc[ids, ["lower_c", "upper_c"]] = 0.0
        return results

    # Refit on spatial blocks sampled with replacement. Each refit predicts both
    # land-cover compositions so the interval measures uncertainty in their difference.
    labels = model.validation.loc[model.features.index, "block"]
    blocks = list(labels.groupby(labels).indices.values())
    target = model.validation.loc[model.features.index, "observed_c"]
    rng = np.random.default_rng(42)
    draws = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled = rng.integers(len(blocks), size=len(blocks))
        rows = np.concatenate([blocks[i] for i in sampled])
        forest = clone(model.forest).fit(model.features.iloc[rows], target.iloc[rows])
        draws.append(forest.predict(after) - forest.predict(before))
    results.loc[ids, ["lower_c", "upper_c"]] = np.quantile(
        draws, [0.025, 0.975], axis=0
    ).T
    return results
