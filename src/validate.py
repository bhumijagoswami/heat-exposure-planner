"""Validate planner requests before constructing geometry or contacting Earth Engine."""

import math
from dataclasses import dataclass
from numbers import Integral, Real

from .config import (
    CELL_SIZES_M,
    FIRST_YEAR,
    LAST_YEAR,
    MAX_CELLS,
    MAX_RADIUS_KM,
    MIN_RADIUS_KM,
)


@dataclass(frozen=True)
class AnalysisRequest:
    lat: float
    lon: float
    radius_km: float
    cell_size_m: int
    start_year: int
    end_year: int


def _bounded_number(value: object, name: str, low: int, high: int) -> float:
    # The range comparison rejects infinities, NaN and enormous ints before conversion.
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not low <= value <= high
    ):
        raise ValueError(f"{name} must be a finite number between {low} and {high}.")
    return float(value)


def _year(value: object, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, Integral)
        or not FIRST_YEAR <= value <= LAST_YEAR
    ):
        raise ValueError(
            f"{name} must be a whole year between {FIRST_YEAR} and {LAST_YEAR}."
        )
    return int(value)


def validate_inputs(
    *,
    lat: float,
    lon: float,
    radius_km: float,
    cell_size_m: int,
    start_year: int = FIRST_YEAR,
    end_year: int = LAST_YEAR,
) -> AnalysisRequest:
    """Return normalized inputs. Coordinates are named to avoid ordering ambiguity."""
    latitude = _bounded_number(lat, "Latitude", -90, 90)
    longitude = _bounded_number(lon, "Longitude", -180, 180)
    radius = _bounded_number(radius_km, "Radius (km)", MIN_RADIUS_KM, MAX_RADIUS_KM)
    if not isinstance(cell_size_m, Integral) or cell_size_m not in CELL_SIZES_M:
        raise ValueError(f"Cell size (m) must be one of {CELL_SIZES_M}.")
    size = int(cell_size_m)
    # Every intersecting square fits in the circle expanded by one cell diagonal.
    # Dividing that circle's area by a full cell's area bounds the grid before clipping.
    upper_bound = math.floor(math.pi * (radius * 1000 / size + math.sqrt(2)) ** 2)
    if upper_bound > MAX_CELLS:
        raise ValueError(
            f"Grid may exceed {MAX_CELLS} cells. Reduce radius or increase cell size."
        )
    first = _year(start_year, "Start year")
    last = _year(end_year, "End year")
    if first > last:
        raise ValueError("Start year must be earlier than or equal to end year.")
    return AnalysisRequest(latitude, longitude, radius, size, first, last)
