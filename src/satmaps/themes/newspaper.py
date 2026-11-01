"""Newspaper: crisp white newsprint paper, classic newspaper serif typography, ruled columns instead of boxes.
Inspired by the structure of a printed broadsheet (kicker, headline, dek, hairline rules, key, notes and a source line).
"""
from __future__ import annotations

from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from satmaps.core import theme
from satmaps.themes.base import Theme, installed

SERIF = installed("Times New Roman", "Times", "Liberation Serif", "PT Serif", "Source Serif Pro", "DejaVu Serif")


def _rule(fig, t: Theme, y: float, x0: float = 0.04, x1: float = 0.96, width: float = 0.8) -> None:
    fig.add_artist(Line2D([x0, x1], [y, y], transform=fig.transFigure, color=t.ink, lw=t.lw(width), solid_capstyle="butt", zorder=3))


class NewspaperChrome:
    """Header as kicker, headline and dek between rules; every other block as a pair of hairlines (a tinted strip for notes)."""

    @staticmethod
    def header(fig, t: Theme, lay) -> None:
        _rule(fig, t, 0.972, width=3.4)
        _rule(fig, t, 0.9665, width=0.8)
        fig.text(0.04, 0.9515, lay.text("header.subtitle"), fontsize=10.5, color=t.muted, va="center", weight="bold",
                 family=list(t.title_font), zorder=4)
        date = lay.text("header.date")
        when = lay.text("header.time")
        fig.text(0.96, 0.9515, f"{date}  ·  {when}" if when else date, fontsize=10.5, color=t.muted, va="center", ha="right",
                 weight="bold", family=list(t.title_font), zorder=4)
        fig.text(0.04, 0.9115, lay.text("header.title"), fontsize=t.title_size, color=t.ink, va="center",
                 family=list(t.title_font), weight="bold", zorder=4)
        fig.text(0.04, 0.8755, lay.text("header.info_line"), fontsize=10.5, color=t.muted, va="center", style="italic",
                 family=list(t.body_font), zorder=4)
        _rule(fig, t, 0.859, width=0.8)

    @staticmethod
    def block(fig, t: Theme, x, y, w, h, fc=None, lw=1.5, shadow=True) -> None:
        if fc and fc != t.card:  # the notice strip is a tinted band
            fig.add_artist(Rectangle((x, y), w, h, transform=fig.transFigure, fc=fc, ec="none", zorder=1))
        _rule(fig, t, y + h, x, x + w, 0.8)
        _rule(fig, t, y, x, x + w, 0.5)


NEWSPAPER = theme("newspaper")(Theme(
    name="newspaper", tag="Newspaper", paper="#ffffff", card="#ffffff", ink="#111111", muted="#505050",
    chip_a="#e6e6e6", chip_b="#dadada", note="#f2f2f2",
    title_font=SERIF, body_font=SERIF, title_size=42, line_scale=0.5, chrome=NewspaperChrome(),
))
