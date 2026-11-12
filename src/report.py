"""Computed exposure brief and in-memory exports for one analysis."""

from dataclasses import dataclass
from html import escape
from io import BytesIO

import geopandas as gpd
import pandas as pd

from .zones import hotspot_level, zone_directory
from .config import WORLDPOP_YEAR
from .model import DriverModel, predictor_label
from .planner import rank_sites
from .validate import AnalysisRequest


@dataclass
class Report:
    cells: gpd.GeoDataFrame
    sections: list[tuple[str, list[str]]]

    def markdown(self) -> str:
        lines = ["# Compound exposure briefing"]
        for heading, paragraphs in self.sections:
            lines.extend(["", f"## {heading}"])
            for paragraph in paragraphs:
                lines.extend(["", escape(paragraph, quote=False)])
        return "\n".join(lines) + "\n"

    def html(self) -> str:
        body = []
        for heading, paragraphs in self.sections:
            body.append(f"<section><h2>{escape(heading)}</h2>")
            body.extend(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
            body.append("</section>")
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Compound exposure briefing</title></head><body><main>"
            "<h1>Compound exposure briefing</h1>"
            + "".join(body)
            + "</main></body></html>"
        )

    def csv(self) -> bytes:
        return (
            self.cells.drop(columns=self.cells.geometry.name)
            .to_csv(index=False)
            .encode("utf-8")
        )

    def geojson(self) -> bytes:
        # RFC 7946 handles CRS conversion and antimeridian cutting in the writer.
        data = BytesIO()
        self.cells.to_file(
            data,
            driver="GeoJSON",
            engine="pyogrio",
            index=False,
            layer="exposure_cells",
            RFC7946="YES",
            COORDINATE_PRECISION=9,
        )
        return data.getvalue()


def _population_text(cells):
    pop = cells.population.where(cells.population.ge(0))
    total = pop.sum(min_count=1)
    if pd.isna(total) or total <= 0:
        return "Population share is unavailable because the area has no positive population estimate."
    priority = cells.robust_priority
    unknown = pop[priority.isna()].sum()
    if not priority.notna().any():
        return f"Priority could not be assessed for any cell. The available population estimate is {total:,.0f} residents."
    robust = priority.fillna(False)
    residents = pop[robust].sum()
    return (
        f"{int(robust.sum())} cells rank in the top quintile under all four schemes. "
        f"They contain an estimated {residents:,.0f} residents, or {100 * residents / total:.1f}% "
        f"of the {total:,.0f} residents in cells with population estimates. "
        f"Cells with unknown priority account for {unknown:,.0f} estimated residents. "
        f"Population estimates are available for {int(pop.notna().sum())} of {len(pop)} cells."
    )


