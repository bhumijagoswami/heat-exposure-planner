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
