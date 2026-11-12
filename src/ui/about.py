"""Source notes and optional, spatially validated cooling scenario."""

import streamlit as st
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import GroupKFold, cross_val_predict

from src.index import score_exposure
from src.model import fit_drivers, InsufficientDriverData
from src.planner import rank_sites, estimate_scenario
from src.ui.limits import begin_compute
from src.ui.places import HEAT, AIR


def render_about(place):
    with st.expander("About and limits"):
        st.write(
            "Saved maps use June, July and August 2019–2021, with 500 m zones within 5 km. Summer here misses Delhi’s worst winter air. The lines cover January 2019 through December 2021. Gaps mean the satellite had too few clear readings."
        )
        st.write(
            f"Landsat 8/9 measures {HEAT}; MODIS supplies the monthly daytime readings. Surface temperatures can also be cooler than the air. The maps average clear-sky summer zone measurements across the area; each zone uses a median Landsat composite. The sensors observe different footprints and times."
        )
        st.write(
            f"Sentinel-5P measures nitrogen dioxide: {AIR}. Dynamic World estimates land cover at 10 m. WorldPop estimates the residential population in 2020; people and neighbourhoods change."
        )
        st.write(
            "Overall risk combines heat, air pollution and lack of greenery equally, then accounts for residents. Dark red marks the highest tenth locally, orange the next fifth, pale yellow the next three tenths and blue the lowest four tenths. Compare ranks combined risk across both places together. Darker green means more tree cover. Grey means no data."
        )
        st.write(
            "Markers skip known airfield and restricted-land flags. Land cover cannot establish ownership, permission or airfield boundaries. Check on site before acting. Street tiles come from OpenStreetMap and satellite imagery from Esri."
        )
        st.caption("Landsat (100 m) and MODIS (1 km) disagree in Delhi: MODIS reads about 7 °C cooler over the same summer months. We could not find a day clear in both to pin down why. Possible causes are pixel size, dust or haze filtering and different observation days. Maps use Landsat; monthly lines use MODIS only as change relative to each place's own average.")
        st.caption("Bengaluru's June–August window is its monsoon, so cloud leaves few clear days; March–May would suit it better.")
        if place is None:
            return
        st.write(
            f"Cooling estimates for {place.name} explore what might happen if trees replaced a quarter of existing bare ground. They are estimates, not guarantees."
        )
        if st.button("Estimate cooling and check the model") and begin_compute():
            try:
                with st.spinner("Checking the model against held-out neighbourhoods…"):
                    model = fit_drivers(place.cells)
                    train = model.validation
                    predictions = cross_val_predict(
                        model.forest,
                        model.features,
                        train.observed_c,
                        groups=train.block,
                        cv=GroupKFold(n_splits=min(5, train.block.nunique())),
                    )
                    sites = rank_sites(score_exposure(place.cells), top_n=5)
                    changes = estimate_scenario(model, sites, 25)
                st.write(
                    f"Across held-out 2 km blocks, the root mean square error was {root_mean_squared_error(train.observed_c, predictions):.1f} °C and R² was {r2_score(train.observed_c, predictions):.2f}."
                )
                if changes.delta_c.notna().any():
                    st.write(
                        f"Average modelled change across {changes.delta_c.count()} planting candidates: {changes.delta_c.mean():+.2f} °C. The model holds other land characteristics fixed."
                    )
                else:
                    st.info("No planting candidates had complete model inputs.")
            except InsufficientDriverData:
                st.info("Too few complete zones or neighbourhoods to estimate cooling.")
