import json
from io import BytesIO

import pandas as pd
import pytest

from src.extract import extract_cells
from src.gee_auth import initialize_earth_engine
from src.index import score_exposure
from src.model import fit_drivers
from src.planner import estimate_scenario, rank_sites
from src.report import build_report
from src.validate import validate_inputs


@pytest.mark.live
def test_delhi_brief_matches_exports():
    initialize_earth_engine()
    request = validate_inputs(
        lat=28.55,
        lon=77.10,
        radius_km=5,
        cell_size_m=500,
        start_year=2023,
        end_year=2023,
    )
    cells = score_exposure(extract_cells(request, season="summer").cells).cells
    model = fit_drivers(cells)
    sites = rank_sites(cells)
    scenario = estimate_scenario(model, sites, 25)
    report = build_report(cells, request, "summer", model=model, scenario=scenario)
    table = pd.read_csv(BytesIO(report.csv()))
    polygons = json.loads(report.geojson())["features"]
    assert len(polygons) == len(table) == len(cells)
    assert set(table.cell_id) == {
        feature["properties"]["cell_id"] for feature in polygons
    }
    assert table.loc[table.planner_rank.eq(1), "delta_c"].item() == pytest.approx(
        scenario.delta_c.iloc[0]
    )
    assert table.loc[table.planner_rank.eq(1), "cell_id"].item() in report.html()
    assert f"{sites.cumulative_exposure_pct.iloc[-1]:.1f}%" in report.markdown()
