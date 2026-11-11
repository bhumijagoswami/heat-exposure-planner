import math
from dataclasses import replace

import pytest
from shapely import union_all

from src.grid import build_grid
from src.validate import validate_inputs


@pytest.mark.parametrize(
    "lat,lon", [(28.6, 77.2), (0, -180), (0, 180), (90, 0), (-90, 30)]
)
def test_grid_tiles_roi_without_overlaps(lat, lon):
    request = validate_inputs(lat=lat, lon=lon, radius_km=1, cell_size_m=250)
    grid = build_grid(request)
    cells = grid.cells
    assert 0 < len(cells) <= 2500
    assert cells.cell_id.is_unique
    assert cells.geometry.is_valid.all()
    assert cells.crs.is_projected
    assert (cells.area_m2 > 0).all()
    assert cells.area_m2.max() == pytest.approx(250**2)
    assert cells.area_m2.min() < 250**2
    assert cells.area_m2.sum() == pytest.approx(grid.roi.area)
    assert union_all(cells.geometry).symmetric_difference(grid.roi).area < 0.01
    assert grid.roi.area == pytest.approx(math.pi * 1000**2, rel=0.0001)
    assert cells.cell_id.tolist() == build_grid(request).cells.cell_id.tolist()


def test_grid_rejects_unvalidated_oversized_request():
    request = validate_inputs(lat=0, lon=0, radius_km=1, cell_size_m=250)
    with pytest.raises(ValueError, match="2500"):
        build_grid(replace(request, radius_km=15))


def test_large_valid_grid_within_budget():
    grid = build_grid(validate_inputs(lat=35, lon=140, radius_km=6.65, cell_size_m=250))
    assert 2000 < len(grid.cells) <= 2500
