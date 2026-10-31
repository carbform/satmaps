"""Zoom side panels: up to three small windows onto the hero picture, each marked on it by a lettered box.

A window given as rows and columns is drawn as it is. One that came from a centre and a size (what the app's map and
`--zoom` give) is widened to the shape of its panel around its centre, so the whole of what was drawn stays in view and the
panel is not stretched."""
from __future__ import annotations

from matplotlib.patches import Rectangle

from satmaps.config import Zoom


def fit_window(rows: tuple[int, int], cols: tuple[int, int], aspect: float,
               shape: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    """The window widened (never narrowed) to width / height = `aspect` around its centre, moved inside a (rows, cols) picture."""
    (r0, r1), (c0, c1) = rows, cols
    h, w = r1 - r0, c1 - c0
    if w / h < aspect:
        w = h * aspect
    else:
        h = w / aspect
    H, W = shape
    scale = min(1.0, W / w, H / h)  # a picture smaller than the window: shrink it, keeping the shape
    w, h = w * scale, h * scale
    cr, cc = (r0 + r1) / 2, (c0 + c1) / 2
    top = min(max(round(cr - h / 2), 0), H - round(h))
    left = min(max(round(cc - w / 2), 0), W - round(w))
    return (top, top + round(h)), (left, left + round(w))


def window(z: Zoom, aspect: float, shape: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    return fit_window(z.rows, z.cols, aspect, shape) if z.fit else (z.rows, z.cols)


def title(z: Zoom) -> str:
    return f"{z.key}  {z.name}" if z.name else f"ZOOM {z.key}"


def mark(ax, t, zooms, ext, shape, aspect_of) -> None:
    """The lettered boxes on the hero, over `ext` = (left, right, bottom, top) of a picture `shape` = (rows, cols) pixels.
    `aspect_of(z)` is the panel shape of that zoom, so the box is the window its panel shows."""
    H, W = shape

    def xx(c):
        return ext[0] + (ext[1] - ext[0]) * c / W

    def yy(r):
        return ext[3] - (ext[3] - ext[2]) * r / H

    for z in zooms:
        (r0, r1), (c0, c1) = window(z, aspect_of(z), shape)
        ax.add_patch(Rectangle((xx(c0), yy(r1)), xx(c1) - xx(c0), yy(r0) - yy(r1), fc="none", ec=t.card, lw=t.lw(1.4), zorder=11))
        ax.text(xx(c0), yy(r0) + 0.006 * (ext[3] - ext[2]), z.key, ha="left", va="bottom", fontsize=10.5, color=t.ink, zorder=13,
                bbox=dict(boxstyle="square,pad=0.2", fc=t.card, ec=t.ink, lw=t.lw(1.0)))
