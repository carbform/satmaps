"""Single arrangement (4:5): one product as a full-width hero, plus the inputs of its recipe as small panels if it has any.

For a SAR composite the panels are the three channels it is built from; a recipe with none gets a larger hero.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt

from satmaps.arrangements.compare import platforms
from satmaps.config import Scene
from satmaps.core import RECIPES, THEMES, check_recipe
from satmaps.furniture import DEFAULT, Furniture, decorate
from satmaps.geo import project
from satmaps.layout import Layout, LayoutError, build_context_products
from satmaps.quality import Profile, save
from satmaps.registry import load_builtin
from satmaps.themes.base import chip, img_axes, social_footer, social_header
from satmaps.zoompanels import mark, title, window

FILENAME = "{scene}_{key}band_Social_{tag}.png"


def _sticker(ax, t, text, xy, xytext, fc) -> None:
    ax.annotate(text, xy, xytext=xytext, textcoords="offset points", fontsize=11.5, color=t.ink, zorder=12,
                bbox=dict(boxstyle="square,pad=0.45", fc=fc, ec=t.ink, lw=t.lw(1.4)),
                arrowprops=dict(arrowstyle="-|>", color=t.ink, lw=t.lw(1.5), shrinkA=0, shrinkB=2, mutation_scale=13))
    ax.plot(*xy, "o", ms=7, mfc=fc, mec=t.ink, mew=t.lw(1.5), zorder=11)


def render(scene: Scene, products: dict, out_dir: Path, layout: dict, input: str = "S", recipe: str = "sar_fcc",
           chip_slot: str = "b", theme: str = "retro_80s", stem: str | None = None,
           extra_caveats: tuple[str, ...] = (), profile: Profile | None = None, furniture: Furniture = DEFAULT) -> list[Path]:
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

    with plt.rc_context(t.rc_params()):
        fig = plt.figure(figsize=(12, 15), facecolor=t.paper)
        social_header(fig, t, lay)

        # Hero
        side = bool(r.components or scene.zooms)  # a column of small panels beside the hero
        hy, hw, hx = 0.255, (0.677 if side else 0.92), 0.04
        hh = hw * 12 / 15 * (H / W)
        if hh > 0.585:  # keep the picture's aspect ratio inside the page
            hh = 0.585
            hw = hh * 15 / 12 * (W / H)
            hx = 0.04 + (0.92 - (hw + 0.02 + 0.223 if side else hw)) / 2  # the picture and its column are centred together
        elif 0.585 - hh > 0.04:  # a clearly landscape scene is much shorter than the box: centre it and its side panels
            hy += (0.585 - hh) / 2
        ax = img_axes(fig, t, hx, hy, hw, hh)
        ax.imshow(r.rgba, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
        for i, co in enumerate(lay.get("callouts", [])):
            if co["key"] not in scene.callouts:
                raise LayoutError(f"{lay.path} [[callouts]] #{i + 1}: unknown callout {co['key']!r}; scene has {list(scene.callouts)}")
            xy = project(P.epsg, *scene.callouts[co["key"]])
            _sticker(ax, t, lay.render(co["text"], f"callouts[{i}]"), xy, (co.get("dx", -60), co.get("dy", 60)),
                     t.card if co.get("fill", "card") == "card" else chip_color)
        zgap, zlab = 0.009, 0.019
        zh = (hh - 2 * zgap) / 3 - zlab  # the picture of a zoom cell (three of them, each with a title above)
        zcell = (min(0.96 - (hx + hw + 0.02), 0.223) * 12) / (zh * 15)  # width / height of a zoom picture, as printed
        if scene.zooms and not r.components:
            mark(ax, t, scene.zooms, ext, (H, W), lambda z: zcell, named=True)
        decorate(ax, t, ext, P.epsg, furniture, first=True)
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

        # The optional zoom panels: windows onto the hero, a lettered box on the hero for each (not beside the channel panels)
        if scene.zooms and not r.components:
            px, pw = hx + hw + 0.02, min(0.96 - (hx + hw + 0.02), 0.223)
            stack = len(scene.zooms) * (zh + zlab) + (len(scene.zooms) - 1) * zgap  # one or two panels sit centred beside the picture
            for i, z in enumerate(scene.zooms):
                (r0, r1), (c0, c1) = window(z, zcell, (H, W))
                top = hy + hh - (hh - stack) / 2 - i * (zh + zlab + zgap)
                fig.text(px + 0.002, top - zlab / 2, title(z), fontsize=10.5, color=t.ink, weight="semibold", va="center", zorder=20)
                za = img_axes(fig, t, px, top - zlab - zh, pw, zh)
                za.imshow(r.rgba[r0:r1, c0:c1], aspect="auto", interpolation="antialiased")

        social_footer(fig, t, lay, legend=r.legend, caveats=[*r.caveats, *extra_caveats], required_credits=[(P.meta["attribution"], P.meta["credit"])])
        out = Path(out_dir) / (f"{stem}.png" if stem else FILENAME.format(scene=f"{platforms([P])}_{scene.name}", key=input, tag=t.tag))
        t.finish(fig)
        save(fig, out, t.paper, profile)
        plt.close(fig)
    return [out]
