import numpy as np
import pytest

from satviz.config import InputSpec
from satviz.core import RECIPES, SENSORS
from satviz.registry import load_builtin
from satviz.sensors import eos04
from satviz.sources import SourceError
from tests.test_geotiff_sensors import AREA, X0, Y0, needs_rasterio, write_tif

load_builtin()

K_BETA0, NOISE = 67.14, 14560.657
META = f"""SatID=EOS-04
ImagingMode=MRS 
Node=DESCENDING
SceneCenterTime=11-OCT-2026 00:28:53.945000000
TxRxPol1=HH
TxRxPol2=HV
Calibration_Constant_Beta0_HH={K_BETA0}
Calibration_Constant_Beta0_HV={K_BETA0}
Calibration_Constant_Gamma0_HH=68.233
Calibration_Constant_Gamma0_HV=68.233
Image_Noise_Bias_HH={NOISE}
Image_Noise_Bias_HV=10882.483
RTC_Apply_Flag=1
"""


def product_folder(tmp_path, dn_hh=3000, dn_hv=900, rtc=1):
    folder = tmp_path / "E04_scene"
    folder.mkdir()
    (folder / "product.xml").write_text("<p><RadarBand>C</RadarBand><RadarCenterFrequency units='Hz'>5.40e09</RadarCenterFrequency></p>")
    (folder / "BAND_META.txt").write_text(META.replace("RTC_Apply_Flag=1", f"RTC_Apply_Flag={rtc}"))
    for pol, v in (("HH", dn_hh), ("HV", dn_hv)):
        (folder / f"scene_{pol}").mkdir()
        a = np.full((100, 100), v, np.uint16)
        a[:10] = 0
        a[50:60, 50:60] = 50  # below the noise bias: DN^2 = 2500 < N
        write_tif(folder / f"scene_{pol}" / f"imagery_{pol}.tif", [a], res=10.0)
    mask = np.full((100, 100), 128, np.uint16)
    mask[:10] = 0
    mask[35:45, 35:45] = 16  # layover
    mask[20:30, 20:30] = 64  # shadow
    write_tif(folder / "E04_scene_mask.tif", [mask], res=10.0)
    return folder


def espec(**opts):
    return InputSpec("E", "eos04", "", {"source": {"path": "E04_scene"}, **opts})


def test_registered():
    assert "eos04" in SENSORS


def test_gamma0_linear_follows_the_document_equations():
    dn = np.array([0, 50, 1000, 3000])
    g = eos04.gamma0_linear(dn, K_BETA0, NOISE)
    assert np.isnan(g[:2]).all()  # outside the image, and below the noise bias
    k = 10 ** (K_BETA0 / 10)
    assert g[2] == pytest.approx((1000**2 - NOISE) / k, rel=1e-5) and g[3] == pytest.approx((3000**2 - NOISE) / k, rel=1e-5)
    # eq. 9 for DN well above the bias: 20 log10(DN) - Kcal_dB
    assert 10 * np.log10(g[3]) == pytest.approx(20 * np.log10(3000) - K_BETA0, abs=0.01)


@needs_rasterio
def test_open_on_canvas_layers_mask_and_credit(tmp_path):
    product_folder(tmp_path)
    prod = eos04.open_on_canvas(espec(), AREA.canvas(phase=(X0 + 5, Y0 - 5)), AREA, tmp_path)
    assert prod.kind == "sar" and set(prod.layers) == {"co", "cross"} and prod.facts.polarisations == "HH/HV"
    assert prod.meta["credit"] == "EOS-04 SAR data, NRSC/ISRO" and prod.meta["platform"] == "EOS-04"
    assert prod.meta["radar_band"] == "C" and prod.meta["freq_ghz"] == 5.4
    # canvas pixel (r, c) is raster pixel (r + 10, c + 10)
    assert not prod.valid[15, 15] and not prod.valid[30, 30] and prod.valid[5, 5]  # shadow, layover, clear
    assert np.isnan(prod.layers["co"][45, 45]) and not prod.valid[45, 45]  # DN below the noise bias
    assert np.isnan(prod.layers["co"][~prod.valid]).all()  # masked pixels carry no value
    assert any("noise bias subtracted" in c and "layover and shadow masked" in c for c in prod.caveats)
    assert not any("NOT terrain-normalised" in c for c in prod.caveats)
    assert RECIPES["sar_fcc"].render(prod).rgba.shape == (60, 60, 4)
    info = eos04.describe(espec(), tmp_path)
    assert info.resolution_m == 10 and info.phase == (X0 + 5, Y0 - 5)


@needs_rasterio
def test_failed_terrain_registration_is_stated(tmp_path):
    product_folder(tmp_path, rtc=0)
    prod = eos04.open_on_canvas(espec(), AREA.canvas(phase=(X0 + 5, Y0 - 5)), AREA, tmp_path)
    assert any("NOT terrain-normalised" in c for c in prod.caveats)


def test_missing_pieces_are_reported(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SourceError, match="BAND_META"):
        eos04.describe(InputSpec("E", "eos04", "", {"source": {"path": "empty"}}), tmp_path)
    with pytest.raises(SourceError, match="unknown key"):
        eos04._check(espec(scale=2))
    with pytest.raises(SourceError, match="dual-polarisation"):
        eos04._pols({"TxRxPol1": "HH"})