def build_report(
    cells: gpd.GeoDataFrame,
    request: AnalysisRequest,
    season: str,
    *,
    scheme: str = "equal",
    top_n: int = 10,
    percent: float = 25,
    model: DriverModel | None = None,
    scenario: pd.DataFrame | None = None,
) -> Report:
    sites = rank_sites(cells, scheme, top_n)
    # A projected centroid stays inside each convex clipped square.
    centers = cells.geometry.centroid.to_crs(4326)
    zones = zone_directory(cells)
    located = cells.assign(latitude=centers.y, longitude=centers.x).join(zones, on="cell_id")
    score = f"exposure_{scheme}"
    ranked = located.dropna(subset=[score]).sort_values(
        [score, "cell_id"], ascending=[False, True]
    )
    coverage = (
        (cells.coverage_pct.fillna(0) * cells.area_m2).sum() / cells.area_m2.sum()
        if len(cells)
        else 0
    )
    area = (
        f"Centre {request.lat:.4f}°, {request.lon:.4f}°. Radius {request.radius_km:g} km. "
        f"{request.cell_size_m} m grid. {season.capitalize()} observations, "
        f"{request.start_year}–{request.end_year}. The {scheme.replace('_', ' ')} scheme is shown. "
        f"{len(ranked)} of {len(cells)} cells have hotspot scores. Joint valid-area coverage is {coverage:.1f}%."
    )
    hotspots = [
        f"{i}. {zones.at[cell, 'Zone']} ({lat:.4f}°, {lon:.4f}°) has a Hotspot score of {value:.4f} ({hotspot_level(value)})."
        for i, (cell, lat, lon, value) in enumerate(
            ranked[["cell_id", "latitude", "longitude", score]]
            .head(5)
            .itertuples(index=False, name=None),
            1,
        )
    ]
    drivers = ["The driver model is unavailable for this analysis."]
    if model is not None:
        drivers = [
            f"The model used {len(model.features)} cells. Spatial validation gave R² {model.r2:.3f} "
            f"and RMSE {model.rmse_c:.2f} °C.",
            "The largest mean absolute SHAP contributions were "
            + ", ".join(
                f"{predictor_label(name)} ({value:.3f} °C)"
                for name, value in model.importance.nlargest(3).items()
            )
            + ".",
        ]
    plan = ["No scored cells met the planting criteria."]
    selection = sites[["cumulative_exposure_pct", "land_use_review"]].copy()
    selection["planner_rank"] = pd.array(range(1, len(sites) + 1), dtype="Int64")
    if not sites.empty:
        first = sites.index[0]
        cumulative = sites.cumulative_exposure_pct.iloc[-1]
        share = (
            f"Together they cover {cumulative:.1f}% of summed area hotspot scores."
            if pd.notna(cumulative)
            else "Exposure coverage is undefined because the total score is zero."
        )
        plan = [
            f"The selected list contains {len(sites)} planting sites. {zones.at[first, 'Zone']} ranks first. Land-use check: {sites.at[first, 'land_use_review']}. {share}"
        ]
        if scenario is None:
            plan.append(
                "A temperature scenario has not been estimated for this selection."
            )
        else:
            if not sites.index.equals(scenario.index):
                raise ValueError("Scenario cells must match the ranked selection.")
            selection = selection.join(scenario)
            plan.append(
                f"The scenario converts {percent:g}% of existing bare cover to trees, "
                f"an estimated {scenario.converted_m2.sum():,.0f} m² across the selected sites."
            )
            available = scenario.dropna(subset=["delta_c", "lower_c", "upper_c"])
            if not available.empty:
                cell = available.index[0]
                row = available.iloc[0]
                plan.append(
                    f"For {zones.at[cell, 'Zone']}, predicted ΔLST is {row.delta_c:+.2f} °C "
                    f"(95% spatial bootstrap interval {row.lower_c:+.2f} to {row.upper_c:+.2f} °C)."
                )
            else:
                plan.append(
                    "The selected sites lack complete inputs for temperature estimates."
                )
    export = located.join(selection, on="cell_id", validate="one_to_one").copy()
    export["scheme"] = scheme
    export["season"] = season
    export["start_year"], export["end_year"] = request.start_year, request.end_year
    export["population_year"] = WORLDPOP_YEAR
    if scenario is not None:
        export["bare_conversion_pct"] = percent
    caveats = [
        f"Landsat measures land-surface temperature. Its thermal observations have approximately 100 m native resolution. "
        f"Sentinel-5P integrates NO₂ through the tropospheric column over a footprint coarser than the planner cells. "
        f"WorldPop population estimates use {WORLDPOP_YEAR}. Dynamic World cover is probabilistic. "
        "Cloud and data gaps can bias coverage and relative ranks. Driver associations and planting scenarios "
        "are model-based, indicative, not causal."
    ]
    return Report(
        export,
        [
            ("Analysis area", [area]),
            ("Highest hotspot scores", hotspots or ["No zones have a valid hotspot score."]),
            ("Robust-priority population", [_population_text(cells)]),
            ("Temperature drivers", drivers),
            ("Intervention plan", plan),
            ("Interpretation", caveats),
        ],
    )
