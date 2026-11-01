"""SAR false-colour composite (FCC): three quantities of the radar signal assigned to red, green and blue.

The quantities a co-/cross-polarised product offers are `co` (HH or VV), `cross` (HV or VH) and `ratio` (co/cross, a dB
difference). The default is R = co, G = cross, B = ratio. Any other assignment is a recipe name with the channels after a
colon: ``sar_fcc:cross,co,ratio`` is R = cross, G = co, B = ratio. A channel may repeat. Labels use the product's own
polarisation names (HH/HV, VV/VH, ...).

Stretch limits are kept per quantity under the keys ``HH``, ``HV`` and ``ratio`` (the co, cross and ratio quantity of any
polarisation pair), so layouts can print them as ``{lim.HH_lo}``.
"""
from __future__ import annotations

from functools import cache

import numpy as np

from satmaps.core import RECIPES, LegendItem, Product, Recipe, Rendered, recipe
from satmaps.geo import utm_extent
from satmaps.sensors.sar.nisar.processing import db

NOISE_RGB = (58, 58, 64)  # HV below the noise floor: neutral dark grey, never drawn as signal
OUTSIDE_RGB = (7, 9, 14)  # outside the valid-sample mask
ROLES = ("co", "cross", "ratio")
LIMS_KEY = {"co": "HH", "cross": "HV", "ratio": "ratio"}
GAMMA = {"co": 0.94, "cross": 0.94, "ratio": 1.05}
DEFAULT_CHANNELS = ("co", "cross", "ratio")
CHANNEL_COLORS = {"R": "#d4574f", "G": "#5fb673", "B": "#6580d6"}


def parse_channels(spec: str) -> tuple[str, str, str]:
    """'cross,co,ratio' -> ('cross', 'co', 'ratio'): three of co, cross, ratio, for red, green and blue."""
    parts = tuple(x.strip() for x in spec.split(","))
    if len(parts) != 3 or any(x not in ROLES for x in parts):
        raise KeyError(f"recipe 'sar_fcc:{spec}': give three of {', '.join(ROLES)} for red, green and blue, "
                       "e.g. sar_fcc:co,cross,ratio")
    return parts  # type: ignore[return-value]


def pol_names(product: Product) -> tuple[str, str]:
    """The product's co- and cross-polarised names ('HH', 'HV'); 'CO' and 'CROSS' when it does not say."""
    if product.native is not None and "pols" in product.native:
        return tuple(product.native["pols"])  # type: ignore[return-value]
    parts = (getattr(product.facts, "polarisations", "") or "").split("/")
    return (parts[0], parts[1]) if len(parts) >= 2 else ("CO", "CROSS")


def channel_name(role: str, pols: tuple[str, str]) -> str:
    return {"co": pols[0], "cross": pols[1], "ratio": f"{pols[0]}/{pols[1]}"}[role]


def _clean_mask(d: dict):
    """Pixels with a usable HV measurement: valid, SNR above threshold, positive after noise subtraction."""
    return d["valid"] & ~d["noisy_hv"] & np.isfinite(d["hv_ns"]) & (d["hv_ns"] > 0)


def _native_quantities(d: dict):
    ok = _clean_mask(d)
    co, cr = db(np.where(ok, d["hh"], np.nan)), db(d["hv_ns"])
    return ok, {"co": co, "cross": cr, "ratio": co - cr}


def _generic_quantities(product: Product):
    """Co/cross in dB for a SAR product with only `co` and `cross` layers (no noise floor, e.g. Sentinel-1 RTC)."""
    co, cr = product.layers["co"], product.layers["cross"]
    ok = product.valid & np.isfinite(co) & np.isfinite(cr) & (co > 0) & (cr > 0)
    co_db, cr_db = db(np.where(ok, co, np.nan)), db(np.where(ok, cr, np.nan))
    return ok, {"co": co_db, "cross": cr_db, "ratio": co_db - cr_db}


def _quantities(product: Product):
    return _native_quantities(product.native) if product.native is not None else _generic_quantities(product)


