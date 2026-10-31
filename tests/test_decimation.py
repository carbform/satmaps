"""Reading a coarse canvas strip by strip gives what reading the whole window and averaging would."""
import numpy as np
import pytest

from satmaps.area import Area
from satmaps.config import BandSpec
from satmaps.grid import _block_mean, to_canvas
from satmaps.sensors.sar import sentinel1 as g
from satmaps.sensors.sar.nisar import io as nisar_io
from tests.conftest import H, W, make_raw, write_granule
from tests.rasters import AREA, EPSG, X0, Y0, needs_rasterio, write_tif


def test_nisar_read_reduced_while_reading_equals_the_block_mean_of_the_full_read(tmp_path, monkeypatch):
    write_granule(tmp_path / "L.h5", "science/LSAR/GCOV", make_raw(seed=3), instrument="LSAR", freq_hz=1.239e9)
    spec = BandSpec("w", "L.h5", "science/LSAR/GCOV", (0, H), (0, W))
    monkeypatch.setattr(nisar_io, "STRIP", 7)  # several strips, so the seams are tested
    full, k2 = nisar_io.read_roi(tmp_path / "L.h5", spec), nisar_io.read_roi(tmp_path / "L.h5", spec, 2)
    for layer in ("hh", "hv", "eta"):
        assert np.allclose(k2[layer], _block_mean(full[layer], 2), rtol=1e-5, equal_nan=True)
    assert k2["hh"].shape == (H // 2, W // 2) and k2["mask"].shape == k2["hh"].shape
    assert np.allclose(k2["x"], full["x"][: (W // 2) * 2].reshape(-1, 2).mean(1))
    assert np.allclose(k2["n_hh_raw"], full["n_hh_raw"][::2, ::2], rtol=1e-4)  # a flat noise floor stays flat


@needs_rasterio
def test_converted_read_equals_converting_the_whole_window_then_resampling(tmp_path, monkeypatch):
    from satmaps.cog import read_converted, read_window

    rng = np.random.default_rng(1)
    dn = rng.integers(0, 4000, (100, 100)).astype(np.uint16)
    dn[:10] = 0
    write_tif(tmp_path / "a.tif", [dn])
    canvas = AREA.canvas(30.0)  # three raster pixels per canvas pixel

    def convert(a):
        out = (a.astype(np.float32) ** 2) * 1e-6
        out[a == 0] = np.nan
        return out

    monkeypatch.setattr("satmaps.cog.STRIP_PX", 600)  # a few rows per strip
    raw, x, y, epsg, _ = read_window(str(tmp_path / "a.tif"), canvas)
    old = to_canvas(convert(raw), x, y, epsg, canvas, "bilinear")
    arr, xs, ys, ep, native = read_converted(str(tmp_path / "a.tif"), canvas, convert, "t")
    new = to_canvas(arr, xs, ys, ep, canvas, "bilinear")
    assert native == 10.0 and arr.shape[0] < raw.shape[0] / 2
    assert (np.isfinite(old) == np.isfinite(new)).all() and np.allclose(old, new, equal_nan=True)
    assert read_converted(str(tmp_path / "a.tif"), canvas, convert, "t", tmp_path / "cache")[0].shape == arr.shape  # and cached
    assert read_converted(str(tmp_path / "a.tif"), canvas, convert, "t", tmp_path / "cache")[4] == 10.0


@needs_rasterio
def test_a_canvas_as_fine_as_the_raster_is_read_whole(tmp_path):
    from satmaps.cog import read_converted

    write_tif(tmp_path / "a.tif", [np.full((100, 100), 7, np.uint16)])
    arr, x, *_ = read_converted(str(tmp_path / "a.tif"), AREA.canvas(10.0), lambda a: a.astype(np.float32), "id")
    assert x[1] - x[0] == 10.0 and (arr == 7).all()


@needs_rasterio
def test_nearest_read_of_a_mask_takes_every_kth_pixel(tmp_path):
    from satmaps.cog import read_window

    cls = np.arange(100 * 100, dtype=np.uint16).reshape(100, 100)
    write_tif(tmp_path / "m.tif", [cls])
    arr, x, y, *_ = read_window(str(tmp_path / "m.tif"), AREA.canvas(30.0), nearest=True)
    assert abs(x[1] - x[0] - 30.0) < 1e-9 and arr.size < cls.size / 4
    assert read_window(str(tmp_path / "m.tif"), AREA.canvas(10.0), nearest=True)[0].shape == (64, 64)  # as fine: whole window


def test_sentinel1_strips_equal_the_full_calibration_then_block_mean(monkeypatch):
    from rasterio.windows import Window

    rng = np.random.default_rng(2)
    dn = rng.integers(200, 900, (64, 80)).astype(np.uint16)
    dn[:, :6] = 0

    class Src:
        def read(self, _band, window: Window):
            return dn[window.row_off:window.row_off + window.height, window.col_off:window.col_off + window.width]

    cal = [(0.0, np.array([0.0, 79.0]), np.array([100.0, 100.0])), (63.0, np.array([0.0, 79.0]), np.array([100.0, 100.0]))]
    noise = [(0.0, np.array([0.0, 79.0]), np.array([1000.0, 1000.0])), (63.0, np.array([0.0, 79.0]), np.array([1000.0, 1000.0]))]
    monkeypatch.setattr(g, "STRIP", 3)
    s0, _ = g.sigma0(dn, 0, 0, cal, noise, [])
    coarse, share = g.sigma0_decimated(Src(), 0, 64, 0, 80, 4, cal, noise, [])
    assert coarse.shape == (16, 20)
    inner = coarse[:, 2:]  # block columns clear of the zero collar
    assert np.allclose(inner, _block_mean(s0, 4)[:, 2:], rtol=1e-5)
    assert (np.isnan(coarse[:, :1])).all() and 0 <= share < 1


@pytest.mark.parametrize("res, k", [(10.0, 1), (19.0, 2), (30.0, 3)])
def test_the_nisar_decimation_factor_is_the_whole_number_of_pixels_per_canvas_pixel(tmp_path, res, k):
    from satmaps.sensors.sar.nisar.canvas import decimation

    write_granule(tmp_path / "L.h5", "science/LSAR/GCOV", make_raw(), instrument="LSAR", freq_hz=1.239e9)
    area = Area(EPSG, X0 + 100, Y0 - 700, X0 + 700, Y0 - 100, res)
    assert decimation(tmp_path / "L.h5", "science/LSAR/GCOV", area.canvas(res)) == k
