"""Streamlit controls and results for the LST driver analysis."""

import logging

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from .limits import begin_compute

from src.config import (
    CACHE_MAX_ENTRIES,
    CACHE_TTL_SECONDS,
    CELL_SIZES_M,
    FIRST_YEAR,
    LAST_YEAR,
    MIN_RADIUS_KM,
    MAX_RADIUS_KM,
)
from src.extract import extract_cells, ExtractionError
from src.gee_auth import initialize_earth_engine, EarthEngineAuthError
from src.index import score_exposure
from src.model import fit_drivers, InsufficientDriverData, predictor_label
from src.validate import validate_inputs


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


def render_area_form():
    st.caption("Earth Engine · live observations")
    with st.form("driver_request"):
        left, right = st.columns(2)
        lat = left.number_input("Latitude (°)", -90.0, 90.0, 28.61, format="%.4f")
        lon = right.number_input("Longitude (°)", -180.0, 180.0, 77.21, format="%.4f")
        radius = left.number_input(
            "Radius (km)", float(MIN_RADIUS_KM), float(MAX_RADIUS_KM), 5.0
        )
        size = right.selectbox("Cell size (m)", CELL_SIZES_M, index=1)
        years = st.slider(
            "Analysis years", FIRST_YEAR, LAST_YEAR, (FIRST_YEAR, LAST_YEAR)
        )
        season = st.selectbox("Period", ["annual", "summer"])
        run = st.form_submit_button("Analyze area", type="primary")
    if run:
        try:
            request = validate_inputs(
                lat=lat,
                lon=lon,
                radius_km=radius,
                cell_size_m=size,
                start_year=years[0],
                end_year=years[1],
            )
        except ValueError as exc:
            st.warning(str(exc))
            return
        if not begin_compute():
            return
        st.session_state.pop("driver_result", None)
        st.session_state.pop("planner_input", None)
        st.session_state.pop("planner_result", None)
        try:
            progress = st.progress(10, text="Extracting satellite observations…")
            try:
                cells = _load_cells(request, season)
                progress.progress(
                    65, text="Scoring exposure and fitting spatial folds…"
                )
                scored = score_exposure(cells).cells
                st.session_state.planner_input = (request, season, scored)
                model = fit_drivers(cells)
                st.session_state.driver_result = (request, season, model)
                progress.progress(100, text="Analysis complete")
            finally:
                progress.empty()
        except (InsufficientDriverData, ExtractionError, EarthEngineAuthError) as exc:
            st.warning(str(exc))
            return
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Area analysis failed (%s)", type(exc).__name__
            )
            st.error("Driver analysis could not finish. Please retry.")
            return


def render_drivers():
    st.header("Land-surface temperature drivers")
    if "driver_result" not in st.session_state:
        st.info(
            "Driver results require at least 150 complete cells in three spatial blocks."
        )
        return
    request, season, model = st.session_state.driver_result
    st.caption(
        f"{request.lat:.4f}°, {request.lon:.4f}° · {request.radius_km:g} km radius · "
        f"{request.cell_size_m} m cells · {season}, {request.start_year}–{request.end_year}"
    )
    a, b = st.columns(2)
    a.metric("Spatial CV R²", f"{model.r2:.3f}")
    b.metric("Spatial CV RMSE (°C)", f"{model.rmse_c:.2f}")
    st.caption(
        f"{len(model.features)} complete cells · {model.excluded_cells} excluded · "
        f"{model.validation.block.nunique()} spatial blocks (2 km) · "
        f"{model.validation.fold.nunique()} held-out folds"
    )
    st.subheader("Drivers across the area")
    st.caption(
        f"Mean absolute SHAP contribution across {len(model.contributions)} cells. "
        "Random forest fitted to Landsat LST using Dynamic World, Sentinel-2 and SRTM."
    )
    st.dataframe(
        model.importance.rename(index=predictor_label)
        .rename("Mean absolute contribution (°C)")
        .rename_axis("Predictor")
    )
    st.subheader("Explain a cell")
    cell = st.selectbox("Cell ID", model.features.index)
    local = model.explain_cell(cell)
    predicted = model.baseline_c + local.sum()
    st.write(
        f"Observed LST {model.validation.at[cell, 'observed_c']:.2f} °C · "
        f"Fitted LST {predicted:.2f} °C · Model baseline {model.baseline_c:.2f} °C"
    )
    st.dataframe(
        local.rename(index=predictor_label)
        .sort_values(key=abs, ascending=False)
        .rename("Signed contribution (°C)")
        .rename_axis("Predictor")
    )
    st.caption(
        "Contributions describe associations learned by the fitted model. Correlated predictors can share credit."
    )
