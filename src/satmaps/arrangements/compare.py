"""Compare arrangement (4:5): chrome around a split-view hero of two products and three zoom pairs.

Any two products on one grid and any recipe: L-vs-S, before/after, SAR-vs-optical (once resampled to a common grid).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from satmaps.config import Scene
from satmaps.core import RECIPES, THEMES, check_recipe
from satmaps.furniture import DEFAULT, Furniture, decorate
from satmaps.layout import Layout, LayoutError, acquisition_label, build_context_products
from satmaps.legend import named_legend
from satmaps.quality import Profile, save
from satmaps.registry import load_builtin
from satmaps.themes.base import chip, img_axes, social_footer, social_header
from satmaps.zoompanels import mark, title, window

FILENAME = "{scene}_{a}vs{b}_Social_{tag}.png"


def platforms(products) -> str:
    """'NISAR', or 'NISAR-Sentinel2' for a cross-sensor figure: the output file prefix."""
    return "-".join(dict.fromkeys(p.meta["platform"].replace(" ", "") for p in products))


def panel_text(lay: Layout, key: str, prod) -> str:
    """Chip text on the hero: the layout's `panels.<id>`, else the product's own label."""
    if lay.get(f"panels.{key}") is not None:
        return lay.text(f"panels.{key}")
    return f"{prod.meta['platform']} {prod.meta['label']} · {acquisition_label(prod.meta)}".upper()


def render(scene: Scene, products: dict, out_dir: Path, layout: dict, inputs: tuple[str, str] = ("L", "S"),
           recipe: str | dict = "sar_fcc", per_band: bool | None = None, theme: str = "neo_retro", strict: bool = False,
           stem: str | None = None, extra_caveats: tuple[str, ...] = (), profile: Profile | None = None, furniture: Furniture = DEFAULT) -> list[Path]:
    """`inputs` are the two input ids, left and right of the split. Wording comes from `layout`; facts from the products.

    `recipe` is one name for both inputs or ``{input id: name}`` (SAR on one side, optical on the other). `stem` names the file.
    `per_band` overrides `[style] stretch`: True stretches each input to its own percentiles (colours not comparable),
    False uses one stretch pooled over both (needs a recipe that can pool). `strict=False` allows different passes."""
    load_builtin()
    t = THEMES.get_or_raise(theme)
    a, b = inputs
    A, B = products[a], products[b]
    names = {a: recipe, b: recipe} if isinstance(recipe, str) else {a: recipe[a], b: recipe[b]}
    recA, recB = RECIPES.get_or_raise(names[a]), RECIPES.get_or_raise(names[b])
    for pid, prod, rec_ in ((a, A, recA), (b, B, recB)):
        try:
            check_recipe(names[pid], rec_, prod, pid)
        except ValueError as e:
            raise LayoutError(str(e)) from None
    rec = recA  # the recipe that pools the stretch, when both sides use the same one
    if A.layers[next(iter(A.layers))].shape != B.layers[next(iter(B.layers))].shape or not (
            np.allclose(A.x, B.x) and np.allclose(A.y, B.y)):
        raise ValueError(f"compare needs {a} and {b} on one grid; resample one onto the other first (see docs/architecture.md)")
    if per_band is None:
        mode = layout.get("style", {}).get("stretch", "per-band")
        if mode not in ("per-band", "pooled"):
            raise LayoutError(f"{layout.get('_path')}: [style] stretch must be 'per-band' or 'pooled', not {mode!r}")
        per_band = mode == "per-band"
    if not per_band and (names[a] != names[b] or rec.shared_lims is None):
        raise LayoutError(f"cannot pool a stretch over {names[a]!r} and {names[b]!r}; use per-band")
    lay = Layout(layout, build_context_products(scene, {a: A, b: B}, per_band, strict=strict))
    lims = None if per_band else rec.shared_lims([A, B])
    rA, rB = recA.render(A, lims), recB.render(B, lims)
    legend = named_legend([(A, rA.legend), (B, rB.legend)])  # each item says whose it is
    caveats = list(dict.fromkeys(c for r in (rA, rB) for c in r.caveats))
    if per_band and (recA.shared_lims is not None or recB.shared_lims is not None):
        caveats.append("Colours are not comparable between the two inputs (own stretch each).")
    caveats += [c for c in extra_caveats if c not in caveats]  # what the template says about how the inputs relate
    ext = rB.extent
    H, W = rB.rgba.shape[:2]
    split = W // 2
    hero = rA.rgba.copy()
    hero[:, split:] = rB.rgba[:, split:]
    xsplit = ext[0] + (ext[1] - ext[0]) * split / W
    rA_, rB_ = rA.rgba, rB.rgba

    with plt.rc_context(t.rc_params()):
        fig = plt.figure(figsize=(12, 15), facecolor=t.paper)

        social_header(fig, t, lay)

        # Hero: first input left, second right, same pixels
        hy, hw, hx = 0.255, (0.677 if scene.zooms else 0.92), 0.04
        hh = hw * 12 / 15 * (H / W)
        if hh > 0.585:  # keep the picture's aspect ratio inside the page
            hh = 0.585
            hw = hh * 15 / 12 * (W / H)
            hx = 0.04 + (0.92 - (hw + 0.02 + 0.223 if scene.zooms else hw)) / 2  # the picture and its column are centred together
        ax = img_axes(fig, t, hx, hy, hw, hh)
        ax.imshow(hero, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
        ax.axvline(xsplit, color=t.card, lw=t.lw(2.2), zorder=12)
        ax.text(xsplit, ext[2] + 0.5 * (ext[3] - ext[2]), f"◄ {a.upper()}   {b.upper()} ►", ha="center", va="center", fontsize=10.5, color=t.ink,
                zorder=13, bbox=dict(boxstyle="square,pad=0.45", fc=t.card, ec=t.ink, lw=t.lw(1.3)))

        # Zoom cells: first input above second for each window (their shape is needed to mark the windows on the hero)
        px, pw = hx + hw + 0.02, min(0.96 - (hx + hw + 0.02), 0.223)
        gap, lab = 0.009, 0.019
        ch = (hh - 2 * gap) / 3
        ih = (ch - lab) / 2
        cell = (pw * 12) / (ih * 15)  # width / height of a zoom picture, as printed
        mark(ax, t, scene.zooms, ext, (H, W), lambda z: cell)
        decorate(ax, t, ext, A.epsg, furniture, first=True)
        chip(fig, t, hx + 0.012, hy + hh - 0.014, panel_text(lay, a, A), t.chip_a, va="top", ha="left")
        chip(fig, t, hx + hw - 0.012, hy + hh - 0.014, panel_text(lay, b, B), t.chip_b, va="top", ha="right")

        for i, z in enumerate(scene.zooms):
            (r0, r1), (c0, c1) = window(z, cell, (H, W))
            top = hy + hh - i * (ch + gap)
            fig.text(px + 0.002, top - lab / 2, title(z), fontsize=10.5, color=t.ink, weight="semibold", va="center", zorder=20)
            for j, (rg, bandname, col) in enumerate(((rA_, a, t.chip_a), (rB_, b, t.chip_b))):
                py = top - lab - (j + 1) * ih
                za = img_axes(fig, t, px, py, pw, ih - (0.003 if j == 0 else 0))
                za.imshow(rg[r0:r1, c0:c1], aspect="auto", interpolation="antialiased")
                chip(fig, t, px + 0.006, py + ih - 0.008, bandname, col, fs=10, va="top")

        social_footer(fig, t, lay, legend=legend, caveats=caveats, required_credits=[(p.meta["attribution"], p.meta["credit"]) for p in (A, B)])

        out = Path(out_dir) / (f"{stem}.png" if stem else FILENAME.format(scene=f"{platforms([A, B])}_{scene.name}", a=a, b=b, tag=t.tag))
        t.finish(fig)
        save(fig, out, t.paper, profile)
        plt.close(fig)
    return [out]
