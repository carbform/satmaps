"""Single template (4:5): one product as a full-width hero, plus the inputs of its recipe as small panels if it has any.

For a SAR composite the panels are the three channels it is built from; a recipe with none gets a larger hero.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt

from satviz.config import Scene
from satviz.core import RECIPES, THEMES, check_recipe
from satviz.geo import project
from satviz.layout import Layout, LayoutError, build_context_products
from satviz.registry import load_builtin
from satviz.templates.compare import platforms
from satviz.themes.base import chip, img_axes, scalebar_blocks, social_footer, social_header

FILENAME = "{scene}_{key}band_Social_{tag}.png"


def _sticker(ax, t, text, xy, xytext, fc) -> None:
    ax.annotate(text, xy, xytext=xytext, textcoords="offset points", fontsize=11.5, color=t.ink, zorder=12,
                bbox=dict(boxstyle="square,pad=0.45", fc=fc, ec=t.ink, lw=t.lw(1.4)),
                arrowprops=dict(arrowstyle="-|>", color=t.ink, lw=t.lw(1.5), shrinkA=0, shrinkB=2, mutation_scale=13))
    ax.plot(*xy, "o", ms=7, mfc=fc, mec=t.ink, mew=t.lw(1.5), zorder=11)


def render(scene: Scene, products: dict, out_dir: Path, layout: dict, input: str = "S", recipe: str = "sar_fcc",
           chip_slot: str = "b", theme: str = "neo_retro", stem: str | None = None) -> list[Path]:
    """Wording comes from `layout`; facts come from the product. `chip_slot` ('a' or 'b') picks the theme's chip colour."""
    load_builtin()
    t = THEMES.get_or_raise(theme)
    rec = RECIPES.get_or_raise(recipe)
    P = products[input]
    try:
        check_recipe(recipe, rec, P, input)
    except ValueError as e:
        raise LayoutError(str(e)) from None
    r = rec.render(P)
    lim = SimpleNamespace(**{f"{k}_{e}": v for k, (lo, hi) in (r.lims or {}).items() for e, v in (("lo", lo), ("hi", hi))})
    lay = Layout(layout, build_context_products(scene, {input: P}, True, extra={"lim": lim}))
    chip_color = {"a": t.chip_a, "b": t.chip_b}[chip_slot]
    ext = r.extent
    H, W = r.rgba.shape[:2]

    with plt.rc_context({"font.family": list(t.body_font), "font.weight": "normal"}):
        fig = plt.figure(figsize=(12, 15), facecolor=t.paper)
        social_header(fig, t, lay)

        # Hero
        hy, hw, hx = 0.255, (0.677 if r.components else 0.92), 0.04
        hh = hw * 12 / 15 * (H / W)
        if hh > 0.585:  # no side panels: keep the picture's aspect ratio inside the page
            hh = 0.585
            hw = hh * 15 / 12 * (W / H)
            hx = 0.04 + (0.92 - hw) / 2
        ax = img_axes(fig, t, hx, hy, hw, hh)
        ax.imshow(r.rgba, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
        for i, co in enumerate(lay.get("callouts", [])):
            if co["key"] not in scene.callouts:
                raise LayoutError(f"{lay.path} [[callouts]] #{i + 1}: unknown callout {co['key']!r}; scene has {list(scene.callouts)}")
            xy = project(P.epsg, *scene.callouts[co["key"]])
            _sticker(ax, t, lay.render(co["text"], f"callouts[{i}]"), xy, (co.get("dx", -60), co.get("dy", 60)),
                     t.card if co.get("fill", "card") == "card" else chip_color)
        scalebar_blocks(ax, t, ext)
        chip(fig, t, hx + 0.012, hy + hh - 0.014, (lay.text("panels.band") if lay.get("panels.band") is not None else f"{P.meta['platform']} {P.meta['label']}".upper()), chip_color, va="top", ha="left")
        chip(fig, t, hx + hw - 0.012, hy + hh - 0.014, (lay.text("panels.composite") if lay.get("panels.composite") is not None else r.title), t.card, va="top", ha="right")

        # The inputs of the recipe (for the SAR composite: the three bands, each tinted in its channel colour)
        if r.components:
            n = len(r.components)
            px, pw = hx + hw + 0.02, 0.96 - (hx + hw + 0.02)
            gap = 0.009
            ph = (hh - (n - 1) * gap) / n
            labels = lay.get("channels.labels") or [c.label for c in r.components]
            if len(labels) != n:
                raise LayoutError(f"{lay.path} [channels.labels]: need exactly {n} labels, one per panel")
            for i, comp in enumerate(r.components):
                py = hy + hh - (i + 1) * ph - i * gap
                a = img_axes(fig, t, px, py, pw, ph)
                a.imshow(comp.img, extent=r.components_extent, origin="upper", aspect="auto", interpolation="nearest")
                chip(fig, t, px + 0.008, py + ph - 0.01, lay.render(labels[i], f"channels.labels[{i}]"), comp.color, fs=10.5, va="top")

        social_footer(fig, t, lay, legend=r.legend, caveats=r.caveats, required_credits=[(P.meta["attribution"], P.meta["credit"])])
        out = Path(out_dir) / (f"{stem}.png" if stem else FILENAME.format(scene=f"{platforms([P])}_{scene.name}", key=input, tag=t.tag))
        fig.savefig(out, dpi=180, facecolor=t.paper)
        plt.close(fig)
    return [out]
