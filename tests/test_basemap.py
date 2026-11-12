import pandas as pd

from src.demo import load_demo
from src.index import score_exposure
from src.ui.basemap import marker_records, relative_bands, select_markers


def test_relative_bands_include_missing():
    data = pd.DataFrame(
        {"lst_c": [*range(100), None], "dw_frac_trees": [*range(100), None]}
    )
    heat = relative_bands(data, "lst_c")
    assert heat.value_counts().sort_index().tolist() == [40, 30, 20, 10, 1]


def test_pooled_risk_and_dominant_type():
    from src.ui.basemap import pooled_risk, dominant_types

    _, cells = load_demo("Bengaluru · central district")
    left, right = pooled_risk([cells, cells])
    assert (left == right).all()
    assert len(set(left)) >= 4
    assert dominant_types(cells).notna().any()


def test_marker_spacing_order_and_exclusions():
    _, cells = load_demo("Bengaluru · central district")
    cells = score_exposure(cells)
    keys = select_markers(cells)
    assert len(keys) == 5
    indexed = cells.set_index("cell_id")
    centers = indexed.loc[keys].geometry.centroid
    assert all(
        centers[i].distance(centers[j]) >= 1000 for i in keys for j in keys if i != j
    )
    assert indexed.loc[keys].exposure_equal.is_monotonic_decreasing
    assert keys == select_markers(cells.sample(frac=1, random_state=1))
    assert keys[0] not in select_markers(
        cells.assign(restricted=cells.cell_id.eq(keys[0]))
    )
    assert all(
        "Residents:" in item["details"] for item in marker_records(indexed, keys)
    )
