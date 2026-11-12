from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import ee
import httplib2
import pandas as pd
import pytest
from googleapiclient.http import HttpRequest
from streamlit.testing.v1 import AppTest

from src import extract, gee_auth
from src.config import EE_MAX_RETRIES, EE_TIMEOUT_SECONDS
from src.validate import validate_inputs


@pytest.fixture
def transport(monkeypatch, tmp_path):
    # Exercise the installed Google SDK retry path while keeping all traffic offline.
    # Replace the EE state as well, so retry settings cannot affect another test.
    from ee import _state

    monkeypatch.setattr(_state, "_state", None)
    monkeypatch.setattr(gee_auth, "_ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("EE_SERVICE_ACCOUNT_JSON", raising=False)
    with patch.object(ee, "Initialize") as initialize:
        gee_auth.initialize_earth_engine({"EE_PROJECT": "qa-project"})
    return initialize.call_args.kwargs["http_transport"]


def test_transport_timeout_and_worker_isolation(transport):
    assert transport.timeout == EE_TIMEOUT_SECONDS == 90
    assert ee.data._get_state().max_retries == EE_MAX_RETRIES == 2
    with ThreadPoolExecutor(max_workers=1) as pool:
        timeout, connections = pool.submit(
            lambda: (transport.timeout, transport.connections)
        ).result()
    assert timeout == EE_TIMEOUT_SECONDS
    assert connections is not transport.connections


@pytest.mark.parametrize(
    "errors,expected,attempts",
    [
        ([429, 503, 200], None, 3),
        (["timeout", "timeout", "timeout"], TimeoutError, 3),
        ([400], ee.EEException, 1),
        ([403], ee.EEException, 1),
    ],
)
def test_real_sdk_retry_budget_and_safe_diagnostics(
    transport, errors, expected, attempts, caplog
):
    marker = "PRIVATE_DIAGNOSTIC_MARKER"
    responses = [
        TimeoutError(marker)
        if status == "timeout"
        else (httplib2.Response({"status": str(status)}), marker.encode())
        for status in errors
    ]
    with patch.object(transport, "request", side_effect=responses) as request:
        rpc = HttpRequest(
            transport,
            lambda resp, data: "done",
            f"https://example.invalid/?test={marker}",
        )
        rpc._sleep = Mock()
        rpc._rand = lambda: 0.5
        if expected:
            with pytest.raises(expected):
                ee.data._execute_cloud_call(rpc)
        else:
            assert ee.data._execute_cloud_call(rpc) == "done"
        assert request.call_count == attempts
        assert rpc._sleep.call_args_list == [call(1.0), call(2.0)][: attempts - 1]
    assert marker not in caplog.text


def test_cross_tab_cooldown_and_redaction(monkeypatch, caplog):
    from src.ui import drivers, limits

    marker = "PRIVATE_DIAGNOSTIC_MARKER"
    clock = Mock(return_value=100.0)
    monkeypatch.setattr(limits, "monotonic", clock)
    area_call = Mock(side_effect=RuntimeError(marker))
    monkeypatch.setattr(drivers, "_load_cells", area_call)
    page = AppTest.from_file("../app.py", default_timeout=30).run()
    page.checkbox[0].check().run()

    def click(label):
        next(button for button in page.button if button.label == label).click().run()
        assert not page.exception
        assert marker not in str([e.value for e in [*page.error, *page.warning]])

    click("Analyze area")
    area_call.assert_called_once()
    clock.return_value = 109.9
    click("Analyze area")
    area_call.assert_called_once()
    assert any("10 seconds" in w.value for w in page.warning)
    clock.return_value = 110.0
    click("Analyze area")
    assert area_call.call_count == 2
    assert "RuntimeError" in caplog.text
    assert marker not in caplog.text


def test_cache_isolates_requests_and_does_not_retain_failures(monkeypatch):
    from src.ui import drivers

    request = validate_inputs(lat=10, lon=20, radius_km=1, cell_size_m=500)
    result = SimpleNamespace(cells=pd.DataFrame({"coverage_pct": [80.0]}))
    load = Mock(side_effect=[TimeoutError(), result, result, result])
    monkeypatch.setattr(drivers, "extract_cells", load)
    monkeypatch.setattr(drivers, "initialize_app_earth_engine", Mock())
    drivers._load_cells.clear()
    try:
        with pytest.raises(TimeoutError):
            drivers._load_cells(request, "annual")
        first = drivers._load_cells(request, "annual")
        first.loc[0, "coverage_pct"] = 0
        assert drivers._load_cells(request, "annual").coverage_pct.item() == 80
        drivers._load_cells(request, "summer")
        drivers._load_cells(replace(request, lat=11), "annual")
        assert load.call_count == 4
    finally:
        drivers._load_cells.clear()


@pytest.mark.parametrize(
    "changes", [{"radius_km": 10**1000}, {"lat": "<img onerror>"}, {"end_year": 9999}]
)
def test_hostile_direct_request_stops_before_earth_engine(monkeypatch, changes):
    request = replace(
        validate_inputs(lat=0, lon=0, radius_km=1, cell_size_m=500), **changes
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid inputs reached the Earth Engine SDK")

    monkeypatch.setattr(extract, "_polygon", forbidden)
    with pytest.raises(ValueError):
        extract.extract_cells(request)


def test_user_facing_timeout_is_actionable_and_redacted(monkeypatch, caplog):
    import traceback

    request = validate_inputs(lat=0, lon=0, radius_km=1, cell_size_m=500)
    fault = TimeoutError("PRIVATE_TIMEOUT_MARKER")
    monkeypatch.setattr(extract, "_polygon", Mock())
    monkeypatch.setattr(extract, "build_layers", Mock())
    monkeypatch.setattr(extract, "_reduce_batch", Mock(side_effect=fault))
    run, error = extract.extract_cells, extract.ExtractionError
    with pytest.raises(error, match="timed out") as caught:
        run(request)
    assert "PRIVATE_TIMEOUT_MARKER" not in "".join(
        traceback.format_exception(caught.value)
    )
    assert "PRIVATE_TIMEOUT_MARKER" not in caplog.text
