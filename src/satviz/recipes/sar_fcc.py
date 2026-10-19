"""False-colour composite: R = HH gamma0 (dB), G = HV gamma0 noise-subtracted (dB), B = HH-HV ratio (dB)."""
from __future__ import annotations

import numpy as np

from satviz.core import Component, LegendItem, Product, Recipe, Rendered, recipe
from satviz.geo import utm_extent
from satviz.sensors.nisar_gcov.processing import coarsen, db

NOISE_RGB = (58, 58, 64)  # HV below the noise floor: neutral dark grey, never drawn as signal
OUTSIDE_RGB = (7, 9, 14)  # outside the valid-sample mask
GAMMAS = (("HH", 0.94), ("HV", 0.94), ("ratio", 1.05))


def _clean_mask(d: dict):
    """Pixels with a usable HV measurement: valid, SNR above threshold, positive after noise subtraction."""
    return d["valid"] & ~d["noisy_hv"] & np.isfinite(d["hv_ns"]) & (d["hv_ns"] > 0)


def _channels_db(d: dict):
    ok = _clean_mask(d)
    co, cr = db(np.where(ok, d["hh"], np.nan)), db(d["hv_ns"])
    return ok, {"HH": co, "HV": cr, "ratio": co - cr}


def fcc_rgba(d: dict, plo: float = 2.0, phi: float = 98.5, lims_in: dict | None = None):
    """Return (rgba uint8, limits used per channel, clean mask).

    Limits are the plo-phi percentiles of this dataset unless `lims_in` is given (e.g. pooled over two bands
    with `shared_lims`, so the same colour means the same thing in both).
    """
    ok, ch = _channels_db(d)
    lims, chans = {}, []
    for name, gam in GAMMAS:
        a = ch[name]
        lo, hi = lims_in[name] if lims_in else np.nanpercentile(a[::6, ::6], [plo, phi])
        lims[name] = (float(lo), float(hi))
        chans.append(np.power(np.clip((a - lo) / (hi - lo + 1e-6), 0, 1), gam))
    rgba = np.zeros(ch["HH"].shape + (4,), np.uint8)
    for i, c in enumerate(chans):
        rgba[..., i] = np.nan_to_num(c * 255).astype(np.uint8)
    rgba[~ok, :3] = NOISE_RGB
    rgba[~d["valid"], :3] = OUTSIDE_RGB
    rgba[..., 3] = 255
    return rgba, lims, ok


def shared_lims(ds: list[dict], plo: float = 2.0, phi: float = 98.5) -> dict:
    """Stretch limits pooled over several datasets, so colours are comparable between bands."""
    out = {}
    for name, _ in GAMMAS:
        vals = []
        for d in ds:
            a = _channels_db(d)[1][name][::6, ::6]
            vals.append(a[np.isfinite(a)])
        out[name] = tuple(float(v) for v in np.percentile(np.concatenate(vals), [plo, phi]))
    return out


CHANNEL_COLORS = {"R": "#d4574f", "G": "#5fb673", "B": "#6580d6"}


def channel_panels(d: dict, lims: dict) -> list[tuple[str, np.ndarray]]:
    """The three composite inputs as separate images, each tinted in its channel colour.

    Returns [("R", img), ("G", img), ("B", img)] of float RGB in 0..1; noise-dominated pixels stay dark in every panel.
    """
    hh_db, hv_db = db(d["hh"]), db(d["hv_ns"])
    okc = d["valid"] & ~d["noisy_hv"] & np.isfinite(hv_db)
    arrays = {"HH": hh_db, "HV": hv_db, "ratio": hh_db - hv_db}
    out = []
    for (name, gam), key in zip(GAMMAS, "RGB", strict=True):
        lo, hi = lims[name]
        v = np.where(okc, np.power(np.clip((arrays[name] - lo) / (hi - lo), 0, 1), gam), np.nan)
        tint = np.array([int(CHANNEL_COLORS[key][k:k + 2], 16) for k in (1, 3, 5)]) / 255.0
        out.append((key, np.where(np.isfinite(v)[..., None], v[..., None] * tint, 0.12)))
    return out


def default_legend() -> list[LegendItem]:
    """How-to-read items for the composite; layouts may replace them (e.g. to add the noise share)."""
    return [
        LegendItem("#d4574f", "RED = HH  (SURFACE)"),
        LegendItem("#5fb673", "GREEN = HV  (VOLUME)"),
        LegendItem("#6580d6", "BLUE = HH−HV  (RATIO)"),
        LegendItem("#a05cb5", "PURPLE = HV LOW, SURFACE-LIKE"),
        LegendItem("#a8c25c", "LIME = HV HIGH, VOLUME-LIKE"),
        LegendItem("noise", "GREY = NOISE (SNR < 3 dB)"),
    ]


def render_product(product: Product, lims_in: dict | None = None) -> Rendered:
    """A NISAR product to a `Rendered` false-colour composite, with the three channels as components."""
    d = product.native
    rgba, lims, _ = fcc_rgba(d, lims_in=lims_in)
    c = coarsen(d, 4)
    labels = {"R": "CH1  HH", "G": "CH2  HV", "B": "CH3  HH−HV"}
    comps = [Component(key, img, CHANNEL_COLORS[key], labels[key]) for key, img in channel_panels(c, lims)]
    return Rendered(rgba=rgba, extent=utm_extent(d), legend=default_legend(),
                    caveats=[*product.caveats, "Noise-screened (SNR < 3 dB shown grey); no speckle filter applied."],
                    components=comps, components_extent=utm_extent(c), lims=lims, title="R+G+B  COMPOSITE")


def pooled_lims(products: list[Product]) -> dict:
    return shared_lims([p.native for p in products])


SAR_FCC = recipe("sar_fcc")(Recipe(render=render_product, kind="sar", shared_lims=pooled_lims))
