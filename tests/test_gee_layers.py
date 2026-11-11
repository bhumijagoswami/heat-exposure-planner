import math
from unittest.mock import patch

import ee
import pytest
from ee.apitestcase import ApiTestCase

from src import config, gee_layers
from src.validate import validate_inputs


class Pixel(float):
    """Scalar stand-in for EE image arithmetic, with NaN representing a masked pixel."""

    def multiply(self, value):
        return Pixel(self * value)

    def add(self, value):
        return Pixel(self + value)

    def subtract(self, value):
        return Pixel(self - value)

    def bitwiseAnd(self, mask):
        return Pixel(int(self) & mask)

    eq = float.__eq__
    gt = float.__gt__
    lt = float.__lt__
    gte = float.__ge__

    def updateMask(self, keep):
        return self if keep else Pixel("nan")

    def rename(self, name):
        return self


class Scene(dict):
    def select(self, name):
        return Pixel(self[name])


@pytest.mark.parametrize("dn", [40000, 45000, 50000])
def test_clear_landsat_temperature(dn):
    result = gee_layers._temperature(Scene(ST_B10=dn, QA_PIXEL=64))
    assert result == pytest.approx(dn * 0.00341802 + 149 - 273.15)


@pytest.mark.parametrize("dn,qa", [(0, 0)] + [(45000, 1 << bit) for bit in range(6)])
def test_landsat_masks_fill_and_bad_quality(dn, qa):
    assert math.isnan(gee_layers._temperature(Scene(ST_B10=dn, QA_PIXEL=qa)))


@pytest.mark.parametrize("cloud,valid", [(0.29, True), (0.3, False), (0.8, False)])
def test_no2_cloud_mask_retains_valid_negative_columns(cloud, valid):
    scene = Scene(tropospheric_NO2_column_number_density=-0.00001, cloud_fraction=cloud)
    result = gee_layers._nitrogen_dioxide(scene)
    assert result == -0.00001 if valid else math.isnan(result)


@pytest.mark.parametrize("score", [0.59, 0.60, 0.9])
def test_sentinel_indices_and_clear_threshold(score):
    class OpticalScene(Scene):
        def updateMask(self, clear):
            return self if clear else OpticalScene.fromkeys(self, float("nan"))

        def normalizedDifference(self, pair):
            a, b = (self[key] for key in pair)
            return Pixel((a - b) / (a + b))

    scene = OpticalScene(cs_cdf=score, B8=6000, B4=2000, B11=3000, B3=1000)
    with patch.object(ee.Image, "cat", side_effect=lambda *bands: bands):
        values = gee_layers._indices(scene)
    if score < 0.6:
        assert all(math.isnan(value) for value in values)
    else:
        assert values == pytest.approx((0.5, -1 / 3, -0.5))


class TestLayerGraph(ApiTestCase):
    def setUp(self):
        # The SDK test helper replaces this global without restoring it.
        self.addCleanup(
            setattr,
            ee.data,
            "_install_cloud_api_resource",
            ee.data._install_cloud_api_resource,
        )
        super().setUp()

    def test_builds_lazy_annual_and_hemisphere_specific_summer_graphs(self):
        point = ee.Geometry.Point([0, 0])
        with patch.object(
            ee.data,
            "computeValue",
            side_effect=AssertionError("unexpected computation"),
        ):
            for lat, season, months in [
                (30, "annual", None),
                (30, "summer", (6, 8)),
                (-30, "summer", (12, 2)),
            ]:
                request = validate_inputs(lat=lat, lon=0, radius_km=1, cell_size_m=250)
                with patch.object(
                    ee.Filter, "calendarRange", wraps=ee.Filter.calendarRange
                ) as calendar:
                    graph = gee_layers.build_layers(
                        point, request, season=season
                    ).serialize()
                    if months:
                        assert calendar.call_count == 6
                        calendar.assert_called_with(*months, "month")
                    else:
                        calendar.assert_not_called()
                for asset in (
                    *config.LANDSAT_L2,
                    config.S5P_NO2,
                    config.S2_SR,
                    config.S2_CLOUD_SCORE,
                    config.DYNAMIC_WORLD,
                    config.WORLDPOP,
                    config.SRTM,
                ):
                    assert asset in graph
