"""Shared drawing helpers: scale bar and the neo-retro 'bento' panels (outline, hard shadow, chips)."""
from __future__ import annotations

import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle

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
