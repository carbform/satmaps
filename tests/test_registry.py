import pytest

from satviz.core import RECIPES, SENSORS, THEMES, Registry
from satviz.registry import describe
from satviz.sensors.nisar_gcov import to_product
from satviz.sensors.nisar_gcov.io import load_roi


def test_builtins_registered():
    d = describe()
    assert d == {"sensors": ["nisar_gcov"], "recipes": ["sar_fcc"], "themes": ["minimal", "neo_brutal", "neo_retro"]}


def test_registry_rejects_duplicates_and_lists_known():
    r = Registry("widget")
    r.register("a")(1)
    with pytest.raises(ValueError, match="already registered"):
        r.register("a")(2)
    with pytest.raises(KeyError, match="available: a"):
        r.get_or_raise("b")


def test_nisar_product_and_recipe(scene):
    describe()
    d = SENSORS["nisar_gcov"].load(scene, "S")
    p = to_product(d)
    assert p.meta["platform"] == "NISAR" and p.meta["resolution_m"] == 10
    assert p.layers["hh"].shape == p.valid.shape
    assert any("calibration" in c for c in p.caveats)  # S fixture is uncalibrated
    assert not to_product(load_roi(scene, "L")).caveats  # L fixture is calibrated
    r = RECIPES["sar_fcc"](p)
    assert r.rgba.shape == p.valid.shape + (4,) and len(r.extent) == 4 and r.caveats == p.caveats
    assert THEMES["neo_retro"].paper.startswith("#")
