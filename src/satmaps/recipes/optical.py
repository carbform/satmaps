"""Optical recipes: true colour, false-colour composites and two spectral indices.

They read surface-reflectance layers by role (`blue green red nir swir16 swir22`), so any optical sensor that provides
these works. Pixels with no data are drawn in the same dark as the SAR recipes; clouds are shown, not masked (the
product's caveat says how much there is).
"""
from __future__ import annotations

from functools import cache

import matplotlib
import numpy as np

from satmaps.core import RECIPES, LegendItem, Product, Recipe, Rendered, recipe
from satmaps.geo import utm_extent
from satmaps.recipes.bands import STRETCH_NOTE, cloud_left_out, usable

OUTSIDE_RGB = (7, 9, 14)
CHANNEL_HEX = ("#d4574f", "#5fb673", "#6580d6")
GAMMA = 0.85  # slight brightening; the stretch limits are printed, so the picture stays checkable


def _extent(p: Product):
    return utm_extent(dict(x=p.x, y=p.y))


def _finish(rgb01: np.ndarray, valid: np.ndarray) -> np.ndarray:
    rgba = np.zeros(valid.shape + (4,), np.uint8)
    rgba[..., :3] = np.nan_to_num(rgb01 * 255).astype(np.uint8)
    rgba[~valid, :3] = OUTSIDE_RGB
    rgba[..., 3] = 255
    return rgba


def _pooled_percentiles(products: list[Product], names: tuple[str, ...], plo=2.0, phi=98.0) -> tuple[float, float]:
    vals = []
    for p in products:
        a = np.stack([p.layers[n][::3, ::3] for n in names])
        ok = np.isfinite(a).all(axis=0) & usable(p)[::3, ::3]  # cloud is drawn, but does not set the limits
        vals.append(a[:, ok].ravel())
    lo, hi = np.percentile(np.concatenate(vals), [plo, phi])
    return float(lo), float(hi)


def _rgb_recipe(name: str, channels: tuple[str, str, str], title: str, texts: tuple[str, str, str]):
    def render(product: Product, lims_in: dict | None = None) -> Rendered:
        lo, hi = lims_in["RGB"] if lims_in else _pooled_percentiles([product], channels)
        stack = np.stack([product.layers[c] for c in channels], axis=-1)
        img = np.power(np.clip((stack - lo) / (hi - lo + 1e-9), 0, 1), GAMMA)
        legend = [LegendItem(c, t) for c, t in zip(CHANNEL_HEX, texts, strict=True)]
        roles = tuple(_role_of(c) for c in channels)
        if roles in OPTICAL_PRESET_LEGENDS:
            legend.extend(OPTICAL_PRESET_LEGENDS[roles])
        else:
            legend.append(LegendItem("noise", f"STRETCH {lo:.2f}–{hi:.2f} REFLECTANCE"))
        caveats = [*product.caveats, *([STRETCH_NOTE] if cloud_left_out(product) else [])]
        return Rendered(rgba=_finish(img, product.valid), extent=_extent(product), legend=legend[:6],
                        caveats=caveats, lims={"RGB": (lo, hi)}, title=title)

    def pooled(products: list[Product]) -> dict:
        return {"RGB": _pooled_percentiles(products, channels)}

    return recipe(name)(Recipe(render=render, kind="optical", needs=channels, shared_lims=pooled))


OPTICAL_ROLE_MAP = {
    "b01": "b01", "b02": "blue", "b03": "green", "b04": "red",
    "b05": "b05", "b06": "b06", "b07": "b07", "b08": "nir",
    "b8a": "nir", "b11": "swir16", "b12": "swir22",
}


def _role_of(c: str) -> str:
    return OPTICAL_ROLE_MAP.get(c.lower(), c.lower())


OPTICAL_PRESET_LEGENDS: dict[tuple[str, str, str], list[LegendItem]] = {
    ("red", "green", "blue"): [
        LegendItem("#2ca02c", "GREEN = VEGETATION & CROPS"),
        LegendItem("#1f77b4", "DARK BLUE = WATER BODIES"),
        LegendItem("#8c564b", "BROWN/GREY = SOIL & BUILT-UP"),
    ],
    ("nir", "red", "green"): [
        LegendItem("#d62728", "BRIGHT RED = HEALTHY VEGETATION"),
        LegendItem("#17becf", "CYAN = URBAN, ROADS, BARE SOIL"),
        LegendItem("#000000", "DARK = WATER BODIES"),
    ],
    ("swir16", "nir", "blue"): [
        LegendItem("#2ca02c", "BRIGHT GREEN = HEALTHY CROPS"),
        LegendItem("#e377c2", "MAGENTA/PINK = BARE SOIL / FALLOW"),
        LegendItem("#000000", "DARK = WATER & WETLANDS"),
    ],
    ("swir22", "nir", "red"): [
        LegendItem("#2ca02c", "GREEN = DENSE VEGETATION"),
        LegendItem("#d95f02", "ORANGE/BROWN = SOIL & BURN SCARS"),
        LegendItem("#08306b", "DARK BLUE = WATER & MOISTURE"),
    ],
    ("swir22", "swir16", "red"): [
        LegendItem("#17becf", "CYAN/GREY = BUILT STRUCTURES"),
        LegendItem("#8c564b", "BROWN = BARE GROUND & ROCK"),
        LegendItem("#1a1a2e", "DARK = VEGETATION & WATER"),
    ],
    ("swir22", "nir", "blue"): [
        LegendItem("#d95f02", "ORANGE/BROWN = ROCK & DRY SOIL"),
        LegendItem("#2ca02c", "GREEN = VEGETATION"),
        LegendItem("#08306b", "DEEP BLUE = WATER BODIES"),
    ],
}


