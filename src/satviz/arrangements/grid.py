"""Grid template (4:5): two to six inputs as equal panels, e.g. radar and optical from several sensors on the same day.

Each panel is one input with its recipe, all on the one canvas. Panel size follows the picture's aspect ratio and the
space the page has for the number of panels.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import matplotlib.pyplot as plt

from satviz.arrangements.compare import panel_text, platforms
from satviz.config import Scene
from satviz.core import RECIPES, THEMES, LegendItem, check_recipe
from satviz.layout import Layout, LayoutError, build_context_products
from satviz.registry import load_builtin
from satviz.themes.base import chip, img_axes, scalebar_blocks, social_footer, social_header

FILENAME = "{scene}_grid{n}_Social_{tag}.png"
AREA_BOX = (0.04, 0.255, 0.92, 0.585)  # x, y, width, height in figure fractions (the page is 12 x 15 inches)
FIG_W, FIG_H = 12.0, 15.0


def grid_legend(legends: list[list]) -> list:
    """One legend for several panels. Identical legends collapse; with two kinds the first three items of each are shown;
    with more, items of the same colour are merged ('RED = HH · VV · RED BAND') so every channel mapping is still stated."""
    groups: dict[tuple, list] = {}
    for leg in legends:
        groups.setdefault(tuple(i.text for i in leg[:3]), leg)
    kinds = list(groups.values())
    if len(kinds) == 1:
        return kinds[0][:6]
    if len(kinds) == 2:
        return [*kinds[0][:3], *kinds[1][:3]]
    merged: dict[str, list] = {}
    for leg in kinds:
        for item in leg[:3]:
            merged.setdefault(item.color, []).append(item.text)
    out = []
    for color, texts in merged.items():
        left = texts[0].split(" = ")[0]
        rights = list(dict.fromkeys(re.sub(r"\s*\(.*\)$", "", x.split(" = ", 1)[-1]).strip() for x in texts))
        out.append(LegendItem(color, f"{left} = {' · '.join(rights)}"))
    return out


def layout_cells(n: int, aspect: float) -> tuple[int, int, float]:
    """(rows, columns, panel width in figure fractions) that give the largest panels for `n` pictures of height/width `aspect`."""
    best = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        gap = 0.012
        w = min((AREA_BOX[2] - gap * (cols - 1)) / cols, (AREA_BOX[3] * FIG_H - gap * FIG_W * (rows - 1)) / (rows * aspect * FIG_W))
        if best is None or w > best[2]:
            best = (rows, cols, w)
    return best


def render(scene: Scene, products: dict, out_dir: Path, layout: dict, inputs: tuple[str, ...], recipe: str | dict = "sar_fcc",
           theme: str = "neo_retro", stem: str | None = None, strict: bool = True) -> list[Path]:
    """`inputs` are two to six input ids in reading order (left to right, top to bottom); `recipe` is one name or {id: name}."""
    load_builtin()
    t = THEMES.get_or_raise(theme)
    if not 2 <= len(inputs) <= 6:
        raise LayoutError(f"grid needs 2 to 6 inputs, got {len(inputs)}")
    names = {k: recipe if isinstance(recipe, str) else recipe[k] for k in inputs}
    rendered, recs = {}, {}
    for k in inputs:
        recs[k] = RECIPES.get_or_raise(names[k])
        try:
            check_recipe(names[k], recs[k], products[k], k)
        except ValueError as e:
            raise LayoutError(str(e)) from None
        rendered[k] = recs[k].render(products[k])
    first = rendered[inputs[0]]
    lay = Layout(layout, build_context_products(scene, {k: products[k] for k in inputs}, True, strict=strict))

    legend = grid_legend([rendered[k].legend for k in inputs])
    caveats = list(dict.fromkeys(c for k in inputs for c in rendered[k].caveats))
    if any(recs[k].shared_lims is not None for k in inputs):
        caveats.append("Colours are not comparable between panels (own stretch each).")

    H, W = first.rgba.shape[:2]
    rows, cols, pw = layout_cells(len(inputs), H / W)
    ph = pw * FIG_W * (H / W) / FIG_H
    gap = 0.012
    total_w, total_h = cols * pw + (cols - 1) * gap, rows * ph + (rows - 1) * gap * FIG_W / FIG_H
    x0 = AREA_BOX[0] + (AREA_BOX[2] - total_w) / 2
    ytop = AREA_BOX[1] + AREA_BOX[3] - (AREA_BOX[3] - total_h) / 2

    with plt.rc_context({"font.family": list(t.body_font), "font.weight": "normal"}):
        fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=t.paper)
        social_header(fig, t, lay)
        for i, k in enumerate(inputs):
            r, c = divmod(i, cols)
            x = x0 + c * (pw + gap)
            y = ytop - (r + 1) * ph - r * gap * FIG_W / FIG_H
            ax = img_axes(fig, t, x, y, pw, ph)
            rd = rendered[k]
            ax.imshow(rd.rgba, extent=rd.extent, origin="upper", aspect="auto", interpolation="antialiased")
            if i == 0:
                scalebar_blocks(ax, t, rd.extent)
            chip(fig, t, x + 0.008, y + ph - 0.008, panel_text(lay, k, products[k]), (t.chip_a, t.chip_b)[i % 2], fs=10, va="top")
        social_footer(fig, t, lay, legend=legend, caveats=caveats,
                      required_credits=[(products[k].meta["attribution"], products[k].meta["credit"]) for k in inputs])
        out = Path(out_dir) / (f"{stem}.png" if stem else FILENAME.format(
            scene=f"{platforms([products[k] for k in inputs])}_{scene.name}", n=len(inputs), tag=t.tag))
        fig.savefig(out, dpi=180, facecolor=t.paper)
        plt.close(fig)
    return [out]
