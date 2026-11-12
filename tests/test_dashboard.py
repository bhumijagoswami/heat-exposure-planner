import pytest

from src.demo import PRESETS, load_demo


@pytest.mark.parametrize("name", PRESETS)
def test_bundled_snapshots(name):
    _, cells = load_demo(name)
    assert cells.cell_id.is_unique and len(cells) >= 150
    assert cells.crs.is_projected and cells.geometry.is_valid.all()
    assert cells.lst_c.notna().any() and cells.population.sum() > 0
