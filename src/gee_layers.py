"""Lazy Earth Engine composites for a validated ROI and analysis period."""

from typing import Literal

import ee

from . import config
from .validate import AnalysisRequest

DW_CLASSES = (
    "water",
    "trees",
    "grass",
    "flooded_vegetation",
    "crops",
    "shrub_and_scrub",
    "built",
    "bare",
    "snow_and_ice",
)
INDICES = ("ndvi", "ndbi", "mndwi")


def _with_schema(image, names):
    """Supply fully masked bands when a collection reducer has no input images."""
    empty = ee.Image.constant([0] * len(names)).rename(list(names)).selfMask()
    return empty.addBands(image, overwrite=True).select(list(names))


def _temperature(image):
    # QA_PIXEL bits 0–5 flag fill, dilated cloud, cirrus, cloud, shadow and snow.
    clear = image.select("QA_PIXEL").bitwiseAnd(0b111111).eq(0)
    thermal = image.select("ST_B10")
    return (
        thermal.multiply(0.00341802)
        .add(149.0)
        .subtract(273.15)
        .updateMask(clear)
        .updateMask(thermal.gt(0))
        .rename("lst_c")
    )


def _nitrogen_dioxide(image):
    column = image.select("tropospheric_NO2_column_number_density")
    return column.updateMask(image.select("cloud_fraction").lt(0.3)).rename(
        "no2_mol_m2"
    )


def _no2_composite(collection, request):
    # Reduce independent years first. Summing observation counts keeps the
    # overall mean weighted by valid observations even when cloud cover varies.
    reducer = ee.Reducer.sum().combine(ee.Reducer.count(), sharedInputs=True)
    bands = ["no2_mol_m2_sum", "no2_mol_m2_count"]
    partials = []
    for year in range(request.start_year, request.end_year + 1):
        images = collection.filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        partials.append(
            _with_schema(images.map(_nitrogen_dioxide).reduce(reducer), bands)
        )
    totals = ee.ImageCollection.fromImages(partials).sum()
    count = totals.select(bands[1])
    mean = totals.select(bands[0]).divide(count).updateMask(count.gt(0))
    # Keep NO2 on the catalog's 0.01° grid when other bands are reduced at 30 m.
    return mean.rename("no2_mol_m2").reproject(
        crs="EPSG:4326", crsTransform=[0.01, 0, -180, 0, -0.01, 90]
    )


def _indices(image):
    clear = image.updateMask(image.select("cs_cdf").gte(0.6))
    # The shared reflectance scale cancels in each normalized difference.
    pairs = (("B8", "B4"), ("B11", "B8"), ("B3", "B11"))
    return ee.Image.cat(
        *(
            clear.normalizedDifference(list(pair)).rename(name)
            for pair, name in zip(pairs, INDICES, strict=True)
        )
    )


def _land_cover(collection):
    label = _with_schema(collection.select("label").mode(), ["label"]).rename(
        "dw_label"
    )
    probabilities = _with_schema(collection.select(list(DW_CLASSES)).mean(), DW_CLASSES)
    # Spatially averaging each indicator yields its fraction of classified cell area.
    indicators = [
        label.eq(i).rename(f"dw_frac_{name}") for i, name in enumerate(DW_CLASSES)
    ]
    return ee.Image.cat(
        label, probabilities.rename([f"dw_prob_{n}" for n in DW_CLASSES]), *indicators
    )


def _population(roi):
    tiles = (
        ee.ImageCollection(config.WORLDPOP)
        .filterBounds(roi)
        .filter(ee.Filter.eq("year", config.WORLDPOP_YEAR))
        .select("population")
    )
    # Preserve the native count grid for subsequent area-weighted population sums.
    image = ee.Image(
        ee.Algorithms.If(
            tiles.limit(1).size(),
            tiles.mosaic().setDefaultProjection(ee.Image(tiles.first()).projection()),
            ee.Image.constant(0).selfMask().rename("population"),
        )
    )
    return image.rename("population")


def build_layers(
    roi: ee.Geometry,
    request: AnalysisRequest,
    *,
    season: Literal["annual", "summer"] = "annual",
    clip_to_roi: bool = True,
) -> ee.Image:
    """Build one consistent period; summer uses JJA north and DJF south within selected years.

    WorldPop counts use a fixed 2020 baseline. SRTM elevation and slope are static.
    Request an explicit CRS and scale when reducing multi-sensor composites.
    """
    if season not in ("annual", "summer"):
        raise ValueError("Season must be annual or summer.")

    # Catalog bounds filters only need a small enclosing geometry. Keep the ROI at
    # the antimeridian/poles where a geographic envelope can span every longitude.
    search_roi = (
        roi.bounds(1) if abs(request.lon) < 179 and abs(request.lat) < 85 else roi
    )

    def scenes(asset):
        images = (
            ee.ImageCollection(asset)
            .filterBounds(search_roi)
            .filterDate(f"{request.start_year}-01-01", f"{request.end_year + 1}-01-01")
        )
        if season == "summer":
            start, end = (6, 8) if request.lat >= 0 else (12, 2)
            images = images.filter(ee.Filter.calendarRange(start, end, "month"))
        return images

    l8, l9 = (scenes(asset) for asset in config.LANDSAT_L2)
    thermal = l8.merge(l9).filter(ee.Filter.eq("PROCESSING_LEVEL", "L2SP"))
    lst = _with_schema(thermal.map(_temperature).median(), ["lst_c"])
    no2 = _no2_composite(scenes(config.S5P_NO2), request)
    # Match each SR scene to its QA once across the collection.
    joined = ee.Join.saveFirst("cloud_score").apply(
        scenes(config.S2_SR),
        scenes(config.S2_CLOUD_SCORE).select("cs_cdf"),
        ee.Filter.equals(leftField="system:index", rightField="system:index"),
    )

    def clear_indices(image):
        return _indices(image.addBands(ee.Image(image.get("cloud_score"))))

    optical = ee.ImageCollection(joined).map(clear_indices)
    indices = _with_schema(optical.median(), INDICES)
    elevation = ee.Image(config.SRTM).select("elevation")
    layers = ee.Image.cat(
        lst,
        no2,
        indices,
        _land_cover(scenes(config.DYNAMIC_WORLD)),
        elevation.rename("elevation_m"),
        ee.Terrain.slope(elevation).rename("slope_deg"),
        _population(roi),
    )
    # Zonal reducers handle edge pixels using their actual overlap with the cell.
    if clip_to_roi:
        layers = layers.clip(roi)
    return layers.set(
        {
            "season": season,
            "start_year": request.start_year,
            "end_year": request.end_year,
            "population_year": config.WORLDPOP_YEAR,
        }
    )
