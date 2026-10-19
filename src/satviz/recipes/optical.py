"""Optical recipes: true colour, false-colour composites and two spectral indices.

They read surface-reflectance layers by role (`blue green red nir swir16 swir22`), so any optical sensor that provides
these works. Pixels with no data are drawn in the same dark as the SAR recipes; clouds are shown, not masked (the
product's caveat says how much there is).
"""
from __future__ import annotations

import matplotlib
import numpy as np

from satviz.core import LegendItem, Product, Recipe, Rendered, recipe
from satviz.geo import utm_extent

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
        ok = np.isfinite(a).all(axis=0) & p.valid[::3, ::3]
        vals.append(a[:, ok].ravel())
    lo, hi = np.percentile(np.concatenate(vals), [plo, phi])
    return float(lo), float(hi)


def _rgb_recipe(name: str, channels: tuple[str, str, str], title: str, texts: tuple[str, str, str]):
    def render(product: Product, lims_in: dict | None = None) -> Rendered:
        lo, hi = lims_in["RGB"] if lims_in else _pooled_percentiles([product], channels)
        stack = np.stack([product.layers[c] for c in channels], axis=-1)
        img = np.power(np.clip((stack - lo) / (hi - lo + 1e-9), 0, 1), GAMMA)
        legend = [LegendItem(c, t) for c, t in zip(CHANNEL_HEX, texts, strict=True)]
        legend.append(LegendItem("noise", f"STRETCH {lo:.2f}–{hi:.2f} REFLECTANCE"))
        return Rendered(rgba=_finish(img, product.valid), extent=_extent(product), legend=legend,
                        caveats=list(product.caveats), lims={"RGB": (lo, hi)}, title=title)

    def pooled(products: list[Product]) -> dict:
        return {"RGB": _pooled_percentiles(products, channels)}

    return recipe(name)(Recipe(render=render, kind="optical", shared_lims=pooled))


TRUE_COLOUR = _rgb_recipe("true_colour", ("red", "green", "blue"), "TRUE COLOUR",
                          ("RED = RED BAND", "GREEN = GREEN BAND", "BLUE = BLUE BAND"))
NIR_FCC = _rgb_recipe("nir_fcc", ("nir", "red", "green"), "NIR FALSE COLOUR",
                      ("RED = NEAR-INFRARED (VEGETATION)", "GREEN = RED BAND", "BLUE = GREEN BAND"))
SWIR_FCC = _rgb_recipe("swir_fcc", ("swir22", "nir", "red"), "SWIR FALSE COLOUR",
                       ("RED = SHORTWAVE INFRARED", "GREEN = NEAR-INFRARED", "BLUE = RED BAND"))


def _index_recipe(name: str, title: str, fn, cmap: str, vmin: float, vmax: float, ends: tuple[str, str]):
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

    return recipe(name)(Recipe(render=render, kind="optical"))


NDVI = _index_recipe("ndvi", "NDVI", lambda L: (L["nir"] - L["red"]) / (L["nir"] + L["red"]), "RdYlGn", -0.2, 0.9,
                     ("WATER OR BARE", "DENSE VEGETATION"))
NDWI = _index_recipe("ndwi", "NDWI", lambda L: (L["green"] - L["nir"]) / (L["green"] + L["nir"]), "BrBG", -0.6, 0.6,
                     ("LAND", "OPEN WATER"))
