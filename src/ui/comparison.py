"""Two places under matched summer filters and a common map scale."""

import altair as alt
import pandas as pd
import streamlit as st

from src.config import summer_months
from src.ui.basemap import (
    COLORS,
    LAND_COLORS,
    LAYERS,
    pooled_risk,
    relative_bands,
    render_map,
)
from src.ui.places import HEAT, choose_place, mean, monthly_line


def stats(place):
    cells = place.cells.set_index("cell_id")
    temp = mean(cells, "lst_c")
    hot = relative_bands(cells, "lst_c").eq(3)
    known = cells.dropna(subset=["population", "lst_c"])
    total = known.population.sum()
    return [
        temp,
        mean(cells[hot], "lst_c") - temp,
        mean(cells, "no2_mol_m2") * 1_000_000,
        100 * mean(cells, "dw_frac_trees"),
        cells.population.sum(min_count=1),
        100 * known.loc[known.lst_c > 40, "population"].sum() / total
        if total
        else float("nan"),
    ]


def render_comparison():
    st.title("Which place carries more heat?")
    places = []
    for i, col in enumerate(st.columns(2)):
        with col:
            places.append(choose_place("Place " + "AB"[i], i, "compare" + "AB"[i]))
    if any(p is None for p in places):
        return None
    a, b = places
    if summer_months(a.request.lat) != summer_months(b.request.lat):
        st.warning(
            "These places use different summer months. Choose two places with the same summer window."
        )
        return a
    st.caption(
        "Both places use the same summer months and the same satellite cloud filters."
    )
    layer = st.radio("Map layer", [*LAYERS[1:], "Combined risk"], horizontal=True)
    bands = (
        pooled_risk([p.cells for p in places])
        if layer == "Combined risk"
        else (None, None)
    )
    for place, column, pooled in zip(places, st.columns(2), bands):
        with column:
            st.subheader(place.name)
            render_map(
                place.cells,
                layer=layer,
                pooled=pooled,
                caption=f"{layer} · "
                + (
                    {
                        "Surface heat": "Landsat 8/9",
                        "Tree cover": "Dynamic World",
                        "Built-up share": "Dynamic World",
                        "Land cover type": "Dynamic World",
                        "People": "WorldPop (2020)",
                        "Combined risk": "Landsat, Sentinel-2, Sentinel-5P and WorldPop (2020)",
                    }[layer]
                )
                + f" · {place.window}.",
            )
    left, right = stats(a), stats(b)
    labels = [
        "Summer surface temperature (°C)",
        "Hottest tenth above local average (°C)",
        "Area nitrogen dioxide (µmol/m²)",
        "Tree cover (%)",
        "Estimated residents",
        "Residents in zones above 40 °C (%)",
    ]
    rows = []
    for i, (label, x, y) in enumerate(zip(labels, left, right)):
        values = [f"{v:,.0f}" if i == 4 else f"{v:,.1f}" for v in (x, y)]
        values = [
            value if pd.notna(v) else "No readings" for value, v in zip(values, (x, y))
        ]
        if pd.notna(x) and pd.notna(y) and x != y:
            worse = int(y > x) if i != 3 else int(y < x)
            values[worse] = "↑ " + values[worse]
            if i == 2 and min(x, y) > 0:
                values[worse] += f" ({100 * (max(x, y) / min(x, y) - 1):.0f}% higher)"
        rows.append([label, *values])
    st.table(
        pd.DataFrame(
            rows, columns=["Summer comparison", "A · " + a.name, "B · " + b.name]
        ).set_index("Summer comparison")
    )
    st.caption(
        "↑ marks the less favourable reading; on the population row it identifies the larger number of residents potentially affected."
    )
    for field in ("roi_day_c", "roi_no2"):
        monthly_line(places, field)
    covers = []
    for i, p in enumerate(places):
        fractions = p.cells.filter(regex="^dw_frac_")
        known = p.cells.loc[fractions.notna().all(axis=1)]
        values = {
            label: 100 * mean(known, "dw_frac_" + field)
            for field, label in (
                ("built", "Built-up"),
                ("trees", "Trees"),
                ("bare", "Bare"),
                ("grass", "Grass"),
                ("water", "Water"),
            )
        }
        values["Other (farmland, shrub)"] = (
            max(0.0, 100 - sum(values.values())) if known.shape[0] else float("nan")
        )
        covers.extend(
            {"Place": "AB"[i] + " · " + p.name, "Land": label, "Share": v}
            for label, v in values.items()
        )
    cover = pd.DataFrame(covers)
    built = cover.loc[cover.Land.eq("Built-up"), "Share"].tolist()
    st.subheader(
        f"Built-up land covers {built[0]:.0f}% of A and {built[1]:.0f}% of B"
        if all(pd.notna(built))
        else "Land cover observations are incomplete"
    )
    st.altair_chart(
        alt.Chart(cover)
        .mark_bar()
        .encode(
            y=alt.Y("Place:N", title=None, axis=alt.Axis(labelLimit=0)),
            x=alt.X("sum(Share):Q", title="Land cover (%)"),
            color=alt.Color(
                "Land:N",
                legend=alt.Legend(labelLimit=0, orient="bottom", columns=2),
                scale=alt.Scale(
                    domain=list(LAND_COLORS),
                    range=list(LAND_COLORS.values()),
                ),
            ),
            tooltip=["Land:N", alt.Tooltip("Share:Q", format=".1f")],
        ),
        width="stretch",
    )
    st.caption(f"Share of land by cover type · Dynamic World (10 m) · {a.window}.")
    shares = [left[-1], right[-1]]
    st.subheader(
        f"{shares[0]:.0f}% of residents in A and {shares[1]:.0f}% in B live in zones where the ground surface exceeds 40 °C"
        if all(pd.notna(shares))
        else "Population or heat observations are incomplete"
    )
    chart = pd.DataFrame({"Place": ["A · " + a.name, "B · " + b.name], "Share": shares})
    base = alt.Chart(chart).encode(
        y=alt.Y("Place:N", title=None, axis=alt.Axis(labelLimit=0)),
        x=alt.X(
            "Share:Q",
            title="Residents in zones where the ground surface exceeds 40 °C (%)",
            scale=alt.Scale(domain=[0, 100]),
        ),
    )
    zeros = base.transform_filter("datum.Share === 0").mark_text(
        align="left", dx=4, text="0%"
    )
    st.altair_chart(base.mark_bar(color=COLORS[2]) + zeros, width="stretch")
    st.caption(
        f"Residents in zones above 40 °C among those with temperature readings · Landsat 8/9 ({HEAT}), WorldPop (2020) · {a.window}."
    )
    first = (
        f"Average surface temperatures were {left[0]:.1f} °C in A and {right[0]:.1f} °C in B."
        if all(pd.notna([left[0], right[0]]))
        else "Missing heat readings limit the comparison."
    )
    second = (
        f"The hottest tenth ran {left[1]:.1f} °C above average in A and {right[1]:.1f} °C above average in B."
        if all(pd.notna([left[1], right[1]]))
        else "The hottest-zones gap could not be measured in both places."
    )
    st.info(first + " " + second)
    return a
