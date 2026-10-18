#!/usr/bin/env python3
"""Shared S-band GCOV processing for the Brahmaputra graphics.

Applies the corrections listed in NISAR_SBand_GCOV_correction_assessment.md on top of the
product and returns display-ready layers for the social and publication renderers.
"""
import os
import numpy as np
import h5py
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator

HERE = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(HERE, "NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5")
FILE_PATH_L = os.path.join(HERE, "NISAR_L2_PR_GCOV_031_112_A_016_4005_DHDH_A_20260925T225740_20260925T225815_P05023_N_F_J_001.h5")
# Same 10 m UTM 46N grid in both bands; the L-band file is offset by (+360 rows, +72 cols), so the ROI
# is the identical ground footprint (checked: 0 m offset in x and y).
BANDS = {
    "S": dict(path=FILE_PATH, base="science/SSAR/GCOV", rows=(27800, 30880), cols=(11500, 14400)),
    "L": dict(path=FILE_PATH_L, base="science/LSAR/GCOV", rows=(28160, 31240), cols=(11572, 14472)),
}

# Braided reach with Simen confluence, sand bars and Dibrugarh; 100 % valid in the mask.
ROW0, ROW1 = 27800, 30880
COL0, COL1 = 11500, 14400

SNR_MIN_DB = 3.0  # cross-pol pixels below this are flagged as noise-dominated


def db(a):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(a)


def load_roi(band="S"):
    b = BANDS[band]
    (r0, r1), (c0, c1) = b["rows"], b["cols"]
    with h5py.File(b["path"], "r") as f:
        g = f[f"{b['base']}/grids/frequencyA"]
        sl = (slice(r0, r1), slice(c0, c1))
        x = g["xCoordinates"][c0:c1]
        y = g["yCoordinates"][r0:r1]
        epsg = int(g["projection"][()])
        hh = g["HHHH"][sl].astype(np.float32)
        hv = g["HVHV"][sl].astype(np.float32)
        mask = g["mask"][sl]
        exc = g["inputDataExceptionMask"][sl]
        eta = g["rtcGammaToSigmaFactor"][sl].astype(np.float32)
        nb = f[f"{b['base']}/metadata/calibrationInformation/frequencyA/noiseEquivalentBackscatter"]
        nx, ny = nb["xCoordinates"][:], nb["yCoordinates"][:]
        nhh, nhv = nb["HH"][:].astype(np.float64), nb["HV"][:].astype(np.float64)

    def interp(grid):
        # NEBS y is descending; RegularGridInterpolator needs ascending axes.
        yy, gg = (ny[::-1], grid[::-1]) if ny[0] > ny[-1] else (ny, grid)
        fn = RegularGridInterpolator((yy, nx), gg, bounds_error=False, fill_value=None)
        Y, X = np.meshgrid(y, x, indexing="ij")
        return fn(np.stack([Y.ravel(), X.ravel()], -1)).reshape(Y.shape).astype(np.float32)

    n_hh_raw, n_hv_raw = interp(nhh), interp(nhv)
    # ISRO format doc (SAC-PR-NISAR-2024-051, 7.3.6.1) describes this layer as noise-equivalent sigma0.
    # Our covariance terms are gamma0, and sigma0 = eta * gamma0, so the gamma0-referenced floor is NEBS / eta.
    with np.errstate(divide="ignore", invalid="ignore"):
        n_hh, n_hv = n_hh_raw / eta, n_hv_raw / eta

    valid = (mask >= 1) & (mask <= 5) & np.isfinite(hh) & np.isfinite(hv) & (hh > 0) & (hv > 0)
    t = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    d = dict(band=band, x=x, y=y, epsg=epsg, hh=hh, hv=hv, mask=mask, exc=exc, eta=eta, n_hh=n_hh, n_hv=n_hv, n_hh_raw=n_hh_raw, n_hv_raw=n_hv_raw,
             valid=valid, to_ll=t, to_utm=Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True))
    return derive(d)


def derive(d):
    """SNR, noise flags and noise-subtracted layers from hh/hv/n_hh/n_hv/valid."""
    valid = d["valid"]
    d["snr_hh"] = db(d["hh"] / d["n_hh"])
    d["snr_hv"] = db(d["hv"] / d["n_hv"])
    d["noisy_hh"] = valid & (d["snr_hh"] < SNR_MIN_DB)
    d["noisy_hv"] = valid & (d["snr_hv"] < SNR_MIN_DB)
    # Noise-subtracted layers where SNR allows it; elsewhere NaN (flagged, not interpreted).
    d["hv_ns"] = np.where(valid & ~d["noisy_hv"], d["hv"] - d["n_hv"], np.nan).astype(np.float32)
    d["hh_ns"] = np.where(valid & ~d["noisy_hh"], d["hh"] - d["n_hh"], np.nan).astype(np.float32)
    return d


