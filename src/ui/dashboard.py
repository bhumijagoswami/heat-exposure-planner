"""Place story, from heat and pollution to the first actions."""

import altair as alt
import pandas as pd
import streamlit as st

from src.demo import PRESETS
from src.index import score_exposure
from src.ui.basemap import (
    COLORS,
    LAYERS,
    marker_records,
    relative_bands,
    render_map,
    select_markers,
)
from src.ui.places import AIR, HEAT, LAND, choose_place, mean, monthly_line, preset

ACTIONS = {
    "Hot and treeless": "Add shade trees or shade structures and use cooler paving.",
    "Hot and crowded": "Prioritise cool roofs, shaded walkways and cooling shelters.",
    "Hot": "Check the hottest walking routes and add shade where people wait.",
}


def land_chart(place):
    cells = place.cells
    fields = cells.filter(regex="^dw_frac_")
    dominant = (
        fields.fillna(-1)
        .idxmax(axis=1)
        .str.removeprefix("dw_frac_")
        .map(LAND)
        .where(fields.max(axis=1) > 0)
    )
    overall = mean(cells, "lst_c")
    rows = []
    for name, group in cells.dropna(subset=["lst_c"]).groupby(dominant):
        if len(group) >= 5:
            rows.append(
                {
                    "Land type": name,
                    "Difference": mean(group, "lst_c") - overall,
                    "Zones": len(group),
                }
            )
    if not rows:
        st.info("Too few zones share a land type to compare their temperatures.")
        return
    data = pd.DataFrame(rows).sort_values("Difference", ascending=False)
    top = data.iloc[0]
    st.subheader(
        f"{top['Land type']} ran {abs(top.Difference):.1f} °C {'hotter' if top.Difference >= 0 else 'cooler'} than average"
    )
    data["Label"] = [
        f"{v:+.1f} ({n} zones)" for v, n in zip(data.Difference, data.Zones)
    ]
    base = alt.Chart(data).encode(
        y=alt.Y("Land type:N", sort="-x", title=None),
        x=alt.X(
            "Difference:Q",
            title="Difference from area average (°C)",
            axis=alt.Axis(format="+.1f"),
        ),
    )
    bars = base.mark_bar().encode(
        color=alt.condition(
            "datum.Difference > 0", alt.value(COLORS[2]), alt.value(COLORS[0])
        )
    )
    labels = base.mark_text(align="left", dx=4).encode(text="Label:N")
    st.altair_chart(bars + labels, width="stretch")
    st.caption(
        f"Average temperature by dominant land type (five or more zones) · Landsat 8/9, {HEAT}; Dynamic World (10 m) · {place.window}."
    )


def render_story():
    st.title("Where do heat and air pollution put people most at risk?")
    place = choose_place("Choose a place", 0, "story", custom_radius=True)
    if place is None:
        return None
    cells = score_exposure(place.cells)
    indexed = cells.set_index("cell_id")
    bands = relative_bands(indexed, "exposure_equal")
    highest = bands.eq(3)
    residents = indexed.loc[highest, "population"].sum()
    if bands.eq(4).all():
        st.warning("There are too few overlapping observations to identify hotspots.")
        return place
    st.info(
        f"An estimated **{residents:,.0f} residents** live in the **{highest.sum()} zones** where heat, pollution and limited greenery combine with the greatest population exposure."
    )
    layer = st.radio("Map layer", list(LAYERS), horizontal=True)
    keys = select_markers(cells)
    render_map(
        cells,
        layer=layer,
        keys=keys,
        caption=f"{layer} and first-action zones · Landsat 8/9 ({HEAT}), Sentinel-5P ({AIR}), Sentinel-2, Dynamic World (10 m), WorldPop (2020) · {place.window}.",
    )
    for column, label, value in zip(
        st.columns(3),
        [
            "Average surface temperature (°C)",
            "Estimated residents",
            "Residents in very high zones",
        ],
        [
            f"{mean(cells, 'lst_c'):.1f}",
            f"{cells.population.sum():,.0f}",
            f"{residents:,.0f}",
        ],
    ):
        column.metric(label, value)
    st.subheader(f"{len(keys)} zones to check first")
    for record in marker_records(indexed, keys):
        with st.container(border=True):
            st.markdown(f"**Zone {record['number']} · {record['tag']}**")
            st.write(ACTIONS[record["tag"]])
    land_chart(place)
    for field in ["roi_day_c", "roi_no2"]:
        monthly_line([place], field)
    other = next(name for name in PRESETS if name != place.name)
    try:
        reference = mean(preset(other).cells, "no2_mol_m2")
    except OSError:
        reference = float("nan")
    value = mean(cells, "no2_mol_m2")
    if reference > 0 and pd.notna(value):
        gap = 100 * (value / reference - 1)
        st.info(
            f"Air pollution: satellite NO₂ over this area is {abs(gap):.0f}% {'higher' if gap >= 0 else 'lower'} than {other}. NO₂ comes mostly from traffic and industry, so traffic and emission measures are the first priority."
        )
    else:
        st.caption("There are insufficient observations to compare air pollution.")
    return place
