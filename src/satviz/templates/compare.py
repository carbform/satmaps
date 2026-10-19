"""Compare template (4:5): chrome around a split-view hero of two products and three zoom pairs.

Any two products on one grid and any recipe: L-vs-S, before/after, SAR-vs-optical (once resampled to a common grid).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from satviz.config import Scene
from satviz.core import RECIPES, THEMES, check_recipe
from satviz.layout import Layout, LayoutError, build_context_products
from satviz.registry import load_builtin
from satviz.themes.base import chip, img_axes, scalebar_blocks, social_footer, social_header

FILENAME = "{scene}_{a}vs{b}_Social_{tag}.png"


def platforms(products) -> str:
    """'NISAR', or 'NISAR-Sentinel2' for a cross-sensor figure: the output file prefix."""
    return "-".join(dict.fromkeys(p.meta["platform"].replace(" ", "") for p in products))


def panel_text(lay: Layout, key: str, prod) -> str:
    """Chip text on the hero: the layout's `panels.<id>`, else the product's own label."""
    if lay.get(f"panels.{key}") is not None:
        return lay.text(f"panels.{key}")
    return f"{prod.meta['platform']} {prod.meta['label']}".upper()


def render(scene: Scene, products: dict, out_dir: Path, layout: dict, inputs: tuple[str, str] = ("L", "S"),
           recipe: str | dict = "sar_fcc", per_band: bool | None = None, theme: str = "neo_retro", strict: bool = True,
           stem: str | None = None) -> list[Path]:
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
    legend = list({i.text: i for i in (*rA.legend, *rB.legend)}.values())
    if names[a] != names[b] or len(legend) > 6:  # the six legend slots are shared: the first three items of each side
        legend = [*rA.legend[:3], *rB.legend[:3]]
    caveats = list(dict.fromkeys(c for r in (rA, rB) for c in r.caveats))
    if per_band and (recA.shared_lims is not None or recB.shared_lims is not None):
        caveats.append("Colours are not comparable between the two inputs (own stretch each).")
    ext = rB.extent
    H, W = rB.rgba.shape[:2]
    split = W // 2
    hero = rA.rgba.copy()
    hero[:, split:] = rB.rgba[:, split:]
    xsplit = ext[0] + (ext[1] - ext[0]) * split / W
    rA_, rB_ = rA.rgba, rB.rgba

    with plt.rc_context({"font.family": list(t.body_font), "font.weight": "normal"}):
        fig = plt.figure(figsize=(12, 15), facecolor=t.paper)

        social_header(fig, t, lay)

        # Hero: first input left, second right, same pixels
        hy, hw, hx = 0.255, (0.677 if scene.zooms else 0.92), 0.04
        hh = hw * 12 / 15 * (H / W)
        if hh > 0.585:  # no zoom column: keep the picture's aspect ratio inside the page
            hh = 0.585
            hw = hh * 15 / 12 * (W / H)
            hx = 0.04 + (0.92 - hw) / 2
        ax = img_axes(fig, t, hx, hy, hw, hh)
        ax.imshow(hero, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
        ax.axvline(xsplit, color=t.card, lw=t.lw(2.2), zorder=12)
        ax.text(xsplit, ext[2] + 0.5 * (ext[3] - ext[2]), f"◄ {a.upper()}   {b.upper()} ►", ha="center", va="center", fontsize=10.5, color=t.ink,
                zorder=13, bbox=dict(boxstyle="square,pad=0.45", fc=t.card, ec=t.ink, lw=t.lw(1.3)))

        def xx0(c):
            return ext[0] + (ext[1] - ext[0]) * c / W

        def yy0(r):
            return ext[3] - (ext[3] - ext[2]) * r / H

        for z in scene.zooms:
            (r0, r1), (c0, c1) = z.rows, z.cols
            ax.add_patch(Rectangle((xx0(c0), yy0(r1)), xx0(c1) - xx0(c0), yy0(r0) - yy0(r1), fc="none", ec=t.card, lw=t.lw(1.4), zorder=11))
            ax.text(xx0(c0), yy0(r0) + 0.006 * (ext[3] - ext[2]), z.key, ha="left", va="bottom", fontsize=10.5, color=t.ink, zorder=13,
                    bbox=dict(boxstyle="square,pad=0.2", fc=t.card, ec=t.ink, lw=t.lw(1.0)))
        scalebar_blocks(ax, t, ext)
        chip(fig, t, hx + 0.012, hy + hh - 0.014, panel_text(lay, a, A), t.chip_a, va="top", ha="left")
        chip(fig, t, hx + hw - 0.012, hy + hh - 0.014, panel_text(lay, b, B), t.chip_b, va="top", ha="right")

        # Zoom cells: first input above second for each window
        px, pw = hx + hw + 0.02, 0.96 - (hx + hw + 0.02)
        gap, lab = 0.009, 0.019
        ch = (hh - 2 * gap) / 3
        ih = (ch - lab) / 2
        for i, z in enumerate(scene.zooms):
            (r0, r1), (c0, c1) = z.rows, z.cols
            top = hy + hh - i * (ch + gap)
            fig.text(px + 0.002, top - lab / 2, f"{z.key}  {z.name}", fontsize=10.5, color=t.ink, weight="semibold", va="center", zorder=20)
            for j, (rg, bandname, col) in enumerate(((rA_, a, t.chip_a), (rB_, b, t.chip_b))):
                py = top - lab - (j + 1) * ih
                za = img_axes(fig, t, px, py, pw, ih - (0.003 if j == 0 else 0))
                za.imshow(rg[r0:r1, c0:c1], aspect="auto", interpolation="antialiased")
                chip(fig, t, px + 0.006, py + ih - 0.008, bandname, col, fs=10, va="top")

        social_footer(fig, t, lay, legend=legend, caveats=caveats, required_credits=[(p.meta["attribution"], p.meta["credit"]) for p in (A, B)])

        out = Path(out_dir) / (f"{stem}.png" if stem else FILENAME.format(scene=f"{platforms([A, B])}_{scene.name}", a=a, b=b, tag=t.tag))
        fig.savefig(out, dpi=180, facecolor=t.paper)
        plt.close(fig)
    return [out]
