"""Initialize Earth Engine using the local SDK login or configured deployment secrets."""

import os
from collections import ChainMap
from collections.abc import Mapping
from pathlib import Path

import ee
from dotenv import dotenv_values

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class EarthEngineAuthError(RuntimeError):
    """Configuration or initialization failure safe to display in the UI."""


def initialize_earth_engine(secrets: Mapping[str, str] | None = None) -> None:
    """Pass st.secrets on Streamlit Cloud. Environment values override local .env."""
    message = "Could not read Earth Engine settings. Check the deployment secrets or local .env."
    try:
        settings = ChainMap(
            secrets if secrets is not None else {},
            os.environ,
            dotenv_values(_ENV_FILE, interpolate=False),
        )
        project = settings.get("EE_PROJECT")
        if not isinstance(project, str) or not project.strip():
            raise EarthEngineAuthError("Set EE_PROJECT to your registered Earth Engine project ID.")
        if "EE_SERVICE_ACCOUNT_JSON" not in settings:
            message = (
                "Earth Engine initialization failed. Check EE_PROJECT and project access, "
                "then run earthengine authenticate if your local login needs renewal."
            )
            ee.Initialize(project=project.strip())
        else:
            message = (
                "Earth Engine service-account initialization failed. "
                "Check EE_SERVICE_ACCOUNT_JSON, EE_PROJECT and project permissions."
            )
            key_data = settings["EE_SERVICE_ACCOUNT_JSON"]
            if not isinstance(key_data, str) or not key_data.strip():
                raise EarthEngineAuthError(message)
            credentials = ee.ServiceAccountCredentials(key_data=key_data)
            ee.Initialize(credentials=credentials, project=project.strip())
    except EarthEngineAuthError:
        raise
    except Exception:
        # SDK/parser exceptions can contain credential material.
        raise EarthEngineAuthError(message) from None
