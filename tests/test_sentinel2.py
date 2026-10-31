import numpy as np
import pytest

from satmaps.config import InputSpec
from satmaps.core import RECIPES, SENSORS
from satmaps.registry import load_builtin
from satmaps.sensors.optical import sentinel2 as s2
from satmaps.sources import SourceError
from tests.rasters import AREA, X0, Y0, needs_rasterio, write_tif

load_builtin()

# Physical band, bandId, native resolution, min, max, centre. B10 is in the metadata but L2A has no image for it.
SPECTRAL = [("B1", 0, 60, 432, 456, 444.2), ("B2", 1, 10, 454, 525, 489.1), ("B3", 2, 10, 541, 581, 560.6),
            ("B4", 3, 10, 648, 686, 666.5), ("B5", 4, 20, 697, 717, 707.1), ("B6", 5, 20, 731, 752, 741.1),
            ("B7", 6, 20, 771, 798, 784.7), ("B8", 7, 10, 776, 908, 834.6), ("B8A", 8, 20, 852, 880, 865.6),
            ("B9", 9, 60, 934, 961, 947.2), ("B10", 10, 60, 1348, 1397, 1372.2), ("B11", 11, 20, 1552, 1679, 1612.0),
            ("B12", 12, 20, 2066, 2312, 2191.3)]
OFFSETS = {i: -1000 for i in range(13)} | {11: -1100, 12: -1200}  # distinct, so a mis-paired offset shows


def mtd() -> str:
    spectral = "".join(
        f'<Spectral_Information bandId="{i}" physicalBand="{b}"><RESOLUTION unit="m">{r}</RESOLUTION><Wavelength>'
        f'<MIN unit="nm">{lo}</MIN><MAX unit="nm">{hi}</MAX><CENTRAL unit="nm">{c}</CENTRAL></Wavelength></Spectral_Information>'
        for b, i, r, lo, hi, c in SPECTRAL)
    offsets = "".join(f'<BOA_ADD_OFFSET band_id="{i}">{v}</BOA_ADD_OFFSET>' for i, v in OFFSETS.items())
    return ("<n1:Level-2A_User_Product xmlns:n1='https://example.org/s2'><General_Info><Product_Info>"
            "<PRODUCT_START_TIME>2026-09-29T04:15:51.025Z</PRODUCT_START_TIME><PROCESSING_BASELINE>05.13</PROCESSING_BASELINE>"
            "<Datatake><SPACECRAFT_NAME>Sentinel-2C</SPACECRAFT_NAME></Datatake></Product_Info>"
            f"<Product_Image_Characteristics><BOA_QUANTIFICATION_VALUE unit='none'>10000</BOA_QUANTIFICATION_VALUE>"
            f"<BOA_ADD_OFFSET_VALUES_LIST>{offsets}</BOA_ADD_OFFSET_VALUES_LIST>"
            f"<Spectral_Information_List>{spectral}</Spectral_Information_List></Product_Image_Characteristics>"
            "</General_Info></n1:Level-2A_User_Product>")


