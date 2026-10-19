import os

import numpy as np
import pytest

from satviz import stac
from satviz.area import Area, AreaError
from satviz.config import InputSpec
from satviz.core import RECIPES
from satviz.registry import load_builtin
from satviz.sensors import stac_optical as so
from satviz.sensors.sentinel2 import SENTINEL2_L2A as S2
from satviz.sources import SourceError

load_builtin()
AREA = Area.from_config({"center": [27.5, 94.9], "size_km": [0.6, 0.6], "resolution_m": 10})
CANVAS = AREA.canvas()  # 60 x 60 pixels


def item(iid, day, tile="46RFR", cloud=5.0):
    assets = {k: {"href": f"https://x/{iid}/{k}.tif", "raster:bands": [{"scale": 0.0001, "offset": -0.1}],
                  "proj:transform": [10, 0, 699960, 0, -10, 3100020], "proj:epsg": 32646}
              for k in ("blue", "green", "red", "nir", "swir16", "swir22")}
    assets["scl"] = {"href": f"https://x/{iid}/scl.tif", "proj:transform": [20, 0, 699960, 0, -20, 3100020]}
    return {"id": iid, "assets": assets,
            "properties": {"datetime": f"{day}T04:30:00Z", "eo:cloud_cover": cloud, "proj:epsg": 32646}}


class FakeWorld:
    """Replaces the catalogue and the COG reader: DN rasters keyed by href, aligned to the canvas."""

    def __init__(self, items, scl_by_item, dn=5000):
        self.items, self.scl, self.dn = items, scl_by_item, dn
        self.searched = 0

    def search(self, prov, collection, bbox, rng, ids=None, **kw):
        self.searched += 1
        return [i for i in self.items if not ids or i["id"] in ids]

    def read_window(self, href, canvas, cache_dir=None):
        iid, name = href.split("/")[-2], href.split("/")[-1].removesuffix(".tif")
        shape = (canvas.height, canvas.width)
        arr = (np.full(shape, self.scl[iid], np.uint16) if name == "scl" else np.full(shape, self.dn, np.uint16))
        return arr, canvas.x, canvas.y, canvas.epsg, (None if name == "scl" else 0)


@pytest.fixture
def world(monkeypatch):
    def install(items, scl, dn=5000):
        w = FakeWorld(items, scl, dn)
        monkeypatch.setattr(stac, "search", w.search)
        monkeypatch.setattr(so, "read_window", w.read_window)
        so._search_cache.clear()
        return w

    return install


def spec(**src):
    return InputSpec("opt", "sentinel2_l2a", "", {"source": {"stac": "earth-search", **src}})


def test_source_errors_are_explained():
    with pytest.raises(SourceError, match="catalogue"):
        so.parse_source(InputSpec("o", "sentinel2_l2a", "", {"source": {"path": "x.tif"}}), S2)
    with pytest.raises(SourceError, match="unknown source key"):
        so.parse_source(spec(date="2026-09-25", cloud=3), S2)
    with pytest.raises(SourceError, match="give `date`"):
        so.parse_source(spec(), S2)
    with pytest.raises(SourceError, match="pick"):
        so.parse_source(spec(date="2026-09-25", pick="best"), S2)


def test_groups_tiles_of_a_day_and_orders_by_distance_from_the_date(world):
    world([item("a", "2026-09-19"), item("b1", "2026-09-24", "46RFR"), item("b2", "2026-09-24", "46RGR"), item("c", "2026-09-30")],
          {"a": 4, "b1": 4, "b2": 4, "c": 4})
    groups = so.candidates(spec(date="2026-09-25"), S2, AREA)
    assert [[i["id"] for i in g] for g in groups] == [["b1", "b2"], ["c"], ["a"]]  # 1, 5 and 6 days away


def test_describe_reads_the_grid_from_metadata(world):
    world([item("a", "2026-09-24")], {"a": 4})
    info = so.describe(spec(date="2026-09-25"), S2, AREA)
    assert info.epsg == 32646 and info.resolution_m == 10 and info.phase == (699965.0, 3100015.0)


def test_cloud_is_measured_in_the_area_and_the_closest_clear_scene_wins(world):
    # SCL 9 = high-probability cloud everywhere on the closest day; the next day is clear vegetation (4)
    world([item("near", "2026-09-24", cloud=2.0), item("far", "2026-09-21", cloud=90.0)], {"near": 9, "far": 4})
    prod = so.open_on_canvas(spec(date="2026-09-25", max_cloud=20), CANVAS, AREA, S2)
    # the tile-wide number said "near" was clear; the area said otherwise, so "far" is used
    assert prod.meta["items"] == ["far"] and prod.facts.cloud_pct == 0
    assert prod.kind == "optical" and prod.meta["attribution"] == "Copernicus Sentinel"
    assert prod.meta["credit"] == "Contains modified Copernicus Sentinel data 2026"
    assert "0% cloud, shadow or cirrus in view" in prod.caveats[0] and "not masked" in prod.caveats[0]


