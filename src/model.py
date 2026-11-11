"""Spatial validation and Tree SHAP explanations for land-surface temperature."""

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd
import shap
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import GroupKFold

from .gee_layers import DW_CLASSES, INDICES

FEATURES = [
    *[f"dw_frac_{name}" for name in DW_CLASSES],
    *INDICES,
    "elevation_m",
    "slope_deg",
]
MIN_MODEL_CELLS = 150
BLOCK_SIZE_M = 2000
MAX_SHAP_CELLS = 2000
_SEED = 42


class InsufficientDriverData(ValueError):
    """The ROI cannot support a meaningful spatially validated model."""


@dataclass
class DriverModel:
    forest: RandomForestRegressor
    features: pd.DataFrame
    validation: pd.DataFrame
    r2: float
    rmse_c: float
    baseline_c: float
    contributions: pd.DataFrame
    importance: pd.Series
    excluded_cells: int

    def explain_cell(self, cell_id: str) -> pd.Series:
        """Signed °C contributions to the full-data model prediction for any fitted cell."""
        if cell_id in self.contributions.index:
            return self.contributions.loc[cell_id].copy()
        row = self.features.loc[[cell_id]]
        values = shap.TreeExplainer(self.forest)(row).values
        return pd.Series(values[0].reshape(-1), index=FEATURES, name=cell_id)


def fit_drivers(cells: gpd.GeoDataFrame) -> DriverModel:
    """Fit LST on land cover, spectral indices and terrain; report out-of-fold skill."""
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
    validation = pd.DataFrame(
        {"observed_c": target, "block": blocks, "fold": -1, "held_out_c": float("nan")}
    )
    folds = GroupKFold(n_splits=min(5, len(unique)))
    for fold, (train, test) in enumerate(folds.split(features, groups=blocks)):
        forest.fit(features.iloc[train], target.iloc[train])
        ids = features.index[test]
        validation.loc[ids, "held_out_c"] = forest.predict(features.iloc[test])
        validation.loc[ids, "fold"] = fold

    forest.fit(features, target)
    sample = (
        features
        if len(features) <= MAX_SHAP_CELLS
        else features.sample(MAX_SHAP_CELLS, random_state=_SEED).sort_index()
    )
    explanation = shap.TreeExplainer(forest)(sample)
    contributions = pd.DataFrame(
        explanation.values.reshape(len(sample), len(FEATURES)),
        index=sample.index,
        columns=FEATURES,
    )
    return DriverModel(
        forest=forest,
        features=features,
        validation=validation,
        r2=float(r2_score(target, validation.held_out_c)),
        rmse_c=float(root_mean_squared_error(target, validation.held_out_c)),
        baseline_c=float(explanation.base_values.reshape(-1)[0]),
        contributions=contributions,
        importance=contributions.abs().mean().sort_values(ascending=False),
        excluded_cells=len(data) - len(numeric),
    )
