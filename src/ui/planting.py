"""Run the existing planting model on demand and retain results for this place."""

import hashlib
import logging

import pandas as pd
import streamlit as st
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import GroupKFold, cross_val_predict

from src.model import InsufficientDriverData, fit_drivers
from src.planner import estimate_scenario, rank_sites
from src.ui.limits import begin_compute


def change_words(delta, lower, upper):
    if pd.isna(delta) or pd.isna(lower) or pd.isna(upper):
        return "Insufficient readings"
    if lower <= 0 <= upper:
        return "Inconclusive"
    return f"{abs(delta):.2f} °C {'cooler' if delta < 0 else 'warmer'}"


def run_planting(cells):
    model = fit_drivers(cells)
    train = model.validation
    predictions = cross_val_predict(
        model.forest,
        model.features,
        train.observed_c,
        groups=train.block,
        cv=GroupKFold(n_splits=min(5, train.block.nunique())),
    )
    sites = rank_sites(cells, top_n=5)
    changes = estimate_scenario(model, sites, 25)
    return {
        "sites": sites.join(changes),
        "r2": r2_score(train.observed_c, predictions),
        "rmse": root_mean_squared_error(train.observed_c, predictions),
    }


def _place_key(place, cells):
    # Include geometry and observations so refreshed custom areas cannot reuse stale results.
    signature = pd.util.hash_pandas_object(cells, index=True).to_numpy().tobytes()
    return place.name, str(place.request), hashlib.sha256(signature).hexdigest()


def render_planting(place, cells):
    st.subheader("Could planting trees help here?")
    st.write(
        "Check up to five candidate sites where trees could replace a quarter of existing bare ground."
    )
    st.write(
        "Temperature and range cards describe the highest-risk modelled candidate; the estimates are indicative, not causal."
    )
    key = _place_key(place, cells)
    saved = st.session_state.get("story_planting_result")
    if saved and saved["key"] != key:
        st.session_state.pop("story_planting_result", None)
        saved = None
    if st.button("Run planting model", type="primary") and begin_compute():
        try:
            with st.spinner(
                "Checking neighbourhoods and estimating the planting range…"
            ):
                saved = {"key": key, **run_planting(cells)}
            st.session_state["story_planting_result"] = saved
        except InsufficientDriverData:
            st.info(
                "This area needs at least 150 complete zones and three 2 km neighbourhood blocks with varying temperatures to estimate planting effects."
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Planting estimate unavailable (%s)", type(exc).__name__
            )
            st.warning(
                "The planting estimate could not finish; try again later or choose a saved place."
            )
    if saved:
        sites = saved["sites"]
        measured = sites.dropna(subset=["delta_c", "lower_c", "upper_c"])
        if measured.empty:
            st.info(
                "No candidate sites have enough complete readings for a planting estimate."
            )
        else:
            first = measured.iloc[0]
            cards = st.columns(3)
            cards[0].metric(
                "Candidate sites",
                f"{len(measured)}",
                help="Modelled sites among the five highest-risk screened candidates.",
            )
            cards[1].metric(
                "Estimated temperature change",
                change_words(first.delta_c, first.lower_c, first.upper_c),
            )
            cards[2].metric(
                "Range (95%)",
                f"{first.lower_c:+.2f} to {first.upper_c:+.2f} °C",
                help="Spatial bootstrap interval for the highest-risk modelled candidate; negative means cooler.",
            )
            if first.lower_c <= 0 <= first.upper_c:
                st.info("No clear cooling effect here; treat as inconclusive")
            elif first.lower_c > 0:
                st.info(
                    "This model does not support cooling at the highest-risk candidate; check the site before planning an intervention."
                )
            table = pd.DataFrame(
                {
                    "Site (grid ID)": measured.index,
                    "Risk (0–1)": measured.exposure.round(3).to_numpy(),
                    "Bare ground planted (m²)": measured.converted_m2.round().to_numpy(),
                    "Estimated change": [
                        change_words(r.delta_c, r.lower_c, r.upper_c)
                        for r in measured.itertuples()
                    ],
                    "Range (°C)": [
                        f"{r.lower_c:+.2f} to {r.upper_c:+.2f}"
                        for r in measured.itertuples()
                    ],
                    "Checks needed": measured.land_use_review.to_numpy(),
                }
            )
            st.dataframe(table, hide_index=True, width="stretch")
        with st.expander("Model check"):
            st.write(
                f"Held-out neighbourhoods: typical prediction error {saved['rmse']:.1f} °C (RMSE); R² = {saved['r2']:.2f}."
            )
            st.write(
                "Whole 2 km blocks are held out together; the range comes from 100 spatial block bootstrap refits."
            )
    st.caption(
        "Indicative estimate from a random forest on this area's land cover, greenery and terrain; assumes 25% of existing bare ground becomes trees."
    )
