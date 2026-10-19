import numpy as np
import pytest

from satviz.area import Area, AreaError
from satviz.config import InputSpec
from satviz.core import RECIPES
from satviz.registry import load_builtin
from satviz.sensors import geotiff
from satviz.sensors import stac_optical as so
from satviz.sensors.landsat import LANDSAT_C2L2 as LS
from satviz.sensors.sentinel1 import SENTINEL1_RTC as S1
from satviz.sources import SourceError
from tests.test_optical import FakeWorld, item, spec

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

load_builtin()
EPSG = 32646
X0, Y0 = 500000.0, 3000000.0
AREA = Area(EPSG, X0 + 100, Y0 - 700, X0 + 700, Y0 - 100, 10)  # 60 x 60 canvas inside the rasters below


def write_tif(path, arrays, res=10.0, size=100, nodata=None):
    with rasterio.open(path, "w", driver="GTiff", height=size, width=size, count=len(arrays), dtype=arrays[0].dtype,
                       crs=f"EPSG:{EPSG}", transform=from_origin(X0, Y0, res, res), nodata=nodata) as dst:
        for i, a in enumerate(arrays, 1):
            dst.write(a, i)


def gspec(**opts):
    base = dict(kind="optical", source={"path": "scene.tif"}, bands={"red": 3, "green": 2, "blue": 1}, scale=0.0001, offset=-0.1,
                nodata=0, date="2026-09-25", platform="ResourceSat-2", label="LISS-IV", credit="ResourceSat-2 LISS-IV, NRSC/ISRO")
    base.update(opts)
    return InputSpec("liss", "geotiff", "", base)


def test_geotiff_optical_band_map_scale_and_credit(tmp_path):
    dn = [np.full((100, 100), v, np.uint16) for v in (1000, 2000, 3000)]  # band 1 blue, 2 green, 3 red
    dn[2][:10] = 0  # nodata rows in the red band
    write_tif(tmp_path / "scene.tif", dn)
    canvas = AREA.canvas(phase=(X0 + 5, Y0 - 5))
    prod = geotiff.open_on_canvas(gspec(), canvas, AREA, tmp_path)
    assert prod.kind == "optical" and set(prod.layers) == {"red", "green", "blue"}
    assert np.allclose(prod.layers["blue"], 1000 * 0.0001 - 0.1) and np.allclose(prod.layers["red"], 3000 * 0.0001 - 0.1)
    assert prod.meta["credit"] == "ResourceSat-2 LISS-IV, NRSC/ISRO" and prod.meta["attribution"] == prod.meta["credit"]
    assert prod.meta["time_known"] is False and any("Reflectance = value x 0.0001" in c for c in prod.caveats)
    assert RECIPES["true_colour"].render(prod).rgba.shape == (60, 60, 4)
    info = geotiff.describe(gspec(), tmp_path)
    assert info.epsg == EPSG and info.resolution_m == 10 and info.phase == (X0 + 5, Y0 - 5)


def test_geotiff_one_file_per_band_and_coarse_pixels_are_declared(tmp_path):
    for name, v in (("b1", 10), ("b2", 20)):
        write_tif(tmp_path / f"{name}.tif", [np.full((20, 20), v, np.uint16)], res=50.0, size=20)
    spec_ = gspec(source={"path": "b1.tif"}, bands={"blue": "b1.tif", "green": "b2.tif", "red": "b2.tif"}, scale=1.0, offset=0.0)
    prod = geotiff.open_on_canvas(spec_, AREA.canvas(), AREA, tmp_path)
    assert np.allclose(prod.layers["green"], 20) and any("50 m pixels are resampled" in c for c in prod.caveats)


def test_geotiff_sar_amplitude_becomes_power_and_uses_the_generic_sar_recipe(tmp_path):
    ramp = np.linspace(0.05, 0.2, 100, dtype=np.float32)[None, :].repeat(100, 0)
    write_tif(tmp_path / "sar.tif", [ramp, ramp / 2])
    s = InputSpec("alos", "geotiff", "", dict(kind="sar", source={"path": "sar.tif"}, bands={"co": 1, "cross": 2}, values="amplitude",
                                              date="2026-09-25", platform="ALOS-2", label="PALSAR", credit="ALOS-2 PALSAR, JAXA"))
    prod = geotiff.open_on_canvas(s, AREA.canvas(), AREA, tmp_path)
    assert prod.kind == "sar" and np.allclose(prod.layers["co"][0, 0], ramp[0, 10] ** 2, rtol=0.05)  # amplitude -> power
    r = RECIPES["sar_fcc"].render(prod)
    assert r.rgba.shape == (60, 60, 4) and len(r.components) == 3 and r.title
    assert RECIPES["sar_fcc"].shared_lims([prod])["HH"][0] < RECIPES["sar_fcc"].shared_lims([prod])["HH"][1]


