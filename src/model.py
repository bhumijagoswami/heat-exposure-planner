"""Local planting scenario model for land-surface temperature."""

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from .gee_layers import DW_CLASSES, INDICES

FEATURES = [
    *[f"dw_frac_{name}" for name in DW_CLASSES],
    *INDICES,
    "elevation_m",
    "slope_deg",
]
MIN_MODEL_CELLS = 150
BLOCK_SIZE_M = 2000
_SEED = 42


class InsufficientDriverData(ValueError):
    """The ROI cannot support a meaningful spatially validated model."""


@dataclass
class DriverModel:
    forest: RandomForestRegressor
    features: pd.DataFrame
    validation: pd.DataFrame
def fit_drivers(cells: gpd.GeoDataFrame) -> DriverModel:
    """Fit LST on land cover, spectral indices and terrain."""
    if (
        cells.crs is None
        or not cells.crs.is_projected
        or any(axis.unit_conversion_factor != 1 for axis in cells.crs.axis_info[:2])
    ):
        raise ValueError("Driver analysis requires grid geometry projected in metres.")
    data = cells.set_index("cell_id").sort_index()
    if not data.index.is_unique or data.index.hasnans:
        raise ValueError("Driver analysis requires unique, nonempty cell IDs.")
    numeric = data[[*FEATURES, "lst_c"]].replace(
        [float("inf"), -float("inf")], float("nan")
    )
    valid = (
        numeric.notna().all(axis=1) & data.geometry.notna() & ~data.geometry.is_empty
    )
    numeric = numeric.loc[valid]
    if len(numeric) < MIN_MODEL_CELLS:
        raise InsufficientDriverData(
            f"Driver analysis needs {MIN_MODEL_CELLS} complete cells. This area has {len(numeric)}."
        )
    target = numeric["lst_c"]
    if target.nunique() < 2:
        raise InsufficientDriverData(
            "Observed LST is constant across the complete cells."
        )
    features = numeric[FEATURES]
    centers = data.geometry.loc[valid].centroid
    block_xy = pd.MultiIndex.from_arrays(
        [centers.x // BLOCK_SIZE_M, centers.y // BLOCK_SIZE_M]
    )
    blocks, unique = pd.factorize(block_xy)
    if len(unique) < 3:
        raise InsufficientDriverData(
            "Driver validation needs at least three occupied 2 km blocks."
        )

    forest = RandomForestRegressor(
        n_estimators=100, min_samples_leaf=3, max_depth=12, random_state=_SEED, n_jobs=1
    )
    forest.fit(features, target)
    training = pd.DataFrame({"observed_c": target, "block": blocks})
    return DriverModel(forest, features, training)