TRUE_COLOUR = _rgb_recipe("true_colour", ("red", "green", "blue"), "TRUE COLOUR",
                          ("RED = RED BAND", "GREEN = GREEN BAND", "BLUE = BLUE BAND"))
NIR_FCC = _rgb_recipe("nir_fcc", ("nir", "red", "green"), "NIR FALSE COLOUR",
                      ("RED = NEAR-INFRARED (VEGETATION)", "GREEN = RED BAND", "BLUE = GREEN BAND"))
SWIR_FCC = _rgb_recipe("swir_fcc", ("swir22", "nir", "red"), "SWIR FALSE COLOUR",
                       ("RED = SHORTWAVE INFRARED", "GREEN = NEAR-INFRARED", "BLUE = RED BAND"))


PRESETS = {("red", "green", "blue"): "true_colour", ("nir", "red", "green"): "nir_fcc", ("swir22", "nir", "red"): "swir_fcc"}


def band_label(product: Product, layer: str) -> str:
    """'B08 NIR': a band's id and common name as the product states them; the layer name when it states none."""
    for b in product.bands:
        if b.layer == layer or (layer in product.layers and product.layers.get(b.layer) is product.layers[layer]):  # a role alias
            return f"{b.id} {b.name}".upper() if b.name and b.name.upper() != b.id.upper() else b.id.upper()
    return layer.upper()


def _fcc_recipe(channels: tuple[str, str, str]) -> Recipe:
    """A false-colour composite of any three bands (red, green, blue). Each band is stretched on its own: bands of different
    kinds (shortwave infrared, blue) have different ranges, and one shared stretch would crush the dimmer ones."""
    keys = ("R", "G", "B")

    def render(product: Product, lims_in: dict | None = None) -> Rendered:
        lims = {k: lims_in[k] if lims_in else _pooled_percentiles([product], (c,)) for k, c in zip(keys, channels, strict=True)}
        chans = [np.power(np.clip((product.layers[c] - lims[k][0]) / (lims[k][1] - lims[k][0] + 1e-9), 0, 1), GAMMA)
                 for k, c in zip(keys, channels, strict=True)]
        names = [band_label(product, c) for c in channels]
        legend = [LegendItem(hexed, f"{word} = {n}")
                  for hexed, word, n in zip(CHANNEL_HEX, ("RED", "GREEN", "BLUE"), names, strict=True)]
        roles = tuple(_role_of(c) for c in channels)
        if roles in OPTICAL_PRESET_LEGENDS:
            legend.extend(OPTICAL_PRESET_LEGENDS[roles])
        else:
            legend.append(LegendItem("noise", "EACH BAND STRETCHED ON ITS OWN (2–98%)"))
        caveats = [*product.caveats, *([STRETCH_NOTE] if cloud_left_out(product) else [])]
        title = "FCC  ·  " + " / ".join(n.split()[0] for n in names)
        return Rendered(rgba=_finish(np.stack(chans, axis=-1), product.valid), extent=_extent(product), legend=legend[:6],
                        caveats=caveats, lims=lims, title=title)

    def pooled(products: list[Product]) -> dict:
        return {k: _pooled_percentiles(products, (c,)) for k, c in zip(keys, channels, strict=True)}

    return Recipe(render=render, kind="optical", needs=tuple(dict.fromkeys(channels)), shared_lims=pooled)


@cache
def _fcc(spec: str) -> Recipe:
    channels = tuple(x.strip() for x in spec.split(","))
    if len(channels) != 3 or not all(channels):
        raise KeyError(f"recipe 'fcc:{spec}': give three band names for red, green and blue, e.g. fcc:nir,red,green")
    return RECIPES.get_or_raise(PRESETS[channels]) if channels in PRESETS else _fcc_recipe(channels)  # type: ignore[index]


RECIPES.factory("fcc")(_fcc)


def _index_recipe(name: str, title: str, fn, cmap: str, vmin: float, vmax: float, ends: tuple[str, str],
                  needs: tuple[str, ...]):
    cm = matplotlib.colormaps[cmap]

    def render(product: Product, lims_in: dict | None = None) -> Rendered:
        with np.errstate(divide="ignore", invalid="ignore"):
            v = fn(product.layers)
        ok = product.valid & np.isfinite(v)
        rgb = cm(np.clip((np.nan_to_num(v) - vmin) / (vmax - vmin), 0, 1))[..., :3]
        hexes = [matplotlib.colors.to_hex(cm(f)) for f in (0.05, 0.5, 0.95)]
        legend = [LegendItem(hexes[0], f"{ends[0]} ({vmin:g})"), LegendItem(hexes[1], f"MID ({(vmin + vmax) / 2:g})"),
                  LegendItem(hexes[2], f"{ends[1]} ({vmax:g})")]
        return Rendered(rgba=_finish(rgb, ok), extent=_extent(product), legend=legend,
                        caveats=list(product.caveats), lims={"index": (vmin, vmax)}, title=title)

    return recipe(name)(Recipe(render=render, kind="optical", needs=needs))


NDVI = _index_recipe("ndvi", "NDVI", lambda L: (L["nir"] - L["red"]) / (L["nir"] + L["red"]), "RdYlGn", -0.2, 0.9,
                     ("WATER OR BARE", "DENSE VEGETATION"), ("nir", "red"))
NDWI = _index_recipe("ndwi", "NDWI", lambda L: (L["green"] - L["nir"]) / (L["green"] + L["nir"]), "BrBG", -0.6, 0.6,
                     ("LAND", "OPEN WATER"), ("green", "nir"))
