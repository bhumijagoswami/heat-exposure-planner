from unittest.mock import Mock

import pytest
from streamlit.errors import StreamlitSecretNotFoundError

from src.ui import drivers


@pytest.mark.parametrize("source", ["hosted", "absent", "malformed"])
def test_auth_uses_host_secret_store_or_local_login(monkeypatch, source):
    class Secrets(dict):
        def __len__(self):
            if source == "hosted":
                return super().__len__()
            raise StreamlitSecretNotFoundError(
                "private-diagnostic",
                error_id="no-secrets-found" if source == "absent" else "invalid-toml",
            )

    secrets = Secrets(EE_PROJECT="example-project", EE_SERVICE_ACCOUNT_JSON="mock-data")
    initialize = Mock()
    monkeypatch.setattr(drivers.st, "secrets", secrets)
    monkeypatch.setattr(drivers, "initialize_earth_engine", initialize)
    drivers.initialize_app_earth_engine.clear()
    try:
        if source == "malformed":
            with pytest.raises(
                drivers.EarthEngineAuthError, match="deployment secrets"
            ):
                drivers.initialize_app_earth_engine()
            initialize.assert_not_called()
        else:
            drivers.initialize_app_earth_engine()
            initialize.assert_called_once_with(secrets if source == "hosted" else None)
    finally:
        drivers.initialize_app_earth_engine.clear()


def test_hosted_toml_template_initializes_without_local_files(monkeypatch):
    import json
    import tomllib
    from pathlib import Path
    from src import gee_auth

    template = Path(__file__).resolve().parents[1] / ".streamlit/secrets.toml.example"
    settings = tomllib.loads(template.read_text())
    assert json.loads(settings["EE_SERVICE_ACCOUNT_JSON"])["type"] == "service_account"
    monkeypatch.setattr(drivers.st, "secrets", settings)
    monkeypatch.setattr(
        gee_auth,
        "dotenv_values",
        Mock(side_effect=AssertionError("local settings accessed")),
    )
    credentials = Mock()
    initialize = Mock()
    monkeypatch.setattr(gee_auth.ee, "ServiceAccountCredentials", credentials)
    monkeypatch.setattr(gee_auth.ee, "Initialize", initialize)
    drivers.initialize_app_earth_engine.clear()
    try:
        drivers.initialize_app_earth_engine()
        credentials.assert_called_once_with(
            key_data=settings["EE_SERVICE_ACCOUNT_JSON"]
        )
        assert initialize.call_args.kwargs["credentials"] is credentials.return_value
        assert initialize.call_args.kwargs["project"] == settings["EE_PROJECT"]
    finally:
        drivers.initialize_app_earth_engine.clear()
