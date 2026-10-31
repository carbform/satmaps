import numpy as np
import pytest

from satmaps.area import Area
from satmaps.config import InputSpec
from satmaps.core import RECIPES, SENSORS
from satmaps.registry import load_builtin
from satmaps.sensors.sar import sentinel1 as g
from satmaps.sources import SourceError
from tests.rasters import needs_rasterio

load_builtin()

SIZE = 200
LON0, LAT0, STEP = 94.80, 27.70, 0.0001  # image pixel (row, col) sits at (LON0 + col*STEP, LAT0 - row*STEP)
CAL_A, NOISE_R, NOISE_AZ = 100.0, 1000.0, 2.0


def vec(tag, line, pixel_tag, values, extra=""):
    px = " ".join(str(p) for p in range(0, SIZE, 50))
    return (f"<{tag}><line>{line}</line><pixel count='4'>{px}</pixel><{pixel_tag} count='4'>{values}</{pixel_tag}>{extra}</{tag}>")


def safe_folder(tmp_path):
    import rasterio
    from rasterio.control import GroundControlPoint
    from rasterio.transform import Affine

    folder = tmp_path / "S1X_IW_GRDH_test.SAFE"
    for d in ("measurement", "annotation/calibration"):
        (folder / d).mkdir(parents=True)
    for pol in ("vv", "vh"):
        stem = f"s1x-iw-grd-{pol}-20260925t114837-20260925t114902-004734-008dbe-00{1 if pol == 'vv' else 2}"
        dn = np.full((SIZE, SIZE), 600, np.uint16)
        dn[100, 120] = 3000  # a bright point scatterer
        dn[:, :5] = 0  # outside the swath
        gcps = [GroundControlPoint(row=r, col=c, x=LON0 + c * STEP, y=LAT0 - r * STEP, z=0.0)
                for r in range(0, SIZE, 40) for c in list(range(0, SIZE, 40)) + [SIZE - 1]]
        with rasterio.open(folder / "measurement" / f"{stem}.tiff", "w", driver="GTiff", height=SIZE, width=SIZE, count=1,
                           dtype="uint16", transform=Affine.identity()) as dst:
            dst.write(dn, 1)
            dst.gcps = (gcps, "EPSG:4326")
        (folder / "annotation" / f"{stem}.xml").write_text(
            "<product><adsHeader><missionId>S1D</missionId></adsHeader>"
            "<productFirstLineUtcTime>2026-09-25T11:48:37.5</productFirstLineUtcTime>"
            "<productLastLineUtcTime>2026-09-25T11:49:02.5</productLastLineUtcTime><pass>Ascending</pass>"
            "<radarFrequency>5.405000454334350e+09</radarFrequency><rangePixelSpacing>1.0e+01</rangePixelSpacing><relativeOrbitNumber>12</relativeOrbitNumber></product>")
        a = " ".join([str(CAL_A)] * 4)
        (folder / "annotation" / "calibration" / f"calibration-{stem}.xml").write_text(
            "<calibration><calibrationVectorList>" + vec("calibrationVector", 0, "sigmaNought", a)
            + vec("calibrationVector", SIZE - 1, "sigmaNought", a) + "</calibrationVectorList></calibration>")
        nr = " ".join([str(NOISE_R)] * 4)
        az = (f"<noiseAzimuthVector><swath>IW1</swath><firstAzimuthLine>0</firstAzimuthLine><firstRangeSample>0</firstRangeSample>"
              f"<lastAzimuthLine>{SIZE - 1}</lastAzimuthLine><lastRangeSample>{SIZE - 1}</lastRangeSample>"
              f"<line count='2'>0 {SIZE - 1}</line><noiseAzimuthLut count='2'>{NOISE_AZ} {NOISE_AZ}</noiseAzimuthLut>"
              "</noiseAzimuthVector>")
        (folder / "annotation" / "calibration" / f"noise-{stem}.xml").write_text(
            "<noise><noiseRangeVectorList>" + vec("noiseRangeVector", 0, "noiseRangeLut", nr)
            + vec("noiseRangeVector", SIZE - 1, "noiseRangeLut", nr) + "</noiseRangeVectorList>"
            f"<noiseAzimuthVectorList>{az}</noiseAzimuthVectorList></noise>")
    return folder


def test_registered():
    assert "sentinel1" in SENSORS


