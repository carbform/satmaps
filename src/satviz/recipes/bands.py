"""Single-band panels for multispectral figures: one band as a linear grey picture, with its stretch stated.

Reflectance is shown linearly (no gamma), so a grey level can be read back as a value from the printed limits. By default every
band shares one stretch, so panels side by side keep their real brightness ratios (vegetation bright in the near infrared and
dark in the red); `per-band` gives each its own limits, printed on its label, which shows structure better and hides the
spectral signature.
"""
from __future__ import annotations

import numpy as np

from satviz.core import BandInfo, Product

OUTSIDE_RGB = (7, 9, 14)  # no data: the same dark as the optical recipes
ROLE_ORDER = ("blue", "green", "red", "nir", "swir16", "swir22")


def bands_of(product: Product) -> tuple[BandInfo, ...]:
    """The product's spectral bands in wavelength order. A product with no band table (the catalogue readers) falls back to its
    colour roles, with no wavelengths: nothing is invented."""
    if product.bands:
        return tuple(b for b in product.bands if b.layer in product.layers)
    return tuple(BandInfo(id=role.upper(), layer=role, name=role) for role in ROLE_ORDER if role in product.layers)


def usable(product: Product) -> np.ndarray:
    """The pixels a stretch is set from: valid and, where the product maps cloud, not cloud. Clouds are still drawn (saturated),
    but they must not set the limits: with a few percent of cloud the upper percentile lands inside it and the land goes
    dark. When almost nothing is clear the cloud is kept in, rather than stretching on a handful of pixels."""
    ok = product.valid
    cloud = product.layers.get("cloud")
    if cloud is not None:
        clear = ok & (np.nan_to_num(cloud) < 0.5)
        if clear.sum() >= max(1000, 0.02 * ok.sum()):
            return clear
    return ok


STRETCH_NOTE = "Stretch set from the clear pixels; cloud is drawn saturated."


def cloud_left_out(product: Product, share: float = 0.01) -> bool:
    """True when `usable` left at least `share` of the view (cloud) out of the stretch, so the figure should say so. A few stray
    pixels do not change the stretch and are not worth a notice."""
    return bool(product.valid.sum() - usable(product).sum() >= share * max(int(product.valid.sum()), 1))


def limits(arrays: list[np.ndarray], valid: np.ndarray, plo: float = 2.0, phi: float = 98.0) -> tuple[float, float]:
    """Stretch limits: the plo-phi percentiles of the valid pixels of all `arrays` pooled."""
    vals = [a[::3, ::3][valid[::3, ::3] & np.isfinite(a[::3, ::3])] for a in arrays]
    pooled = np.concatenate(vals) if vals else np.array([])
    if pooled.size == 0:
        return 0.0, 1.0
    lo, hi = np.percentile(pooled, [plo, phi])
    return (float(lo), float(hi)) if hi > lo else (float(lo), float(lo) + 1e-6)


def grey_rgba(arr: np.ndarray, valid: np.ndarray, lo: float, hi: float) -> np.ndarray:
    ok = valid & np.isfinite(arr)
    g = np.clip((np.nan_to_num(arr) - lo) / (hi - lo), 0, 1)
    rgba = np.zeros(arr.shape + (4,), np.uint8)
    rgba[..., :3] = (g * 255).astype(np.uint8)[..., None]
    rgba[~ok, :3] = OUTSIDE_RGB
    rgba[..., 3] = 255
    return rgba


def wavelength_text(b: BandInfo) -> str:
    if b.wavelength_nm is not None:
        return f"{b.wavelength_nm:.0f} NM"
    if b.range_nm is not None:  # only a nominal range is known: show the range
        return f"{b.range_nm[0]:.0f}–{b.range_nm[1]:.0f} NM"
    return ""


def label_lines(b: BandInfo, lims: tuple[float, float] | None = None) -> str:
    """Chip text: the band id and common name, then centre wavelength (or nominal range), native pixel size and, for a per-band
    stretch, its limits. The native size keeps a 60 m panel from passing for 10 m detail."""
    first = f"{b.id} · {b.name}".upper() if b.name and b.name.upper() != b.id else b.id
    second = " · ".join(x for x in (wavelength_text(b), f"{b.resolution_m:g} M" if b.resolution_m else "") if x)
    lines = [first, second] if second else [first]
    if lims is not None:
        lines.append(f"{lims[0]:.2f}–{lims[1]:.2f}")
    return "\n".join(lines)
