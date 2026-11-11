"""Construct clipped square cells in a local metric CRS, including at the poles."""

from dataclasses import asdict, dataclass
from math import ceil, floor

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point, Polygon, box

from .config import MAX_CELLS
from .validate import AnalysisRequest, validate_inputs


@dataclass
class Grid:
    roi: Polygon
    cells: gpd.GeoDataFrame


def build_grid(request: AnalysisRequest) -> Grid:
    request = validate_inputs(**asdict(request))
    if request.lat >= 84:
        epsg = 32661
    elif request.lat < -80:
        epsg = 32761
    else:
        zone = min(60, floor((request.lon + 180) / 6) + 1)
        epsg = (32600 if request.lat >= 0 else 32700) + zone
    transform = Transformer.from_crs(4326, epsg, always_xy=True)
    x, y = transform.transform(request.lon, request.lat)
    # 360 segments keep the circle's chord error below 0.6 m at the maximum radius.
    roi = Point(x, y).buffer(request.radius_km * 1000, quad_segs=90)
    west, south, east, north = roi.bounds
    size = request.cell_size_m
    rows = []
    for j in range(floor(south / size), ceil(north / size)):
        for i in range(floor(west / size), ceil(east / size)):
            square = box(i * size, j * size, (i + 1) * size, (j + 1) * size)
            cell = square.intersection(roi)
            if cell.area > 0:
                rows.append((f"{epsg}-{size}-{i}-{j}", cell.area, cell))
    if len(rows) > MAX_CELLS:
        raise ValueError(f"Grid exceeds {MAX_CELLS} cells.")
    cells = gpd.GeoDataFrame(
        rows, columns=["cell_id", "area_m2", "geometry"], geometry="geometry", crs=epsg
    )
    return Grid(roi, cells)