def test_lut_interpolates_between_lines_and_across_pixels():
    vecs = [(0.0, np.array([0.0, 10.0]), np.array([1.0, 3.0])), (10.0, np.array([0.0, 10.0]), np.array([5.0, 7.0]))]
    out = g.lut_on_grid(vecs, np.array([0.0, 5.0, 10.0, 20.0]), np.array([0.0, 5.0, 10.0]))
    assert out[0].tolist() == [1.0, 2.0, 3.0] and out[1].tolist() == [3.0, 4.0, 5.0]
    assert out[3].tolist() == [5.0, 6.0, 7.0]  # beyond the last vector the value is held


def test_azimuth_noise_applies_only_inside_its_swath_block():
    blocks = [dict(first_line=0, last_line=9, first_sample=0, last_sample=4, lines=np.array([0.0, 9.0]), lut=np.array([2.0, 4.0]))]
    out = g.azimuth_noise_on_grid(blocks, np.arange(10.0), np.arange(8.0))
    assert out[0, 0] == 2.0 and out[9, 4] == 4.0 and (out[:, 5:] == 1.0).all()


def test_sigma0_follows_dn2_minus_noise_over_a_squared():
    dn = np.array([[0, 40], [500, 3000]], np.uint16)
    cal = [(0.0, np.array([0.0, 1.0]), np.array([CAL_A, CAL_A]))]
    nr = [(0.0, np.array([0.0, 1.0]), np.array([NOISE_R, NOISE_R]))]
    az = [dict(first_line=0, last_line=1, first_sample=0, last_sample=1, lines=np.array([0.0, 1.0]), lut=np.array([2.0, 2.0]))]
    s0, share = g.sigma0(dn, 0, 0, cal, nr, az)
    n = NOISE_R * NOISE_AZ
    assert np.isnan(s0[0, 0]) and np.isnan(s0[0, 1])  # outside the swath; below the noise
    assert s0[1, 0] == pytest.approx((500**2 - n) / CAL_A**2) and s0[1, 1] == pytest.approx((3000**2 - n) / CAL_A**2)
    assert share == pytest.approx(1 / 3)  # one of the three pixels inside the swath is under the noise


@needs_rasterio
def test_open_on_canvas_geolocates_calibrates_and_credits(tmp_path):
    folder = safe_folder(tmp_path)
    lon, lat = LON0 + 120 * STEP, LAT0 - 100 * STEP  # where the bright point is
    area = Area.from_config(dict(center=[lat, lon], size_km=[0.8, 0.8], resolution_m=10))
    canvas = area.canvas(10)
    spec = InputSpec("S1", "sentinel1", "", {"source": {"path": folder.name}})
    prod = g.open_on_canvas(spec, canvas, area, tmp_path)
    assert prod.kind == "sar" and set(prod.layers) == {"co", "cross"} and prod.facts.polarisations == "VV/VH"
    assert prod.meta["platform"] == "Sentinel-1D" and prod.meta["credit"] == "Contains modified Copernicus Sentinel data 2026"
    assert prod.meta["radar_band"] == "C" and prod.meta["wavelength_cm"] == pytest.approx(5.55, abs=0.01)
    assert any("not terrain-flattened" in c for c in prod.caveats)
    co = prod.layers["co"]
    flat = (600**2 - NOISE_R * NOISE_AZ) / CAL_A**2
    assert np.nanmedian(co) == pytest.approx(flat, rel=0.02)
    # the bright scatterer must land on the canvas pixel nearest its true position (GCP chain, not just calibration)
    from pyproj import Transformer

    ex, ey = Transformer.from_crs("EPSG:4326", f"EPSG:{canvas.epsg}", always_xy=True).transform(lon, lat)
    er, ec = np.argmin(np.abs(canvas.y - ey)), np.argmin(np.abs(canvas.x - ex))
    r, c = np.unravel_index(np.nanargmax(co), co.shape)
    assert abs(r - er) <= 1 and abs(c - ec) <= 1
    assert RECIPES["sar_fcc"].render(prod).rgba.shape[:2] == co.shape
    info = g.describe(spec, tmp_path)
    assert info.resolution_m == 10


def test_missing_measurement_and_unknown_key(tmp_path):
    (tmp_path / "empty.SAFE").mkdir()
    with pytest.raises(SourceError, match="measurement"):
        g.describe(InputSpec("S1", "sentinel1", "", {"source": {"path": "empty.SAFE"}}), tmp_path)
    with pytest.raises(SourceError, match="unknown key"):
        g._check(InputSpec("S1", "sentinel1", "", {"source": {"path": "x"}, "scale": 1}))
    with pytest.raises(SourceError, match="VV\\+VH or HH\\+HV"):
        g._pols({"VV": 1})
