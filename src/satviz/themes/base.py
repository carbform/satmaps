"""Theme tokens and the chrome primitives (bento blocks, chips, header, footer) drawn from them.

A theme is a `Theme` instance of design tokens. The same primitives draw every theme, so a new look that fits the
bento structure is a dozen tokens. A look that needs a different structure (e.g. the editorial newspaper) gets its own
chrome module instead.

Only the chrome around the data is styled; data panels are never filtered, glowed or recoloured, and no theme can
hide the notice strip.
"""
from __future__ import annotations

from dataclasses import dataclass

from matplotlib.patches import Rectangle
from matplotlib.transforms import offset_copy

from satviz.layout import Layout, LayoutError


@dataclass(frozen=True)
class Theme:
    name: str
    tag: str  # used in output filenames, e.g. "NeoRetro"
    paper: str  # page background
    card: str  # panels
    ink: str  # outlines and text
    muted: str  # secondary text
    chip_l: str  # L-band chips
    chip_s: str  # S-band chips
    note: str  # notice strip
    accent: str | None = None  # offset behind the title; None = no offset
    header_fc: str | None = None  # title block fill; None = card
    noise_grey: str = "#3a3a40"  # also used in the data, so it is not a style choice
    title_font: tuple[str, ...] = ("DejaVu Sans",)
    body_font: tuple[str, ...] = ("DejaVu Sans Mono",)
    title_size: float = 40
    shadow: tuple[float, float] = (0.0, 0.0)  # hard shadow offset, figure fraction; (0, 0) = none
    line_scale: float = 1.0  # multiplies every outline width

    @property
    def has_shadow(self) -> bool:
        return self.shadow != (0.0, 0.0)

    def lw(self, base: float) -> float:
        return base * self.line_scale


def block(fig, t: Theme, x, y, w, h, fc=None, lw=1.5, shadow=True) -> None:
    """Filled, outlined panel in figure coordinates with an optional hard offset shadow."""
    if shadow and t.has_shadow:
        fig.add_artist(Rectangle((x + t.shadow[0], y + t.shadow[1]), w, h, transform=fig.transFigure,
                                 fc=t.ink, ec="none", zorder=0))
    fig.add_artist(Rectangle((x, y), w, h, transform=fig.transFigure, fc=fc or t.card, ec=t.ink, lw=t.lw(lw), zorder=1))


def img_axes(fig, t: Theme, x, y, w, h):
    """Image axes with ink outline and hard shadow."""
    if t.has_shadow:
        fig.add_artist(Rectangle((x + t.shadow[0], y + t.shadow[1]), w, h, transform=fig.transFigure,
                                 fc=t.ink, ec="none", zorder=0))
    ax = fig.add_axes([x, y, w, h], zorder=2)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(t.lw(1.5))
        s.set_color(t.ink)
    return ax


def chip(target, t: Theme, x, y, text, fc, fs=11, **kw):
    """Small outlined label box. `target` is a Figure (figure coords) or Axes."""
    return target.text(x, y, text, fontsize=fs, color=t.ink, zorder=20, weight="medium",
                       bbox=dict(boxstyle="square,pad=0.35", fc=fc, ec=t.ink, lw=t.lw(1.3)), **kw)


def social_header(fig, t: Theme, lay: Layout) -> None:
    """Title box with (if the theme has an accent) one soft offset behind the title, details right-aligned, and the info line under it."""
    block(fig, t, 0.04, 0.885, 0.92, 0.09, fc=t.header_fc)
    title = lay.text("header.title")
    if t.accent:
        fig.text(0.06, 0.941, title, fontsize=t.title_size, color=t.accent, va="center", family=list(t.title_font), weight="bold",
                 transform=offset_copy(fig.transFigure, fig=fig, x=2.2, y=-2.2, units="points"), zorder=3)
    fig.text(0.06, 0.941, title, fontsize=t.title_size, color=t.ink, va="center", family=list(t.title_font), weight="bold", zorder=4)
    fig.text(0.062, 0.903, lay.text("header.subtitle"), fontsize=11.5, color=t.muted, va="center", zorder=4)
    fig.text(0.94, 0.941, lay.text("header.date"), fontsize=13, color=t.ink, va="center", ha="right", weight="semibold", zorder=4)
    fig.text(0.94, 0.909, lay.text("header.time"), fontsize=11.5, color=t.muted, va="center", ha="right", zorder=4)
    fig.text(0.04, 0.858, lay.text("header.info_line"), fontsize=10.5, color=t.muted, va="center")


def social_footer(fig, t: Theme, lay: Layout) -> None:
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
        fig.add_artist(Rectangle((xx, yy - 0.008), 0.016, 0.016, transform=fig.transFigure, fc=col, ec=t.ink, lw=min(t.lw(1.1), 1.2), zorder=6))
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
