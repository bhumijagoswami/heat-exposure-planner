"""Initialize Earth Engine using the local SDK login or configured deployment secrets."""

import logging
import os
from collections import ChainMap
from collections.abc import Mapping
from pathlib import Path
from threading import local

import ee
import httplib2
from dotenv import dotenv_values

from .config import EE_MAX_RETRIES, EE_TIMEOUT_SECONDS

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class _ThreadHttp(httplib2.Http, local):
    """Give each Streamlit worker its own timeout-bound connection pool."""


class _SafeNetworkLog(logging.Filter):
    def filter(self, record):
        # The Google client can log the full URI, response body or exception on retry.
        record.msg = "Google API transport diagnostic (request details redacted)"
        record.args = ()
        record.exc_info = record.exc_text = record.stack_info = None
        return True


_NETWORK_FILTER = _SafeNetworkLog()


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
            raise EarthEngineAuthError(
                "Set EE_PROJECT to your registered Earth Engine project ID."
            )
        for name in (
            "googleapiclient.http",
            "googleapiclient.discovery",
            "google_auth_httplib2",
        ):
            logging.getLogger(name).addFilter(_NETWORK_FILTER)
        ee.data.setMaxRetries(EE_MAX_RETRIES)
        transport = _ThreadHttp(timeout=EE_TIMEOUT_SECONDS)
        if "EE_SERVICE_ACCOUNT_JSON" not in settings:
            message = (
                "Earth Engine initialization failed. Check EE_PROJECT and project access, "
                "then run earthengine authenticate if your local login needs renewal."
            )
            ee.Initialize(project=project.strip(), http_transport=transport)
        else:
            message = (
                "Earth Engine service-account initialization failed. "
                "Check EE_SERVICE_ACCOUNT_JSON, EE_PROJECT and project permissions."
            )
            key_data = settings["EE_SERVICE_ACCOUNT_JSON"]
            if not isinstance(key_data, str) or not key_data.strip():
                raise EarthEngineAuthError(message)
            credentials = ee.ServiceAccountCredentials(key_data=key_data)
            ee.Initialize(
                credentials=credentials,
                project=project.strip(),
                http_transport=transport,
            )
    except EarthEngineAuthError:
        raise
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Earth Engine initialization failed (%s)", type(exc).__name__
        )
        # SDK/parser exceptions can contain credential material.
        raise EarthEngineAuthError(message) from None
