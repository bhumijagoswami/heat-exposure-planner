"""Cached live observations and Earth Engine initialization."""

from src.monthly import fetch_monthly

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


from src.config import (
    CACHE_MAX_ENTRIES,
    CACHE_TTL_SECONDS,
)
from src.extract import extract_cells
from src.gee_auth import initialize_earth_engine, EarthEngineAuthError


@st.cache_resource(ttl=CACHE_TTL_SECONDS, max_entries=1, show_spinner=False)
def initialize_app_earth_engine():
    # Community Cloud supplies secrets through Streamlit's configured secret store.
    try:
        configured = bool(st.secrets)
    except StreamlitSecretNotFoundError as exc:
        if exc.error_id != "no-secrets-found":
            raise EarthEngineAuthError(
                "Could not load Streamlit deployment secrets."
            ) from None
        configured = False
    initialize_earth_engine(st.secrets if configured else None)


@st.cache_data(ttl=CACHE_TTL_SECONDS, max_entries=CACHE_MAX_ENTRIES, show_spinner=False)
def _load_cells(request, season):
    initialize_app_earth_engine()
    return extract_cells(request, season=season).cells


@st.cache_data(ttl=CACHE_TTL_SECONDS, max_entries=CACHE_MAX_ENTRIES, show_spinner=False)
def _load_monthly(request):
    initialize_app_earth_engine()
    return fetch_monthly(request)