def coarsen(d, k=3):
    """Block-mean k x k in linear power (display only; raises ENL by k^2)."""
    H, W = (d["hh"].shape[0] // k) * k, (d["hh"].shape[1] // k) * k

    def bm(a):
        return a[:H, :W].reshape(H // k, k, W // k, k).mean(axis=(1, 3)).astype(np.float32)

    c = dict(d)
    for key in ("hh", "hv", "n_hh", "n_hv", "n_hh_raw", "n_hv_raw", "eta"):
        c[key] = bm(d[key])
    c["valid"] = d["valid"][:H, :W].reshape(H // k, k, W // k, k).all(axis=(1, 3))
    c["x"] = d["x"][:W].reshape(-1, k).mean(1)
    c["y"] = d["y"][:H].reshape(-1, k).mean(1)
    c["exc"] = d["exc"][:H:k, :W:k]
    return derive(c)


def fcc_rgba(d, plo=2.0, phi=98.5, lims_in=None):
    """R = HH γ0 dB, G = HV γ0 dB (noise-subtracted), B = HH/HV ratio dB.

    Pixels with HV below the noise floor are drawn in a neutral dark grey, not as signal,
    so "dark" in the image means low backscatter that is actually measured.
    """
    ok = d["valid"] & ~d["noisy_hv"] & np.isfinite(d["hv_ns"]) & (d["hv_ns"] > 0)
    hh = np.where(ok, d["hh"], np.nan)
    co, cr = db(hh), db(d["hv_ns"])
    rt = co - cr
    lims = {}
    chans = []
    for name, a, gam in (("HH", co, 0.94), ("HV", cr, 0.94), ("ratio", rt, 1.05)):
        lo, hi = lims_in[name] if lims_in else np.nanpercentile(a[::6, ::6], [plo, phi])
        lims[name] = (float(lo), float(hi))
        chans.append(np.power(np.clip((a - lo) / (hi - lo + 1e-6), 0, 1), gam))
    rgba = np.zeros(co.shape + (4,), np.uint8)
    for i, c in enumerate(chans):
        rgba[..., i] = np.nan_to_num(c * 255).astype(np.uint8)
    rgba[~ok, :3] = (58, 58, 64)          # noise-dominated / invalid: neutral grey
    rgba[~d["valid"], :3] = (7, 9, 14)    # outside the valid mask
    rgba[..., 3] = 255
    return rgba, lims, ok


def shared_lims(ds, plo=2.0, phi=98.5):
    """Pooled FCC stretch limits over several datasets, so colours are comparable between bands."""
    out = {}
    for name in ("HH", "HV", "ratio"):
        vals = []
        for d in ds:
            ok = d["valid"] & ~d["noisy_hv"] & np.isfinite(d["hv_ns"]) & (d["hv_ns"] > 0)
            co, cr = db(np.where(ok, d["hh"], np.nan)), db(d["hv_ns"])
            a = {"HH": co, "HV": cr, "ratio": co - cr}[name]
            vals.append(a[::6, ::6][np.isfinite(a[::6, ::6])])
        out[name] = tuple(float(v) for v in np.percentile(np.concatenate(vals), [plo, phi]))
    return out


def valid_noisy_raw(d):
    return d["valid"] & (db(d["hv"] / d["n_hv_raw"]) < SNR_MIN_DB)


def stats(d):
    v = d["valid"]
    return {
        "roi_pixels": int(v.size),
        "valid_frac": float(v.mean()),
        "noisy_hv_frac_of_valid": float(d["noisy_hv"].sum() / v.sum()),
        "noisy_hv_frac_if_gamma_referenced": float((valid_noisy_raw(d)).sum() / v.sum()),
        "exc64_frac_of_valid": float(((d["exc"] == 64) & v).sum() / v.sum()),
        "eta_p1_p50_p99": [float(x) for x in np.nanpercentile(d["eta"][v], [1, 50, 99])],
        "nebs_hv_db_median": float(np.nanmedian(db(d["n_hv_raw"]))),
        "noise_floor_gamma0_db_median": float(np.nanmedian(db(d["n_hv"]))),
        "hh_db_p2_p50_p98": [float(x) for x in np.nanpercentile(db(d["hh"][v]), [2, 50, 98])],
        "hv_db_p2_p50_p98": [float(x) for x in np.nanpercentile(db(d["hv"][v]), [2, 50, 98])],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(stats(load_roi()), indent=1))