@pytest.mark.parametrize("opts, msg", [
    ({"kind": "radar"}, "kind"),
    ({"bands": {}}, "band map"),
    ({"bands": {"purple": 1}}, "unknown band"),
    ({"date": ""}, "`date` is required"),
    ({"credit": ""}, "`credit` is required"),
    ({"colour": 1}, "unknown key"),
])
def test_geotiff_misconfiguration_is_explained(tmp_path, opts, msg):
    with pytest.raises(SourceError, match=msg):
        geotiff.open_on_canvas(gspec(**opts), AREA.canvas(), AREA, tmp_path)


def test_a_recipe_missing_a_band_is_refused_clearly(tmp_path):
    write_tif(tmp_path / "scene.tif", [np.full((100, 100), 1000, np.uint16)] * 3)
    prod = geotiff.open_on_canvas(gspec(), AREA.canvas(), AREA, tmp_path)
    from satviz.core import check_recipe

    with pytest.raises(ValueError, match=r"recipe 'ndvi' needs band\(s\) nir.*input 'liss' does not have"):
        check_recipe("ndvi", RECIPES["ndvi"], prod, "liss")


def test_a_file_that_misses_the_area_is_reported(tmp_path):
    write_tif(tmp_path / "scene.tif", [np.full((100, 100), 1000, np.uint16)] * 3)
    far = Area(EPSG, X0 + 50_000, Y0 - 50_700, X0 + 50_600, Y0 - 50_100, 10)
    with pytest.raises(AreaError, match="does not cover the area"):
        geotiff.open_on_canvas(gspec(), far.canvas(), far, tmp_path)


def test_landsat_quality_bits_and_platform_name(monkeypatch):
    world = FakeWorld([], {})
    items = [item("LC08_x", "2026-09-25")]
    items[0]["properties"].update({"platform": "landsat-8", "landsat:wrs_path": "135"})
    for k in ("blue", "green", "red", "nir08", "swir16", "swir22", "qa_pixel"):
        items[0]["assets"][k] = {"href": f"https://x/LC08_x/{k}.tif", "raster:bands": [{"scale": 2.75e-05, "offset": -0.2}],
                                 "proj:transform": [30, 0, 699960, 0, -30, 3100020]}
    world.items = items
    world.scl = {"LC08_x": 0}
    q = np.array([0, 1, 21824, 21824 | 0b1000, 21824 | 0b10000, 21824 | 0b100])
    assert list(LS.nodata_mask(q)) == [True, True, False, False, False, False]
    assert list(LS.cloud_mask(q)) == [False, False, False, True, True, True]  # cloud, shadow, cirrus
    assert LS.platform_of(items[0]) == "Landsat 8" and "courtesy of the U.S. Geological Survey" in LS.credit(2026, "Landsat 8")
    assert so.describe_group(items[0], LS)[0] == 30


def test_sentinel1_picks_polarisations_orbit_query_and_has_no_cloud(monkeypatch):
    it = item("S1D_x", "2026-09-25")
    it["assets"] = {"vv": {"href": "https://x/S1D_x/vv.tif", "proj:transform": [10, 0, 699960, 0, -10, 3100020]},
                    "vh": {"href": "https://x/S1D_x/vh.tif"}}
    it["properties"].update({"platform": "sentinel-1d", "sat:relative_orbit": 143, "sat:orbit_state": "ascending",
                             "sar:polarizations": ["VV", "VH"]})
    assert S1.bands_for(it) == {"co": "vv", "cross": "vh"} and S1.platform_of(it) == "Sentinel-1D"
    assert S1.bands_for({"assets": {"hh": {}, "hv": {}}}) == {"co": "hh", "cross": "hv"}
    assert S1.extra_query({"orbit": "ascending"}) == {"sat:orbit_state": {"eq": "ascending"}} and S1.extra_query({}) is None

    class W(FakeWorld):
        def read_window(self, href, canvas, cache_dir=None):
            shape = (canvas.height, canvas.width)
            v = 0.2 if href.endswith("vv.tif") else 0.02
            return np.full(shape, v, np.float32), canvas.x, canvas.y, canvas.epsg, -32768.0

    w = W([it], {})
    monkeypatch.setattr("satviz.stac.search", w.search)
    monkeypatch.setattr("satviz.stac.sign", lambda prov, coll, href: href)  # no network for the access token
    monkeypatch.setattr(so, "read_window", w.read_window)
    so._search_cache.clear()
    area = Area.from_config({"center": [27.5, 94.9], "size_km": [0.6, 0.6], "resolution_m": 10})
    prod = so.open_on_canvas(InputSpec("s1", "sentinel1_rtc", "", {"source": {"stac": "planetary-computer", "date": "2026-09-25"}}),
                             area.canvas(), area, S1)
    assert prod.kind == "sar" and prod.meta["platform"] == "Sentinel-1D" and prod.facts.polarisations == "VV/VH"
    assert np.allclose(prod.layers["co"], 0.2) and prod.valid.all() and prod.facts.cloud_pct == 0
    assert "no noise floor published" in prod.caveats[0] and prod.meta["attribution"] == "Copernicus Sentinel"
    from satviz.sensors.sentinel2 import SENTINEL2_L2A

    with pytest.raises(SourceError, match="orbit"):  # optical collections have no orbit direction to filter on
        so.parse_source(spec(date="2026-09-25", orbit="ascending"), SENTINEL2_L2A)
