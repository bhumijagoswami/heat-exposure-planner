"""Batched Earth Engine zonal statistics with explicit coverage and native-grid counts."""

import logging
from dataclasses import dataclass
from typing import Literal

import ee
import geopandas as gpd
import pandas as pd

from .config import EXTRACTION_BATCH_SIZE, EXTRACTION_SCALE_M
from .gee_layers import DW_CLASSES, INDICES, build_layers
from .grid import build_grid
from .validate import AnalysisRequest

FRACTIONS = [f"dw_frac_{name}" for name in DW_CLASSES]
MEAN_BANDS = [
    "lst_c",
    "no2_mol_m2",
    *INDICES,
    "elevation_m",
    "slope_deg",
    *[f"dw_prob_{name}" for name in DW_CLASSES],
    *FRACTIONS,
]
EXPOSURE_BANDS = ["lst_c", "no2_mol_m2", "ndvi", "population"]


class ExtractionError(RuntimeError):
    """A batch failed or returned an incomplete set of cell IDs."""


@dataclass
class ExtractionResult:
    cells: gpd.GeoDataFrame
    area_coverage_pct: float


def _polygon(shape, crs):
    return ee.Geometry.Polygon([list(shape.exterior.coords)], proj=crs, geodesic=False)


def _reduce_batch(layers, cells, crs):
    features = ee.FeatureCollection(
        [
            ee.Feature(_polygon(row.geometry, crs), {"cell_id": row.cell_id})
            for row in cells.itertuples()
        ]
    )
    # Fraction of cell area with joint heat, air, vegetation and population support.
    coverage = (
        layers.select(EXPOSURE_BANDS)
        .mask()
        .unmask(0, sameFootprint=False)
        .reduce(ee.Reducer.min())
        .multiply(100)
        .rename("coverage_pct")
    )
    means = (
        layers.select(MEAN_BANDS)
        .addBands(coverage)
        .reduceRegions(
            collection=features,
            reducer=ee.Reducer.mean(),
            crs=crs,
            scale=EXTRACTION_SCALE_M,
        )
    )
    # Weighted sums on WorldPop's own affine grid preserve fractional edge pixels.
    population = layers.select("population")
    support = population.multiply(0).add(1).rename("population_support")
    totals = population.addBands(support).reduceRegions(
        collection=means,
        reducer=ee.Reducer.sum(),
        crs=population.projection(),
    )
    response = totals.map(lambda feature: feature.setGeometry(None)).getInfo()
    return [feature["properties"] for feature in response["features"]]


def extract_cells(
    request: AnalysisRequest, *, season: Literal["annual", "summer"] = "annual"
) -> ExtractionResult:
    """Return all clipped cells, including masked cells, with geometry in metres."""
    grid = build_grid(request)
    crs = grid.cells.crs.to_string()
    layers = build_layers(
        _polygon(grid.roi, crs), request, season=season, clip_to_roi=False
    )
    records = []
    for start in range(0, len(grid.cells), EXTRACTION_BATCH_SIZE):
        batch = grid.cells.iloc[start : start + EXTRACTION_BATCH_SIZE]
        try:
            result = _reduce_batch(layers, batch, crs)
            ids = [row["cell_id"] for row in result]
            if len(ids) != len(batch) or set(ids) != set(batch.cell_id):
                raise ExtractionError(
                    "Earth Engine returned an incomplete grid batch. Retry extraction."
                )
            records.extend(result)
        except ExtractionError:
            raise
        except TimeoutError:
            logging.getLogger(__name__).warning("Earth Engine extract batch timed out")
            raise ExtractionError(
                "Earth Engine timed out while extracting cells. Try a smaller radius or a shorter period."
            ) from None
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Earth Engine extract batch failed (%s)", type(exc).__name__
            )
            raise ExtractionError(
                "Could not extract Earth Engine data. Check access and retry."
            ) from None

    table = pd.DataFrame.from_records(records).set_index("cell_id")
    numeric = table.reindex(
        columns=[*MEAN_BANDS, "population", "population_support", "coverage_pct"]
    ).astype(float)
    support = numeric.pop("population_support")
    numeric["population"] = numeric.population.where(support > 0)
    numeric["coverage_pct"] = numeric.coverage_pct.fillna(0)
    # The largest class area defines the cell label; ties follow catalog class order.
    fractions = numeric[FRACTIONS]
    valid = fractions.notna().all(axis=1) & fractions.sum(axis=1).gt(0)
    labels = pd.Series(pd.NA, index=numeric.index, dtype="Int64")
    labels.loc[valid] = fractions.loc[valid].to_numpy().argmax(axis=1)
    numeric["dw_label"] = labels
    cells = grid.cells.join(numeric, on="cell_id", validate="one_to_one")
    coverage_pct = (cells.area_m2 * cells.coverage_pct).sum() / cells.area_m2.sum()
    return ExtractionResult(cells, float(coverage_pct))
