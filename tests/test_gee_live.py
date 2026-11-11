import ee
import pytest

from src.gee_auth import initialize_earth_engine


@pytest.mark.live
def test_earth_engine_can_compute():
    initialize_earth_engine()
    assert ee.Number(1).getInfo() == 1
