"""One shared, plain-language explanation of the map's equal-weight score."""

import streamlit as st


def render_score_formula():
    st.latex(
        r"\begin{aligned}\text{Hazard} &= \tfrac13\text{Heat}"
        r"+\tfrac13\text{Air pollution (NO}_2\text{)}"
        r"+\tfrac13\text{Lack of greenery}\\"
        r"\text{Risk} &= \text{Hazard}\times\text{Population rank}\end{aligned}"
    )
    st.write("**Heat:** the zone's surface-temperature rank; hotter zones rank higher.")
    st.write(
        "**Air pollution:** the zone's satellite NO₂ rank; higher columns rank higher."
    )
    st.write(
        "**Lack of greenery:** one minus the NDVI rank; less green zones rank higher."
    )


def render_rank_detail():
    st.write(
        "Ranks run from 0 to 1 within the city: (average rank − 0.5) / count; ties share "
        "a rank. Heat uses lst_c, pollution uses no2_mol_m2, and greenery uses ndvi. "
        "Subtracting the same area-average temperature leaves the heat ranks unchanged."
    )
    st.write(
        "Population rank applies the same rule to population; zero residents means zero risk. "
        "The map uses zones with all three hazard readings and valid area, then ranks population "
        "where hazard, population and joint coverage are available; missing scores stay unknown."
    )