def _compose(q: dict, ok, bad, channels, lims_in, plo=2.0, phi=98.5):
    """(rgba, lims): each channel stretched between its quantity's limits; `bad` is [(mask, colour)] painted over the result."""
    lims, scaled = {}, {}
    for role in ROLES:
        a = q[role]
        lo, hi = lims_in[LIMS_KEY[role]] if lims_in else np.nanpercentile(a[::6, ::6], [plo, phi])
        lims[LIMS_KEY[role]] = (float(lo), float(hi))
        scaled[role] = np.power(np.clip((a - lo) / (hi - lo + 1e-6), 0, 1), GAMMA[role])
    rgba = np.zeros(q["co"].shape + (4,), np.uint8)
    for i, role in enumerate(channels):
        rgba[..., i] = np.nan_to_num(scaled[role] * 255).astype(np.uint8)
    for mask, colour in bad:
        rgba[mask, :3] = colour
    rgba[..., 3] = 255
    return rgba, lims


def fcc_rgba(d: dict, plo: float = 2.0, phi: float = 98.5, lims_in: dict | None = None, channels=DEFAULT_CHANNELS):
    """(rgba uint8, limits per quantity, clean mask) for a NISAR working dataset.

    Limits are the plo-phi percentiles of this dataset unless `lims_in` is given (e.g. pooled over two datasets with
    `shared_lims`, so the same colour means the same thing in both)."""
    ok, q = _native_quantities(d)
    rgba, lims = _compose(q, ok, [(~ok, NOISE_RGB), (~d["valid"], OUTSIDE_RGB)], channels, lims_in, plo, phi)
    return rgba, lims, ok


def shared_lims(ds: list[dict], plo: float = 2.0, phi: float = 98.5) -> dict:
    """Stretch limits pooled over several NISAR datasets, so colours are comparable between them."""
    return _pooled([_native_quantities(d)[1] for d in ds], plo, phi)


def _pooled(quantities: list[dict], plo: float = 2.0, phi: float = 98.5) -> dict:
    out = {}
    for role in ROLES:
        vals = []
        for q in quantities:
            a = q[role][::6, ::6]
            vals.append(a[np.isfinite(a)])
        out[LIMS_KEY[role]] = tuple(float(v) for v in np.percentile(np.concatenate(vals), [plo, phi]))
    return out


def pooled_lims(products: list[Product]) -> dict:
    """Stretch limits pooled over products (NISAR or any co/cross SAR product), 2nd to 98.5th percentile."""
    return _pooled([_quantities(p)[1] for p in products])


def _noise_or_water(native: bool, text: str = "DARK = CALM WATER / SMOOTH") -> LegendItem:
    return LegendItem("noise", "GREY = NOISE (SNR < 3 dB)") if native else LegendItem("#1a1a2e", text)


def default_legend(p1: str = "HH", p2: str = "HV", native: bool = True) -> list[LegendItem]:
    """How-to-read items for the default composite; layouts may replace them (e.g. to add the noise share)."""
    return [
        LegendItem("#d4574f", f"RED = {p1}  (SURFACE)"),
        LegendItem("#5fb673", f"GREEN = {p2}  (VOLUME)"),
        LegendItem("#6580d6", f"BLUE = {p1}/{p2}  (RATIO)"),
        LegendItem("#a05cb5", "PURPLE = HV LOW, SURFACE-LIKE"),
        LegendItem("#a8c25c", "LIME = HV HIGH, VOLUME-LIKE"),
        _noise_or_water(native),
    ]


def vegetation_legend(p1: str = "HH", p2: str = "HV", native: bool = True) -> list[LegendItem]:
    ratio = f"{p1}/{p2}"
    return [
        LegendItem("#d4574f", f"RED = {p2}  (CANOPY / VOLUME)"),
        LegendItem("#5fb673", f"GREEN = {p1}  (SURFACE / STRUCTURE)"),
        LegendItem("#6580d6", f"BLUE = {ratio}  (RATIO)"),
        LegendItem("#d95f02", "WARM / RED = DENSE VEGETATION"),
        LegendItem("#fdb863", "YELLOW = BUILT-UP / ROUGH GROUND"),
        _noise_or_water(native),
    ]


