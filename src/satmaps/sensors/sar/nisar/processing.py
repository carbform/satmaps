"""Radiometric screening of GCOV covariance terms: noise floor, SNR flags and block averaging.

All arrays are linear power (gamma0). `d` is a dict of ROI layers as built by `satmaps.sensors.sar.nisar.io.assemble`.
"""
from __future__ import annotations

import numpy as np

SNR_MIN_DB = 3.0  # cross-pol pixels below this are flagged as noise-dominated


def db(a):
    """10*log10 without warnings for zeros and negatives (they become -inf / nan)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(a)


def derive(d: dict) -> dict:
    """SNR, noise flags and noise-subtracted layers from hh/hv/n_hh/n_hv/valid. Updates `d` in place."""
    valid = d["valid"]
    d["snr_hh"] = db(d["hh"] / d["n_hh"])
    d["snr_hv"] = db(d["hv"] / d["n_hv"])
    d["noisy_hh"] = valid & (d["snr_hh"] < SNR_MIN_DB)
    d["noisy_hv"] = valid & (d["snr_hv"] < SNR_MIN_DB)
    # Noise-subtracted layers where SNR allows it; elsewhere NaN (flagged, not interpreted).
    d["hv_ns"] = np.where(valid & ~d["noisy_hv"], d["hv"] - d["n_hv"], np.nan).astype(np.float32)
    d["hh_ns"] = np.where(valid & ~d["noisy_hh"], d["hh"] - d["n_hh"], np.nan).astype(np.float32)
    return d


def coarsen(d: dict, k: int = 3) -> dict:
    """Block-mean k x k in linear power (display only; raises the equivalent number of looks by k^2)."""
    H, W = (d["hh"].shape[0] // k) * k, (d["hh"].shape[1] // k) * k

    def bm(a):
        return a[:H, :W].reshape(H // k, k, W // k, k).mean(axis=(1, 3)).astype(np.float32)

    c = dict(d)
    for key in ("hh", "hv", "n_hh", "n_hv", "n_hh_raw", "n_hv_raw", "eta", "s2", "s3"):
        if key in d:
            c[key] = bm(d[key])
    c["valid"] = d["valid"][:H, :W].reshape(H // k, k, W // k, k).all(axis=(1, 3))
    c["x"] = d["x"][:W].reshape(-1, k).mean(1)
    c["y"] = d["y"][:H].reshape(-1, k).mean(1)
    c["exc"] = d["exc"][:H:k, :W:k]
    return derive(c)


def valid_noisy_raw(d: dict):
    """HV noise flag if the noise layer were already gamma0-referenced (i.e. not divided by eta)."""
    return d["valid"] & (db(d["hv"] / d["n_hv_raw"]) < SNR_MIN_DB)


def stats(d: dict) -> dict:
    """Summary numbers quoted on the figures and in the notes."""
    v = d["valid"]
    return {
        "roi_pixels": int(v.size),
        "valid_frac": float(v.mean()),
        "noisy_hv_frac_of_valid": float(d["noisy_hv"].sum() / v.sum()),
        "noisy_hv_frac_if_gamma_referenced": float(valid_noisy_raw(d).sum() / v.sum()),
        "exc64_frac_of_valid": float(((d["exc"] == 64) & v).sum() / v.sum()),
        "eta_p1_p50_p99": [float(x) for x in np.nanpercentile(d["eta"][v], [1, 50, 99])],
        "nebs_hv_db_median": float(np.nanmedian(db(d["n_hv_raw"]))),
        "noise_floor_gamma0_db_median": float(np.nanmedian(db(d["n_hv"]))),
        "hh_db_p2_p50_p98": [float(x) for x in np.nanpercentile(db(d["hh"][v]), [2, 50, 98])],
        "hv_db_p2_p50_p98": [float(x) for x in np.nanpercentile(db(d["hv"][v]), [2, 50, 98])],
    }
