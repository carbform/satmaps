import numpy as np
import pytest

from satmaps.sensors.sar.nisar.io import load_roi, read_roi
from tests.conftest import NEBS_DB, H, W


def test_read_roi_shapes_and_interpolated_noise(scene):
    raw = read_roi(scene.band_path("S"), scene.bands["S"])
    assert raw["hh"].shape == (H, W) and raw["n_hv_raw"].shape == (H, W)
    assert np.allclose(10 * np.log10(raw["n_hv_raw"]), NEBS_DB, atol=1e-3)  # flat NEBS survives the descending-y interpolation


def test_roi_window_is_applied(scene):
    from dataclasses import replace

    spec = replace(scene.bands["S"], rows=(10, 40), cols=(20, 50))
    raw = read_roi(scene.band_path("S"), spec)
    assert raw["hh"].shape == (30, 30) and raw["x"][0] == 500000.0 + 200


def test_missing_granule_message_mentions_data_dir(scene, tmp_path):
    from dataclasses import replace

    with pytest.raises(FileNotFoundError, match="NISAR_DATA_DIR"):
        load_roi(replace(scene, data_dir=tmp_path / "nowhere"), "S")


def test_cache_roundtrip_and_invalidation(scene, tmp_path, caplog):
    cache = tmp_path / "cache"
    a = load_roi(scene, "S", cache)
    files = list(cache.glob("*.npz"))
    assert len(files) == 1
    caplog.set_level("INFO")
    b = load_roi(scene, "S", cache)  # served from cache
    assert any("cache hit" in m for m in caplog.messages)
    caplog.clear()
    assert np.array_equal(a["hh"], b["hh"]) and np.array_equal(a["noisy_hv"], b["noisy_hv"])
    # touching the source file must invalidate the cache entry
    p = scene.band_path("S")
    p.write_bytes(p.read_bytes() + b"\0")
    import os

    os.utime(p, ns=(1, 1))
    c = load_roi(scene, "S", cache)
    assert not any("cache hit" in m for m in caplog.messages)  # re-read from the HDF5
    assert np.array_equal(a["hh"], c["hh"])