def urban_legend(p1: str = "HH", p2: str = "HV", native: bool = True) -> list[LegendItem]:
    ratio = f"{p1}/{p2}"
    return [
        LegendItem("#d4574f", f"RED = {p1}  (STRUCTURE / DOUBLE-BOUNCE)"),
        LegendItem("#5fb673", f"GREEN = {ratio}  (RATIO / CONTRAST)"),
        LegendItem("#6580d6", f"BLUE = {p2}  (CANOPY / VOLUME)"),
        LegendItem("#fdb863", "YELLOW / ORANGE = BUILT-UP URBAN"),
        LegendItem("#6580d6", "BLUE / CYAN = VEGETATION & CANOPY"),
        _noise_or_water(native, "DARK = CALM WATER BODIES"),
    ]


def water_legend(p1: str = "HH", p2: str = "HV", native: bool = True) -> list[LegendItem]:
    ratio = f"{p1}/{p2}"
    return [
        LegendItem("#d4574f", f"RED = {ratio}  (DEPOLARISATION RATIO)"),
        LegendItem("#5fb673", f"GREEN = {p1}  (SURFACE BACKSCATTER)"),
        LegendItem("#6580d6", f"BLUE = {p2}  (CANOPY / VOLUME)"),
        LegendItem("#d4574f", "RED = ROUGH / TEXTURED TERRAIN"),
        LegendItem("#5fb673", "CYAN = VEGETATED CANOPY"),
        _noise_or_water(native, "DARK = CALM OPEN WATER"),
    ]


def legend_for(channels, pols: tuple[str, str], native: bool) -> list[LegendItem]:
    """The legend of a composite: presets include color interpretation; custom assignments say what is where."""
    ch = tuple(channels)
    if ch == DEFAULT_CHANNELS:
        return default_legend(*pols, native=native)
    if ch == ("cross", "co", "ratio"):
        return vegetation_legend(*pols, native=native)
    if ch == ("co", "ratio", "cross"):
        return urban_legend(*pols, native=native)
    if ch == ("ratio", "co", "cross"):
        return water_legend(*pols, native=native)
    items = [LegendItem(CHANNEL_COLORS[k], f"{n} = {channel_name(r, pols)}")
             for k, n, r in zip("RGB", ("RED", "GREEN", "BLUE"), channels, strict=True)]
    return [*items, LegendItem("noise", "GREY = NOISE (SNR < 3 dB)")] if native else items


def render_product(product: Product, lims_in: dict | None = None, channels=DEFAULT_CHANNELS) -> Rendered:
    """A co-/cross-polarised SAR product to a `Rendered` false-colour composite."""
    d = product.native
    if d is not None and "s2" in d:
        raise ValueError("recipe 'sar_fcc' is for products with a co- and a cross-polarised channel (HH+HV, VV+VH); this one "
                         "is compact-pol (RH+RV): use recipe 'sar_compact'")
    pols = pol_names(product)
    if d is None:
        ok, q = _generic_quantities(product)
        rgba, lims = _compose(q, ok, [(~ok, OUTSIDE_RGB)], channels, lims_in)
        caveats = list(product.caveats)
    else:
        rgba, lims, _ = fcc_rgba(d, lims_in=lims_in, channels=channels)
        caveats = [*product.caveats, "NISAR: noise-screened (SNR < 3 dB shown grey); no speckle filter."]
    title = "FCC  ·  " + " / ".join(channel_name(r, pols) for r in channels)
    extent = utm_extent(d) if d is not None else utm_extent(dict(x=product.x, y=product.y))
    return Rendered(rgba=rgba, extent=extent, legend=legend_for(channels, pols, d is not None), caveats=caveats, lims=lims,
                    title=title)


SAR_FCC = recipe("sar_fcc")(Recipe(render=render_product, kind="sar", shared_lims=pooled_lims))


@cache
def _custom(spec: str) -> Recipe:
    channels = parse_channels(spec)
    return Recipe(render=lambda product, lims_in=None: render_product(product, lims_in, channels), kind="sar",
                  shared_lims=pooled_lims)


RECIPES.factory("sar_fcc")(_custom)
