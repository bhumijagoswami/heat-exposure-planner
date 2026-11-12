"""Monthly Earth Engine observations and gap-aware seasonal trend statistics."""

import logging
from dataclasses import dataclass

import ee
import numpy as np
import pandas as pd
import pymannkendall as mk
from scipy.stats import theilslopes
from statsmodels.tsa.seasonal import STL

from . import config
from .extract import _polygon
from .gee_layers import _nitrogen_dioxide, _with_schema
from .grid import projected_roi
from .validate import AnalysisRequest

METRICS = {
    "day_c": ("Daytime LST", "°C"),
    "night_c": ("Nighttime LST", "°C"),
    "no2": ("Tropospheric NO₂", "mol/m²"),
}
ZONES = {"roi": "Whole area", "core": "Urban core", "green": "Green"}


class TrendExtractionError(RuntimeError):
    """Safe message for a failed monthly extraction."""


def _modis_temperature(image, period):
    dn = image.select(f"LST_{period}_1km")
    good = image.select(f"QC_{period}").bitwiseAnd(3).eq(0)
    return dn.multiply(0.02).subtract(273.15).updateMask(good).updateMask(dn.gt(0))


def _monthly_features(request):
    roi, epsg = projected_roi(request)
    crs = f"EPSG:{epsg}"
    bounds = _polygon(roi, crs)
    start, end = f"{request.start_year}-01-01", f"{request.end_year + 1}-01-01"

    def collection(asset):
        return ee.ImageCollection(asset).filterBounds(bounds).filterDate(start, end)

    modis = collection(config.MODIS_LST)
    # All tiles use the MODIS sinusoidal grid, including where the ROI has no data.
    projection = (
        ee.ImageCollection(config.MODIS_LST).first().select("LST_Day_1km").projection()
    )
    no2 = collection(config.S5P_NO2)
    labels = _with_schema(
        collection(config.DYNAMIC_WORLD).select("label").mode(), ["label"]
    )
    core = labels.eq(6)
    green = labels.eq(1).Or(labels.eq(2)).Or(labels.eq(5))

    def temperatures(image):
        return ee.Image.cat(
            _modis_temperature(image, "Day").rename("day_c"),
            _modis_temperature(image, "Night").rename("night_c"),
        )

    def month(offset):
        date = ee.Date(start).advance(offset, "month")
        stop = date.advance(1, "month")
        lst = _with_schema(
            modis.filterDate(date, stop).map(temperatures).mean(), ["day_c", "night_c"]
        ).reproject(projection)
        column = (
            _with_schema(
                no2.filterDate(date, stop).map(_nitrogen_dioxide).mean(), ["no2_mol_m2"]
            )
            .rename("no2")
            .reproject(crs="EPSG:4326", crsTransform=[0.01, 0, -180, 0, -0.01, 90])
        )
        observed = lst.addBands(column)
        cover = (
            observed.mask()
            .unmask(0, sameFootprint=False)
            .multiply(100)
            .rename([f"{name}_coverage" for name in METRICS])
        )
        measurements = observed.addBands(cover)
        bands = [*METRICS, *[f"{name}_coverage" for name in METRICS]]
        zones = ee.Image.cat(
            *(
                img.rename([f"{zone}_{band}" for band in bands])
                for zone, img in (
                    ("roi", measurements),
                    ("core", measurements.updateMask(core)),
                    ("green", measurements.updateMask(green)),
                )
            )
        )
        values = zones.reduceRegion(
            ee.Reducer.mean(), bounds, scale=100, crs=crs, maxPixels=200000
        )
        return ee.Feature(None, values).set("month", date.format("YYYY-MM"))

    return month


def fetch_monthly(request: AnalysisRequest) -> pd.DataFrame:
    """One bounded request per year; preserve missing values and every calendar month."""
    month = _monthly_features(request)
    records = []
    for year in range(request.start_year, request.end_year + 1):
        offset = 12 * (year - request.start_year)
        try:
            response = ee.FeatureCollection(
                ee.List.sequence(offset, offset + 11).map(month)
            ).getInfo()
            rows = [f["properties"] for f in response["features"]]
            if sorted(row["month"] for row in rows) != [
                f"{year}-{m:02d}" for m in range(1, 13)
            ]:
                raise TrendExtractionError(
                    "Earth Engine returned an incomplete monthly series. Retry."
                )
            records.extend(rows)
        except TrendExtractionError:
            raise
        except TimeoutError:
            logging.getLogger(__name__).warning("Earth Engine trends batch timed out")
            raise TrendExtractionError(
                "Earth Engine timed out while retrieving monthly observations. Retry this area or reduce its radius."
            ) from None
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Earth Engine trends batch failed (%s)", type(exc).__name__
            )
            raise TrendExtractionError(
                "Could not retrieve monthly Earth Engine data. Please retry."
            ) from None
    table = pd.DataFrame(records).set_index("month").sort_index()
    table.index = pd.to_datetime(table.index, format="%Y-%m")
    columns = [
        f"{zone}_{metric}{suffix}"
        for zone in ZONES
        for metric in METRICS
        for suffix in ("", "_coverage")
    ]
    return table.reindex(columns=columns).astype(float)


@dataclass
class Trend:
    adjusted: pd.Series
    slope_per_year: float | None
    p_value: float | None
    note: str
    low_weight_2020: int | None = None


def analyze_trend(observations: pd.Series) -> Trend:
    """Use robust annual STL; run inference on observed deseasonalized months only."""
    observed = (
        observations.sort_index()
        .asfreq("MS")
        .astype(float)
        .replace([np.inf, -np.inf], np.nan)
    )
    adjusted = pd.Series(np.nan, index=observed.index, dtype=float)
    valid = observed.dropna()
    if len(valid) < 24:
        return Trend(adjusted, None, None, "At least 24 observed months are required.")
    span = observed.loc[valid.index[0] : valid.index[-1]]
    missing = span.isna()
    longest_gap = missing.groupby((~missing).cumsum()).sum().max()
    if longest_gap > 2 or missing.mean() > 0.2:
        return Trend(
            adjusted,
            None,
            None,
            "Seasonal fit needs at least 80% coverage and gaps of at most two months.",
        )
    filled = span.interpolate()
    fit = STL(filled, period=12, robust=True).fit()
    adjusted.loc[span.index] = span - fit.seasonal
    in_2020 = span.notna() & (span.index.year == 2020)
    low_weight = int((fit.weights[in_2020] < 0.5).sum()) if in_2020.any() else None
    values = adjusted.dropna()
    if np.ptp(values) <= 1e-12:
        return Trend(adjusted, 0.0, 1.0, "", low_weight)
    years = (
        values.index.to_period("M").asi8 - values.index[0].to_period("M").ordinal
    ) / 12
    return Trend(
        adjusted,
        float(theilslopes(values, years).slope),
        float(mk.original_test(values).p),
        "",
        low_weight,
    )


def rolling_comparison(monthly: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Trailing three-calendar-month means, requiring all three observations."""
    columns = [f"{zone}_{metric}" for zone in ("core", "green")]
    return (
        monthly[columns]
        .asfreq("MS")
        .rolling(3, min_periods=3)
        .mean()
        .rename(columns=dict(zip(columns, ("Urban core", "Green"), strict=True)))
    )