def test_reflectance_scaling_comes_from_the_item_metadata(world):
    world([item("a", "2026-09-24")], {"a": 4}, dn=3000)
    prod = so.open_on_canvas(spec(date="2026-09-25"), CANVAS, AREA, S2)
    assert np.allclose(prod.layers["red"], 3000 * 0.0001 - 0.1)  # 0.2, not a hardcoded constant
    assert prod.layers["red"].shape == (CANVAS.height, CANVAS.width) and prod.valid.all()


def test_no_clear_scene_gives_a_helpful_error(world):
    world([item("a", "2026-09-24")], {"a": 8})
    with pytest.raises(AreaError, match=r"(?s)at most 20% cloud.*24.*cloud 100%.*max_cloud"):
        so.open_on_canvas(spec(date="2026-09-25"), CANVAS, AREA, S2)


def test_a_pinned_item_is_used_whatever_its_cloud(world):
    w = world([item("a", "2026-09-24"), item("b", "2026-09-21")], {"a": 4, "b": 9})
    prod = so.open_on_canvas(spec(item="b"), CANVAS, AREA, S2)
    assert prod.meta["items"] == ["b"] and prod.facts.cloud_pct == 100 and w.searched >= 1


def test_optical_recipes_render_and_check_the_product_kind(world):
    world([item("a", "2026-09-24")], {"a": 4}, dn=3000)
    prod = so.open_on_canvas(spec(date="2026-09-25"), CANVAS, AREA, S2)
    for name in ("true_colour", "nir_fcc", "swir_fcc", "ndvi", "ndwi"):
        r = RECIPES[name].render(prod)
        assert r.rgba.shape == (CANVAS.height, CANVAS.width, 4) and r.rgba[..., 3].min() == 255 and r.title and r.legend
        assert r.caveats == prod.caveats
    assert RECIPES["true_colour"].shared_lims([prod]) ["RGB"][1] > 0
    assert RECIPES["true_colour"].kind == "optical" and RECIPES["sar_fcc"].kind == "sar"


def test_compare_refuses_a_recipe_of_the_wrong_kind(scene, world, tmp_path, layouts_dir):
    from satviz.layout import LayoutError, load_layout
    from satviz.sensors.nisar_gcov import load as load_nisar
    from satviz.templates import compare

    world([item("a", "2026-09-24")], {"a": 4})
    opt = so.open_on_canvas(spec(date="2026-09-25"), CANVAS, AREA, S2)
    prods = {"S": load_nisar(scene, "S"), "opt": opt}
    with pytest.raises(LayoutError, match="needs a sar product but input 'opt' is optical"):
        compare.render(scene, prods, tmp_path, load_layout(layouts_dir, "ls_social"), inputs=("S", "opt"), recipe="sar_fcc")


def test_stac_signing_only_where_a_provider_needs_it(monkeypatch):
    assert stac.sign("earth-search", "sentinel-2-l2a", "https://x/a.tif") == "https://x/a.tif"
    calls = []
    monkeypatch.setattr(stac, "_request", lambda url, body=None: calls.append(url) or {"token": "sv=1&sig=abc"})
    stac._tokens.clear()
    assert stac.sign("planetary-computer", "landsat-c2-l2", "https://b/a.tif") == "https://b/a.tif?sv=1&sig=abc"
    assert stac.sign("planetary-computer", "landsat-c2-l2", "https://b/a.tif?x=1").endswith("?x=1&sv=1&sig=abc")
    assert len(calls) == 1  # the token is reused
    with pytest.raises(stac.StacError, match="unknown STAC provider"):
        stac.provider("nope")


@pytest.mark.skipif(os.environ.get("SATVIZ_TEST_NETWORK") != "1", reason="set SATVIZ_TEST_NETWORK=1 to query the live catalogue")
def test_live_earth_search_finds_sentinel2_near_dibrugarh():
    items = stac.search("earth-search", "sentinel-2-l2a", (94.7, 27.45, 95.05, 27.75), "2026-09-15T00:00:00Z/2026-10-05T23:59:59Z")
    assert items and "proj:epsg" in items[0]["properties"] and stac.scale_offset(items[0], "red")[0] == 0.0001
