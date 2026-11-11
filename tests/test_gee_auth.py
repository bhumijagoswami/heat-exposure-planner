import traceback
from unittest.mock import Mock

import pytest

from src import gee_auth


@pytest.fixture
def sdk(monkeypatch, tmp_path):
    for key in ("EE_PROJECT", "EE_SERVICE_ACCOUNT_JSON"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(gee_auth, "_ENV_FILE", tmp_path / ".env")
    client = Mock(spec=["Initialize", "ServiceAccountCredentials"])
    monkeypatch.setattr(gee_auth, "ee", client)
    return client


def test_sdk_uses_existing_login(sdk):
    gee_auth._ENV_FILE.write_text("EE_PROJECT=local-example\n")
    gee_auth.initialize_earth_engine()
    sdk.Initialize.assert_called_once_with(project="local-example")
    sdk.ServiceAccountCredentials.assert_not_called()


def test_process_environment_overrides_dotenv(sdk, monkeypatch):
    gee_auth._ENV_FILE.write_text("EE_PROJECT=local-example\n")
    monkeypatch.setenv("EE_PROJECT", "process-example")
    gee_auth.initialize_earth_engine()
    sdk.Initialize.assert_called_once_with(project="process-example")


@pytest.mark.parametrize("source", ["env", "streamlit"])
def test_service_account(sdk, monkeypatch, source):
    settings = {
        "EE_PROJECT": "deployment-example",
        "EE_SERVICE_ACCOUNT_JSON": "mock-json",
    }
    if source == "env":
        for name, value in settings.items():
            monkeypatch.setenv(name, value)
        gee_auth.initialize_earth_engine()
    else:
        monkeypatch.setenv("EE_PROJECT", "process-example")
        gee_auth.initialize_earth_engine(secrets=settings)
    sdk.ServiceAccountCredentials.assert_called_once_with(key_data="mock-json")
    sdk.Initialize.assert_called_once_with(
        credentials=sdk.ServiceAccountCredentials.return_value,
        project="deployment-example",
    )


def test_missing_project(sdk):
    with pytest.raises(gee_auth.EarthEngineAuthError, match="Set EE_PROJECT"):
        gee_auth.initialize_earth_engine()
    sdk.Initialize.assert_not_called()


@pytest.mark.parametrize("value", ["", "  ", None])
def test_invalid_deployment_setting_cannot_select_local_login(sdk, value):
    with pytest.raises(gee_auth.EarthEngineAuthError, match="service-account"):
        gee_auth.initialize_earth_engine(
            {"EE_PROJECT": "example", "EE_SERVICE_ACCOUNT_JSON": value}
        )
    sdk.Initialize.assert_not_called()


@pytest.mark.parametrize("local", [True, False])
def test_sdk_failures_have_safe_actionable_message(sdk, local, caplog):
    settings = {"EE_PROJECT": "example"}
    failing_call = sdk.Initialize
    if not local:
        settings["EE_SERVICE_ACCOUNT_JSON"] = "mock-json"
        failing_call = sdk.ServiceAccountCredentials
    failing_call.side_effect = ValueError("sensitive-sdk-diagnostic")
    with pytest.raises(gee_auth.EarthEngineAuthError) as caught:
        gee_auth.initialize_earth_engine(settings)
    assert ("earthengine authenticate" if local else "service-account") in str(
        caught.value
    )
    assert "sensitive-sdk-diagnostic" not in "".join(
        traceback.format_exception(caught.value)
    )
    assert "sensitive-sdk-diagnostic" not in caplog.text
    if not local:
        sdk.Initialize.assert_not_called()
