from unittest.mock import patch

import ee
import pandas as pd
import pytest
from ee.apitestcase import ApiTestCase

from src import extract
from src.validate import validate_inputs


def request(radius=1):
    return validate_inputs(lat=28.6, lon=77.2, radius_km=radius, cell_size_m=250)


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(extract, "_polygon", lambda *args: None)
    monkeypatch.setattr(extract, "build_layers", lambda *args, **kwargs: None)


def test_ordered_batched_extraction_and_coverage(offline, monkeypatch):
    sizes = []

    def reduce(layers, cells, crs):
        sizes.append(len(cells))
        result = []
        for row in cells.itertuples():
            if row.Index % 2:
                result.append(
                    {"cell_id": row.cell_id, "population": 0, "population_support": 0}
                )
                continue
            props = {band: 0.0 for band in extract.FRACTIONS}
            props.update(
                dw_frac_trees=1.0,
                cell_id=row.cell_id,
                coverage_pct=85.0,
                lst_c=32.0,
                population=0.0,
                population_support=0.5,
            )
            result.append(props)
        return list(reversed(result))

    monkeypatch.setattr(extract, "_reduce_batch", reduce)
    result = extract.extract_cells(request(6.65))
    cells = result.cells
    assert len(sizes) == 5
    assert max(sizes) == 500
    assert sum(sizes) == len(cells)
    assert cells.cell_id.is_unique and cells.geometry.notna().all()
    assert cells.iloc[::2].dw_label.eq(1).all()
    assert cells.iloc[1::2].dw_label.isna().all()
    assert cells.iloc[::2].population.eq(0).all()
    assert cells.iloc[1::2].population.isna().all()
    assert cells.iloc[::2].lst_c.eq(32).all()
    assert cells.iloc[1::2].lst_c.isna().all()
    assert result.area_coverage_pct == pytest.approx(
        85 * cells.area_m2.iloc[::2].sum() / cells.area_m2.sum()
    )


def test_ocean_retains_empty_rows_and_zero_coverage(offline, monkeypatch):
    monkeypatch.setattr(
        extract,
        "_reduce_batch",
        lambda layers, cells, crs: [{"cell_id": key} for key in cells.cell_id],
    )
    result = extract.extract_cells(request())
    assert len(result.cells) > 0
    assert result.cells[extract.EXPOSURE_BANDS].isna().all().all()
    assert result.cells.coverage_pct.eq(0).all()
    assert result.area_coverage_pct == 0


@pytest.mark.parametrize("failure", ["duplicate", "missing", "server"])
def test_incomplete_batch_fails_without_partial_table(offline, monkeypatch, failure):
    def reduce(layers, cells, crs):
        if failure == "server":
            raise RuntimeError("sensitive diagnostic")
        ids = list(cells.cell_id)
        if failure == "missing":
            ids.pop()
        else:
            ids[-1] = ids[0]
        return [{"cell_id": key} for key in ids]

    monkeypatch.setattr(extract, "_reduce_batch", reduce)
    with pytest.raises(extract.ExtractionError) as exc:
        extract.extract_cells(request())
    assert "sensitive diagnostic" not in str(exc.value)


class TestBatchGraph(ApiTestCase):
    def setUp(self):
        self.addCleanup(
            setattr,
            ee.data,
            "_install_cloud_api_resource",
            ee.data._install_cloud_api_resource,
        )
        super().setUp()

    def test_one_request_per_batch_with_native_population_sum(self):
        seen = []

        def evaluate(collection):
            graph = collection.serialize()
            assert "Reducer.sum" in graph
            assert "Reducer.mean" in graph
            assert "population_support" in graph
            assert "Image.projection" in graph
            seen.append(graph)
            # Read only local grid IDs, substituting an all-masked EE response.
            return {
                "features": [{"properties": {"cell_id": key}} for key in cells.cell_id]
            }

        cells = extract.build_grid(request()).cells
        with patch.object(ee.data, "computeValue", side_effect=evaluate):
            result = extract.extract_cells(request())
        assert len(seen) == 1
        assert pd.isna(result.cells.population).all()
