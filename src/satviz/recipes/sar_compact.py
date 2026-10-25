"""Compact-polarisation composite: the m-chi decomposition of a circular-transmit (RH, RV) NISAR product.

The product holds RHRH and RVRV (powers) and RHRV (complex), from which the Stokes vector follows (S0 = RH + RV, S1 = RH - RV,
S2 = 2 Re RHRV, S3 = -2 Im RHRV, with the noise floor taken off the two powers first). The degree of polarisation m and the
ellipticity chi (sin 2chi = -S3 / (m S0)) split the power S0 into three mechanisms (Raney 2007; Raney et al. 2012):

    RED   double bounce  m S0 (1 - sin 2chi) / 2     (buildings, flooded forest, trunks)
    GREEN volume         S0 (1 - m)                  (canopy: depolarised)
    BLUE  surface        m S0 (1 + sin 2chi) / 2     (water, bare ground: an odd number of bounces)

This is the radar-appropriate composite for such a product. The linear HH/HV composite (`sar_fcc`) does not apply to it: a
circular transmit has no HH or HV.
"""
from __future__ import annotations

import numpy as np

from satviz.core import Component, LegendItem, Product, Recipe, Rendered, recipe
from satviz.geo import utm_extent
from satviz.recipes.sar_fcc import CHANNEL_COLORS, NOISE_RGB, OUTSIDE_RGB
from satviz.sensors.sar.nisar.processing import coarsen, db

CHANNELS = (("DBL", "R"), ("VOL", "G"), ("ODD", "B"))
GAMMA = 0.94
# The sign of S3 (-2 Im RHRV as read) that the product's convention needs. It is set from known ground, not from a formula: on the
# 005 frame (Mangaluru coast) with -1, the smooth low-power returns are 86% surface (blue) and the brightest polarised returns 66%
# double bounce (red); with +1 both flip. A formula's sign depends on the file's conjugation convention: recheck on a new type.
S3_SIGN = -1.0


def decompose(d: dict) -> tuple[np.ndarray, dict]:
    """(clean mask, {"DBL", "VOL", "ODD": power}) from a working dataset: hh and hv hold RHRH and RVRV, s2 and s3 the Stokes parts
    of RHRV. Pixels at the noise floor in either channel are not interpreted."""
    ok = d["valid"] & ~d["noisy_hh"] & ~d["noisy_hv"] & np.isfinite(d["hh_ns"]) & np.isfinite(d["hv_ns"])
    a, b = np.where(ok, d["hh_ns"], np.nan), np.where(ok, d["hv_ns"], np.nan)
    ok &= (a > 0) & (b > 0)
    s0, s1, s2, s3 = a + b, a - b, d["s2"], S3_SIGN * d["s3"]
    with np.errstate(divide="ignore", invalid="ignore"):
        m = np.clip(np.sqrt(s1 ** 2 + s2 ** 2 + s3 ** 2) / s0, 0, 1)
        sin2chi = np.nan_to_num(np.clip(-s3 / (m * s0), -1, 1))  # (no polarised part: no ellipticity, and no bounce power)
        out = {"DBL": m * s0 * (1 - sin2chi) / 2, "VOL": s0 * (1 - m), "ODD": m * s0 * (1 + sin2chi) / 2}
    return ok, out


def _db(a):
    return db(np.where(a > 0, a, np.nan))


def rgba_of(d: dict, lims_in: dict | None = None):
    """(rgba, limits per channel, clean mask): a 2nd to 98.5th percentile stretch of each mechanism in dB."""
    ok, ch = decompose(d)
    lims, rgba = {}, np.zeros(ok.shape + (4,), np.uint8)
    for i, (name, _) in enumerate(CHANNELS):
        a = _db(ch[name])
        lo, hi = lims_in[name] if lims_in else np.nanpercentile(a[ok][::7] if ok.any() else [0, 1], [2.0, 98.5])
        lims[name] = (float(lo), float(hi))
        rgba[..., i] = np.nan_to_num(np.power(np.clip((a - lo) / (hi - lo + 1e-6), 0, 1), GAMMA) * 255).astype(np.uint8)
    rgba[~ok, :3] = NOISE_RGB
    rgba[~d["valid"], :3] = OUTSIDE_RGB
    rgba[..., 3] = 255
    return rgba, lims, ok


def _components(c: dict, lims: dict) -> list[Component]:
    ok, ch = decompose(c)
    comps = []
    for (name, key), label in zip(CHANNELS, ("CH1  DOUBLE BOUNCE", "CH2  VOLUME", "CH3  SURFACE"), strict=True):
        lo, hi = lims[name]
        v = np.where(ok, np.power(np.clip((_db(ch[name]) - lo) / (hi - lo + 1e-6), 0, 1), GAMMA), np.nan)
        tint = np.array([int(CHANNEL_COLORS[key][q:q + 2], 16) for q in (1, 3, 5)]) / 255.0
        comps.append(Component(key, np.where(np.isfinite(v)[..., None], v[..., None] * tint, 0.12), CHANNEL_COLORS[key], label))
    return comps


def legend() -> list[LegendItem]:
    return [LegendItem("#d4574f", "RED = DOUBLE BOUNCE  (BUILDINGS, TRUNKS)"), LegendItem("#5fb673", "GREEN = VOLUME  (CANOPY)"),
            LegendItem("#6580d6", "BLUE = SURFACE  (WATER, BARE GROUND)"), LegendItem("noise", "GREY = NOISE (SNR < 3 dB)")]


def render_product(product: Product, lims_in: dict | None = None) -> Rendered:
    d = product.native
    rgba, lims, _ = rgba_of(d, lims_in)
    c = coarsen(d, 4)
    return Rendered(
        rgba=rgba, extent=utm_extent(d), legend=legend(),
        caveats=[*product.caveats, "NISAR compact-pol (RH + RV): m-chi decomposition, noise-screened (SNR < 3 dB shown grey); "
                                   "no speckle filter; hues drifting across a swath are RH/RV channel imbalance."],
        components=_components(c, lims), components_extent=utm_extent(c), lims=lims, title="m-χ  COMPOSITE")


def pooled_lims(products: list[Product]) -> dict:
    out = {}
    for name, _ in CHANNELS:
        vals = []
        for p in products:
            ok, ch = decompose(p.native)
            a = _db(ch[name])[ok][::7]
            vals.append(a[np.isfinite(a)])
        out[name] = tuple(float(v) for v in np.percentile(np.concatenate(vals), [2.0, 98.5]))
    return out


SAR_COMPACT = recipe("sar_compact")(Recipe(render=render_product, kind="sar", needs=("s2", "s3"), shared_lims=pooled_lims))
