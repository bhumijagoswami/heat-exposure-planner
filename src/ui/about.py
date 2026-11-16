"""Concise sources, interpretation and operating limits."""

import pandas as pd
import streamlit as st

from src.ui.score import render_score_formula


def render_about(*, include_score=True):
    with st.expander("How this works and what to keep in mind"):
        st.subheader("What you are looking at")
        st.write(
            "Saved maps combine satellite observations for June–August 2019–21 in 500 m zones "
            "within 5 km of each city centre. Colours locate relative risks and cover patterns; "
            "monthly charts show available observations across January 2019–December 2021."
        )
        st.subheader("How the score works")
        if include_score:
            render_score_formula()
            st.write(
                "Each rank is (average rank − 0.5) / count; population uses the same rule, "
                "with zero residents giving zero risk."
            )
        else:
            st.write(
                "The ‘How the risk score works’ card above explains the equal-weight formula and population rank."
            )
        st.write(
            "Story ranks are local; Compare ranks combined risk across both places together. "
            "Blue is the lowest 40%, yellow the next 30%, orange the next 20% and dark red the highest 10%; grey means missing data."
        )
        st.table(
            pd.DataFrame(
                [
                    ["Surface heat", "Landsat 8/9", "~100 m thermal", "Summer 2019–21"],
                    [
                        "Air pollution (NO₂)",
                        "Sentinel-5P",
                        "Several km pixels",
                        "Summer 2019–21",
                    ],
                    ["Greenery", "Sentinel-2 NDVI", "10 m", "Summer 2019–21"],
                    ["Land cover", "Dynamic World", "10 m", "Summer 2019–21"],
                    ["People", "WorldPop", "100 m, 2020 baseline", "2020"],
                    ["Terrain", "SRTM", "30 m", "2000"],
                    [
                        "Monthly surface heat / NO₂",
                        "MODIS / Sentinel-5P",
                        "1 km / several km",
                        "Jan 2019–Dec 2021",
                    ],
                ],
                columns=["Layer", "Source", "Detail", "Period"],
            ).set_index("Layer")
        )
        st.subheader("Good to know")
        st.markdown(
            "- **Summer and clear skies only:** maps miss winter pollution, and monsoon clouds leave gaps in Bengaluru, so averages can favour clearer days.\n"
            "- **NO₂ columns span several kilometres:** they cannot locate street-level pollution or measure the concentration people breathe.\n"
            "- **Surface heat differs from air temperature:** it describes roofs and ground; Landsat and MODIS also differ by about 7.5 °C in Delhi’s available summer observations, so sensor values are not interchangeable.\n"
            "- **People use a 2020 baseline:** WorldPop estimates residential counts, so growth and daytime movement are missing.\n"
            "- **Airfield and restricted-land flags are incomplete:** markers and candidate sites still need ownership, safety and access checks.\n"
            "- **Planting estimates are indicative:** land cover is uncertain and the model learns associations, so an interval including zero is inconclusive."
        )
        with st.expander("Technical notes"):
            st.write(
                "Inputs are checked on the server: finite coordinates, radius 1–15 km, supported "
                "grid sizes and dates, and at most 2,500 cells; Compare fixes the radius at 5 km."
            )
            st.write(
                "Live work uses batches of at most 500 cells, a shared 10-second cooldown, "
                "90-second request timeouts with at most two retries, and cached data for up to one day (50 entries). "
                "Saved city data work offline; street and imagery tiles need internet."
            )
            st.write(
                "Cloud masks and joint valid-area coverage control missing scores. Dynamic World "
                "is a probabilistic classification; the fixed WorldPop collection is deprecated. "
                "Street tiles: OpenStreetMap; imagery: Esri."
            )
