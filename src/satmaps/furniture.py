"""Map furniture: the lat/lon grid with its labels, the north arrow and the scale bar.

Panels are drawn in the product's projected metres (a UTM zone), so the grid is drawn by transforming meridians and parallels
into that projection: they come out as straight lines slightly tilted away from the panel's edges, which is the truth about a
UTM map, and each label sits where its line meets the panel's edge. The north arrow points at true north, measured the same way
(it leans off vertical by the meridian convergence, a degree or two in most of a zone). Defaults keep earlier figures as they
were: scale bar on, grid and arrow off.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from matplotlib.patches import Rectangle
from pyproj import Transformer

NICE_DEG = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20)
LINES = 4  # about this many grid lines across a panel


@dataclass(frozen=True)
class Furniture:
    scale: bool = True  # scale bar (on the first panel of a page)
    north: bool = False  # north arrow (on the first panel)
    grid: bool = False  # lat/lon grid with labels (on every panel)


DEFAULT = Furniture()


def nice_step(span_deg: float) -> float:
    """The smallest round step (0.05, 0.1, 0.5, 1, ... degrees) that gives about LINES lines across `span_deg`."""
    want = span_deg / LINES
    return next((s for s in NICE_DEG if s >= want), NICE_DEG[-1])


def _label(value: float, step: float, positive: str, negative: str) -> str:
    decimals = 0 if step >= 1 else min(3, math.ceil(-math.log10(step) - 1e-9))
    return f"{abs(value):.{decimals}f}°{positive if value >= 0 else negative}"


def lonlat_window(ext, epsg: int) -> tuple[float, float, float, float]:
    """(west, south, east, north) of an extent [left, right, bottom, top] in a projected CRS, from its edges."""
    xs, ys = np.meshgrid(np.linspace(ext[0], ext[1], 9), np.linspace(ext[2], ext[3], 9))
    lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(xs.ravel(), ys.ravel())
    return float(np.min(lon)), float(np.min(lat)), float(np.max(lon)), float(np.max(lat))


def graticule_lines(ext, epsg: int) -> dict:
    """The grid for an extent: {"step": degrees, "meridians": [(lon, xs, ys, label)], "parallels": [(lat, xs, ys, label)]},
    each line sampled well past the extent so that it can be cut at the panel's edge."""
    w, s, e, n = lonlat_window(ext, epsg)
    step = nice_step(max(e - w, (n - s) * 1.0))
    to_xy = Transformer.from_crs(4326, epsg, always_xy=True)
    pad_lat, pad_lon = (n - s) * 0.15 + step, (e - w) * 0.15 + step
    meridians, parallels = [], []
    for lon in np.arange(math.ceil(w / step) * step, e + 1e-9, step):
        lats = np.linspace(s - pad_lat, n + pad_lat, 60)
        xs, ys = to_xy.transform(np.full_like(lats, lon), lats)
        meridians.append((float(lon), xs, ys, _label(float(lon), step, "E", "W")))
    for lat in np.arange(math.ceil(s / step) * step, n + 1e-9, step):
        lons = np.linspace(w - pad_lon, e + pad_lon, 60)
        xs, ys = to_xy.transform(lons, np.full_like(lons, lat))
        parallels.append((float(lat), xs, ys, _label(float(lat), step, "N", "S")))
    return {"step": step, "meridians": meridians, "parallels": parallels}


def _at_edge(along, across, edge: float):
    """The value of `along` where the curve (along, across) meets across == edge, or None if it never does."""
    order = np.argsort(across)
    a, c = np.asarray(along)[order], np.asarray(across)[order]
    if not (c[0] <= edge <= c[-1]):
        return None
    return float(np.interp(edge, c, a))


def graticule(ax, t, ext, epsg: int, fs: float = 8.5) -> None:
    """Lat/lon lines across a panel, labelled where they meet its edge: longitudes along the bottom, latitudes down the left."""
    g = graticule_lines(ext, epsg)
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    line = dict(color=t.ink, lw=0.7, alpha=0.45, zorder=8, solid_capstyle="butt")
    tag = dict(fontsize=fs, color=t.ink, zorder=16, bbox=dict(boxstyle="square,pad=0.15", fc=t.card, ec="none", alpha=0.85))
    for _, xs, ys, text in g["meridians"]:
        ax.plot(xs, ys, **line)
        x = _at_edge(xs, ys, ext[2])
        if x is not None and ext[0] + 0.045 * (ext[1] - ext[0]) < x < ext[1] - 0.045 * (ext[1] - ext[0]):
            ax.text(x, ext[2] + 0.008 * (ext[3] - ext[2]), text, ha="center", va="bottom", **tag)
    for _, xs, ys, text in g["parallels"]:
        ax.plot(xs, ys, **line)
        y = _at_edge(ys, xs, ext[0])
        if y is not None and ext[2] + 0.04 * (ext[3] - ext[2]) < y < ext[3] - 0.09 * (ext[3] - ext[2]):  # (clear of the chips)
            ax.text(ext[0] + 0.008 * (ext[1] - ext[0]), y, text, ha="left", va="center", **tag)
    ax.set_xlim(xlim)  # the lines run past the panel: they are cut at its edge, which stays where it was
    ax.set_ylim(ylim)


def true_north(ext, epsg: int) -> tuple[float, float]:
    """Unit vector (dx, dy), in projected metres, pointing at true north from the middle of an extent."""
    cx, cy = (ext[0] + ext[1]) / 2, (ext[2] + ext[3]) / 2
    lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(cx, cy)
    x1, y1 = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat + 0.01)
    d = math.hypot(x1 - cx, y1 - cy)
    return (x1 - cx) / d, (y1 - cy) / d


def north_arrow(ax, t, ext, epsg: int) -> None:
    """An arrow with an N on a small card, lower right of the panel, pointing at true north."""
    dx, dy = true_north(ext, epsg)
    w, h = ext[1] - ext[0], ext[3] - ext[2]
    length = 0.085 * min(w, h)
    cx = ext[1] - 0.05 * w - 0.4 * length
    cy = ext[2] + 0.075 * h + 0.75 * length  # above the row of longitude labels
    mid = cy - 0.1 * length  # the arrow sits a little below the card's middle, under the N
    tail, head = (cx - dx * length / 2, mid - dy * length / 2), (cx + dx * length / 2, mid + dy * length / 2)
    ax.add_patch(Rectangle((cx - 0.45 * length, cy - 0.78 * length), 0.9 * length, 1.62 * length, fc=t.card, ec=t.ink,
                           lw=t.lw(1.0), alpha=0.92, zorder=13))
    ax.annotate("", xy=head, xytext=tail, zorder=15,
                arrowprops=dict(arrowstyle="-|>,head_width=0.4,head_length=0.8", lw=t.lw(1.8), color=t.ink, shrinkA=0, shrinkB=0))
    ax.text(cx, cy + 0.42 * length, "N", ha="center", va="center", fontsize=10.5, weight="bold", color=t.ink, zorder=15)


def decorate(ax, t, ext, epsg: int, f: Furniture = DEFAULT, first: bool = True) -> None:
    """Draw the furniture a figure asks for on one panel. `first` is True for the page's first panel, which alone carries the
    scale bar and the arrow (the panels of a page share one map)."""
    from satmaps.themes.base import scalebar_blocks

    if f.grid:
        graticule(ax, t, ext, epsg)
    if f.scale and first:
        scalebar_blocks(ax, t, ext, lift=0.055 if f.grid else 0.0)
    if f.north and first:
        north_arrow(ax, t, ext, epsg)