def safe_folder(tmp_path, dn=None):
    """A tiny L2A product. Band DN: B2 1500, B3 2000, B4 2500, B8 4000, B11 3000, B12 3000, B1 1200; one pixel 0, one 65535."""
    dn = dn or {}
    folder = tmp_path / "S2C_MSIL2A_test.SAFE"
    img = folder / "GRANULE" / "L2A_T46XXX_A000001_20260929T042029" / "IMG_DATA"
    (folder).mkdir()
    (folder / "MTD_MSIL2A.xml").write_text(mtd())
    values = {"B02": 1500, "B03": 2000, "B04": 2500, "B08": 4000, "B11": 3000, "B12": 3000, "B01": 1200} | dn
    for code, res in (("B02", 10), ("B03", 10), ("B04", 10), ("B08", 10), ("B11", 20), ("B12", 20), ("B01", 60)):
        (img / f"R{res}m").mkdir(parents=True, exist_ok=True)
        a = np.full((1000 // res,) * 2, values[code], np.uint16)
        if code == "B04":
            a[30, 30], a[31, 31] = 0, 65535  # no data, saturated (canvas pixel (20, 20) and (21, 21))
        write_tif(img / f"R{res}m" / f"T46XXX_20260929T041551_{code}_{res}m.jp2", [a], res=float(res), size=1000 // res)
    # a downsampled copy of B02 in the 20 m folder: it must not be used
    write_tif(img / "R20m" / "T46XXX_20260929T041551_B02_20m.jp2", [np.full((50, 50), 9999, np.uint16)], res=20.0, size=50)
    scl = np.full((50, 50), 4, np.uint8)  # 20 m: vegetation everywhere ...
    scl[:25, :25] = 9  # ... except a quarter of the scene, which is high-probability cloud
    write_tif(img / "R20m" / "T46XXX_20260929T041551_SCL_20m.jp2", [scl], res=20.0, size=50)
    return folder


def sspec(**opts):
    return InputSpec("S2", "sentinel2", "", {"source": {"path": "S2C_MSIL2A_test.SAFE"}, **opts})


def test_registered_and_band_codes():
    assert "sentinel2" in SENSORS
    assert [s2.band_code(b) for b in ("B1", "B2", "B8A", "B9", "B11", "B12")] == ["B01", "B02", "B8A", "B09", "B11", "B12"]


def test_reflectance_formula_and_nodata_before_offset():
    dn = np.array([0, 65535, 1000, 3500], np.uint16)
    r = s2.to_reflectance(dn, -1000.0, 10000.0)
    assert np.isnan(r[:2]).all()  # nodata and saturation are NaN, not -0.1 and 6.4
    assert r[2] == pytest.approx(0.0) and r[3] == pytest.approx(0.25)


@needs_rasterio
def test_offsets_follow_band_id_not_the_files_found_on_disk(tmp_path):
    safe_folder(tmp_path)
    prod = s2.open_on_canvas(sspec(), AREA.canvas(phase=(X0 + 5, Y0 - 5)), AREA, tmp_path)
    assert np.nanmedian(prod.layers["B11"]) == pytest.approx((3000 - 1100) / 10000)  # band_id 11
    assert np.nanmedian(prod.layers["B12"]) == pytest.approx((3000 - 1200) / 10000)  # band_id 12, not shifted by the missing B10
    assert np.nanmedian(prod.layers["B02"]) == pytest.approx(0.05)  # from the 10 m file, not the 9999 copy in R20m
    assert "B10" not in prod.layers


@needs_rasterio
def test_layers_roles_bands_cloud_and_caveats(tmp_path):
    safe_folder(tmp_path)
    prod = s2.open_on_canvas(sspec(), AREA.canvas(phase=(X0 + 5, Y0 - 5)), AREA, tmp_path)
    assert prod.kind == "optical" and prod.meta["reflectance"] == "surface" and prod.meta["platform"] == "Sentinel-2C"
    assert prod.meta["credit"] == "Contains modified Copernicus Sentinel data 2026" and prod.meta["time_known"] is True
    assert {"B01", "B02", "B03", "B04", "B08", "B11", "B12", "blue", "green", "red", "nir", "swir16", "swir22", "cloud"} == set(prod.layers)
    assert prod.layers["red"] is prod.layers["B04"] and prod.layers["blue"] is prod.layers["B02"]  # the same arrays, not copies
    assert [b.id for b in prod.bands] == ["B01", "B02", "B03", "B04", "B08", "B11", "B12"]  # wavelength order, TCI/AOT/SCL excluded
    b4 = next(b for b in prod.bands if b.id == "B04")
    assert (b4.name, b4.wavelength_nm, b4.range_nm, b4.resolution_m) == ("red", 666.5, (648.0, 686.0), 10.0)
    assert next(b for b in prod.bands if b.id == "B11").resolution_m == 20.0 and next(b for b in prod.bands if b.id == "B01").resolution_m == 60.0
    assert not prod.valid[20, 20] and not prod.valid[21, 21]  # the 0 and 65535 pixels of B04
    # cloud covers scene metres 0-500 in x and y; the canvas spans 100-700, so (400/600)^2 of it is cloud
    assert prod.facts.cloud_pct == pytest.approx(100 * (400 / 600) ** 2, abs=1.5)
    assert any("cloud, shadow or cirrus in view" in c for c in prod.caveats)
    assert any("B01 (60 m)" in c and "B11 (20 m)" in c and "resampled" in c for c in prod.caveats)
    assert RECIPES["true_colour"].render(prod).rgba.shape == (60, 60, 4)  # the existing recipes work unchanged
    info = s2.describe(sspec(), tmp_path)
    assert info.resolution_m == 10 and info.phase == (X0 + 5, Y0 - 5)


def test_a_folder_that_is_not_level_2a_is_explained(tmp_path):
    (tmp_path / "x.SAFE").mkdir()
    with pytest.raises(SourceError, match="MTD_MSIL2A.xml"):
        s2.describe(InputSpec("S2", "sentinel2", "", {"source": {"path": "x.SAFE"}}), tmp_path)
    with pytest.raises(SourceError, match="unknown key"):
        s2._check(sspec(scale=2))
