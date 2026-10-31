import math
from datetime import datetime

import numpy as np
import pytest

from satmaps.config import InputSpec
from satmaps.core import RECIPES, SENSORS
from satmaps.registry import load_builtin
from satmaps.sensors.optical import liss4
from satmaps.sources import SourceError
from tests.rasters import AREA, EPSG, X0, Y0, needs_rasterio, write_tif

load_builtin()

META = """SatID= IRS-R2
Sensor= L4FX
Path= 103
Row= 062
SceneCenterTime= 05-OCT-2026 04:47:22.601994
SunElevationAtCenter=  58.551725
B2SaturationRadiance=  47.5614
B3SaturationRadiance=  45.6990
B4SaturationRadiance=  31.5000
"""


def product_folder(tmp_path, dn=(145, 118, 228)):
    folder = tmp_path / "R2F_scene"
    folder.mkdir()
    (folder / "R2F_scene.meta").write_text(META)
    for band, v in zip((2, 3, 4), dn, strict=True):
        a = np.full((100, 100), v, np.uint16)
        a[:10] = 0  # outside the scene
        write_tif(folder / f"BAND{band}.tif", [a], res=10.0)
    return folder


def lspec(**opts):
    return InputSpec("liss", "liss4", "", {"source": {"path": "R2F_scene"}, **opts})


def test_registered_and_meta_parsed(tmp_path):
    assert "liss4" in SENSORS
    meta = liss4.read_meta(product_folder(tmp_path))
    assert meta["Path"] == "103" and liss4._when(meta) == datetime(2026, 10, 5, 4, 47, 22)


def test_toa_reflectance_formula_and_plausible_range():
    meta = {"B2SaturationRadiance": "47.5614", "SunElevationAtCenter": "58.551725"}
    when = datetime(2026, 10, 5, 4, 47, 22)
    rho = liss4.toa_reflectance(np.array([145]), "green", meta, when)[0]
    d = liss4.earth_sun_distance(when)
    expected = math.pi * 145 * 47.5614 / 1024 * d**2 / (181.89 * math.sin(math.radians(58.551725)))
    assert rho == pytest.approx(expected, rel=1e-5) and 0.10 < rho < 0.18  # a median land pixel is a few tens of percent at most
    assert 0.98 < d < 1.02


@needs_rasterio
def test_open_on_canvas_layers_valid_and_credit(tmp_path):
    product_folder(tmp_path)
    canvas = AREA.canvas(phase=(X0 + 5, Y0 - 5))
    prod = liss4.open_on_canvas(lspec(), canvas, AREA, tmp_path)
    assert prod.kind == "optical" and set(prod.layers) == {"green", "red", "nir"}
    assert prod.meta["credit"] == "ResourceSat-2 LISS-IV data, NRSC/ISRO" and prod.meta["time_known"] is True
    assert prod.meta["start"] == datetime(2026, 10, 5, 4, 47, 22) and prod.facts.path_row == "103/062"
    assert np.isfinite(prod.layers["red"]).all() and prod.valid.all()  # canvas sits below the DN 0 rows
    assert any("No blue band" in c for c in prod.caveats)
    assert RECIPES["nir_fcc"].render(prod).rgba.shape == (60, 60, 4)
    info = liss4.describe(lspec(), tmp_path)
    assert info.epsg == EPSG and info.resolution_m == 10


@needs_rasterio
def test_true_colour_is_refused_without_blue(tmp_path):
    from satmaps.core import check_recipe

    product_folder(tmp_path)
    prod = liss4.open_on_canvas(lspec(), AREA.canvas(phase=(X0 + 5, Y0 - 5)), AREA, tmp_path)
    with pytest.raises(ValueError, match="blue"):
        check_recipe("true_colour", RECIPES["true_colour"], prod, "liss")


def test_folder_without_meta_and_unknown_key(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SourceError, match="no \\*.meta"):
        liss4.read_meta(tmp_path / "empty")
    with pytest.raises(SourceError, match="unknown key"):
        liss4._check(lspec(scale=2))


@needs_rasterio
def test_raster_epsg_falls_back_for_untagged_utm(tmp_path):
    import rasterio
    from pyproj import CRS
    from rasterio.transform import from_origin

    from satmaps.cog import raster_epsg

    wkt = CRS.from_epsg(32644).to_wkt().replace(',ID["EPSG",32644]', "")
    path = tmp_path / "untagged.tif"
    with rasterio.open(path, "w", driver="GTiff", height=4, width=4, count=1, dtype="uint16", crs=wkt,
                       transform=from_origin(500000, 1800000, 5, 5)) as dst:
        dst.write(np.ones((4, 4), np.uint16), 1)
    with rasterio.open(path) as src:
        assert raster_epsg(src) == 32644


META_R2A = """SatID= IRS-R2A
Sensor= L4FX
Path= 113
Row= 052
SceneCenterTime= 19-OCT-2026 04:25:42.369583
SunElevationAtCenter=  49.515075
B2_Lmax=  52.0000
B3_Lmax=  47.0000
B4_Lmax=  31.5000
"""


@needs_rasterio
def test_resourcesat_2a_with_only_lmax_is_read_and_named_as_2a(tmp_path):
    folder = product_folder(tmp_path)
    (folder / "R2F_scene.meta").write_text(META_R2A)
    canvas = AREA.canvas(phase=(X0 + 5, Y0 - 5))
    prod = liss4.open_on_canvas(lspec(), canvas, AREA, tmp_path)
    assert prod.meta["platform"] == "ResourceSat-2A" and prod.meta["credit"] == "ResourceSat-2A LISS-IV data, NRSC/ISRO"
    assert prod.meta["reflectance"] == "top-of-atmosphere"
    note = next(c for c in prod.caveats if "top-of-atmosphere" in c)
    assert "B*_Lmax" in note and "may differ for 2A" in note  # the constant used, and the irradiance caveat, are stated
    # Lmax (52) not the SaturationRadiance field: the reflectance follows the scale that is there
    assert liss4.radiance_scale(liss4.nrsc.read_meta(folder, "*.meta"), "green") == (52.0, "B*_Lmax")


def test_the_saturation_radiance_field_is_preferred_when_both_exist():
    meta = {"B2SaturationRadiance": "47.5614", "B2_Lmax": "52"}
    assert liss4.radiance_scale(meta, "green") == (47.5614, "B*SaturationRadiance")
    with pytest.raises(SourceError, match="neither"):
        liss4.radiance_scale({}, "green")


@needs_rasterio
def test_band_table_comes_from_the_handbook_ranges(tmp_path):
    product_folder(tmp_path)
    prod = liss4.open_on_canvas(lspec(), AREA.canvas(phase=(X0 + 5, Y0 - 5)), AREA, tmp_path)
    assert [b.id for b in prod.bands] == ["B2", "B3", "B4"] and [b.layer for b in prod.bands] == ["green", "red", "nir"]
    assert prod.bands[1].range_nm == (620.0, 680.0) and prod.bands[1].wavelength_nm is None  # only a nominal range is known
