"""Shared drawing helpers: scale bar and the neo-retro 'bento' panels (outline, hard shadow, chips)."""
from __future__ import annotations

import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle
from matplotlib.transforms import offset_copy

from nisar_viz.layout import Layout, LayoutError
from nisar_viz.themes import NeoRetro


def scalebar(ax, ext, km: float, y_frac: float = 0.045, x_frac: float = 0.035, fs: float = 10) -> None:
    """White-over-black bar of `km` kilometres with a stroked label, in axes-data (metre) coordinates."""
    x0 = ext[0] + x_frac * (ext[1] - ext[0])
    y0 = ext[2] + y_frac * (ext[3] - ext[2])
    ax.plot([x0, x0 + km * 1000], [y0, y0], color="white", lw=4.5, solid_capstyle="butt", zorder=15)
    ax.plot([x0, x0 + km * 1000], [y0, y0], color="black", lw=1.8, solid_capstyle="butt", zorder=16)
    ax.text(x0 + km * 500, y0 + 0.014 * (ext[3] - ext[2]), f"{km:g} km", ha="center", fontsize=fs,
            weight="bold", color="white", path_effects=[pe.withStroke(linewidth=2.5, foreground="black")], zorder=17)


def block(fig, t: NeoRetro, x, y, w, h, fc=None, lw=1.5, shadow=True) -> None:
    """Filled, outlined panel in figure coordinates with an optional hard offset shadow."""
    if shadow:
        fig.add_artist(Rectangle((x + t.shadow[0], y + t.shadow[1]), w, h, transform=fig.transFigure,
                                 fc=t.ink, ec="none", zorder=0))
    fig.add_artist(Rectangle((x, y), w, h, transform=fig.transFigure, fc=fc or t.card, ec=t.ink, lw=lw, zorder=1))


def img_axes(fig, t: NeoRetro, x, y, w, h):
    """Image axes with ink outline and hard shadow."""
    fig.add_artist(Rectangle((x + t.shadow[0], y + t.shadow[1]), w, h, transform=fig.transFigure,
                             fc=t.ink, ec="none", zorder=0))
    ax = fig.add_axes([x, y, w, h], zorder=2)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(1.5)
        s.set_color(t.ink)
    return ax


def chip(target, t: NeoRetro, x, y, text, fc, fs=11, **kw):
    """Small outlined label box. `target` is a Figure (figure coords) or Axes."""
    return target.text(x, y, text, fontsize=fs, color=t.ink, zorder=20, weight="medium",
                       bbox=dict(boxstyle="square,pad=0.35", fc=fc, ec=t.ink, lw=1.3), **kw)


def social_header(fig, t: NeoRetro, lay: Layout) -> None:
    """Title box with one soft offset behind the title, details right-aligned, and the info line under it."""
    block(fig, t, 0.04, 0.885, 0.92, 0.09)
    title = lay.text("header.title")
    fig.text(0.06, 0.941, title, fontsize=40, color=t.orange, va="center", family=list(t.title_font), weight="bold",
             transform=offset_copy(fig.transFigure, fig=fig, x=2.2, y=-2.2, units="points"), zorder=3)
    fig.text(0.06, 0.941, title, fontsize=40, color=t.ink, va="center", family=list(t.title_font), weight="bold", zorder=4)
    fig.text(0.062, 0.903, lay.text("header.subtitle"), fontsize=11.5, color=t.muted, va="center", zorder=4)
    fig.text(0.94, 0.941, lay.text("header.date"), fontsize=13, color=t.ink, va="center", ha="right", weight="semibold", zorder=4)
    fig.text(0.94, 0.909, lay.text("header.time"), fontsize=11.5, color=t.muted, va="center", ha="right", zorder=4)
    fig.text(0.04, 0.858, lay.text("header.info_line"), fontsize=10.5, color=t.muted, va="center")


def social_footer(fig, t: NeoRetro, lay: Layout) -> None:
    """How-to-read block (up to 6 items), notice strip (up to 3 lines) and credits (up to 3 lines)."""
    block(fig, t, 0.04, 0.135, 0.92, 0.095)
    fig.text(0.058, 0.213, lay.text("how_to_read.title"), fontsize=11, color=t.ink, weight="bold", va="center")
    fig.text(0.168, 0.213, lay.text("how_to_read.subtitle"), fontsize=10.5, color=t.muted, va="center")
    items = lay.raw("how_to_read.items")
    if len(items) > 6:
        raise LayoutError(f"{lay.path} [how_to_read.items]: {len(items)} items, at most 6 fit")
    for i, item in enumerate(items):
        col = t.noise_grey if item["color"] == "noise" else item["color"]
        xx = 0.058 + (i % 3) * 0.300
        yy = 0.188 - (i // 3) * 0.0265
        fig.add_artist(Rectangle((xx, yy - 0.008), 0.016, 0.016, transform=fig.transFigure, fc=col, ec=t.ink, lw=1.1, zorder=6))
        fig.text(xx + 0.024, yy, lay.render(item["text"], f"how_to_read.items[{i}]").strip(), fontsize=9.6, color=t.ink,
                 va="center", zorder=6)

    # the notice strip and credits flow downwards from the how-to-read block
    notes = lay.lines("notes.lines", limit=3)
    credits = lay.lines("credits.lines", limit=3)
    bottom = round(0.119 - 0.0235 * len(notes), 4)
    if notes:
        block(fig, t, 0.04, bottom, 0.92, round(0.0235 * len(notes), 4), t.note, shadow=False, lw=1.2)
    for i, line in enumerate(notes):
        fig.text(0.05, round(0.1075 - 0.024 * i, 4), line, fontsize=9.3, color=t.ink, va="center")
    for i, line in enumerate(credits):
        fig.text(0.04, round(bottom - 0.02 - 0.02 * i, 4), line, fontsize=9, color=t.muted, va="center")
