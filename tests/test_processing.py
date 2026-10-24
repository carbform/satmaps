import numpy as np

from satviz.sensors.sar.nisar.processing import SNR_MIN_DB, coarsen, db, stats
from tests.conftest import ETA, NEBS_DB


def test_db_handles_zero_and_negative_without_warning():
    out = db(np.array([1.0, 10.0, 0.0, -1.0]))
    assert out[0] == 0.0 and np.isclose(out[1], 10.0)
    assert np.isneginf(out[2]) and np.isnan(out[3])


def test_noise_floor_is_nebs_divided_by_eta(ds):
    # NEBS is sigma0-referenced; the gamma0 floor is NEBS / eta = NEBS_DB - 10log10(eta)
    expected = NEBS_DB - 10 * np.log10(ETA)
    assert np.allclose(db(ds["n_hv"]), expected, atol=1e-4)
    assert np.allclose(db(ds["n_hv_raw"]), NEBS_DB, atol=1e-4)


def test_noise_flag_uses_the_3db_threshold(ds):
    snr = db(ds["hv"] / ds["n_hv"])
    assert np.array_equal(ds["noisy_hv"], ds["valid"] & (snr < SNR_MIN_DB))
    assert ds["noisy_hv"][100, 10]  # water block is below the floor
    assert not ds["noisy_hv"][10, 50]  # land is above it


def test_noise_subtracted_layers_are_nan_where_flagged(ds):
    assert np.isnan(ds["hv_ns"][ds["noisy_hv"]]).all()
    ok = ds["valid"] & ~ds["noisy_hv"]
    assert np.allclose(ds["hv_ns"][ok], (ds["hv"] - ds["n_hv"])[ok])


def test_coarsen_block_means_in_linear_power(ds):
    c = coarsen(ds, 3)
    assert c["hh"].shape == (ds["hh"].shape[0] // 3, ds["hh"].shape[1] // 3)
    assert np.isclose(c["hh"][0, 0], ds["hh"][:3, :3].mean(), rtol=1e-5)
    assert np.isclose(c["x"][0], ds["x"][:3].mean())


def test_coarsen_drops_ragged_edges(ds):
    c = coarsen(ds, 7)  # 120 x 110 is not a multiple of 7
    assert c["hh"].shape == (120 // 7, 110 // 7)


def test_stats_fractions_are_consistent(ds):
    s = stats(ds)
    assert 0 < s["noisy_hv_frac_of_valid"] < 1
    # dividing the floor by eta<1 raises it, so more pixels fall below than if the layer were already gamma0
    assert s["noisy_hv_frac_of_valid"] >= s["noisy_hv_frac_if_gamma_referenced"]
    assert s["valid_frac"] == 1.0 and s["exc64_frac_of_valid"] == 0.0
    assert np.isclose(s["eta_p1_p50_p99"][1], ETA, atol=1e-6)
