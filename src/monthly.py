"""Area-wide monthly daytime surface temperature and nitrogen dioxide."""

import logging

import ee
import pandas as pd

from . import config
from .extract import _polygon
from .gee_layers import _nitrogen_dioxide, _with_schema
from .grid import projected_roi
from .validate import AnalysisRequest


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

    def month(offset):
        date = ee.Date(start).advance(offset, "month")
        stop = date.advance(1, "month")
        lst = _with_schema(
            modis.filterDate(date, stop)
            .map(lambda image: _modis_temperature(image, "Day").rename("roi_day_c"))
            .mean(),
            ["roi_day_c"],
        ).reproject(projection)
        column = (
            _with_schema(
                no2.filterDate(date, stop).map(_nitrogen_dioxide).mean(), ["no2_mol_m2"]
            )
            .rename("roi_no2")
            .reproject(crs="EPSG:4326", crsTransform=[0.01, 0, -180, 0, -0.01, 90])
        )
        observed = lst.addBands(column)
        values = observed.reduceRegion(
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
    return table.reindex(columns=["roi_day_c", "roi_no2"]).astype(float)
