"""L-band vs S-band, clean white layout: two large maps, compact header and a two-column footer."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from nisar_viz.chrome import scalebar
from nisar_viz.composite import fcc_rgba, shared_lims
from nisar_viz.config import Scene
from nisar_viz.geo import utm_extent
from nisar_viz.layout import Layout, build_context
from nisar_viz.processing import stats

FILENAME = "{scene}_LvsS_Clean.png"
INK, MUTED, RULE = "#14161a", "#5b616b", "#c9ccd2"
W, H = 14.0, 9.5  # inches
RC = {"font.family": ["IBM Plex Sans", "DejaVu Sans"], "font.size": 10, "text.color": INK,
      "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK}


def render(scene: Scene, bands: dict, out_dir: Path, layout: dict) -> list[Path]:
    """Wording comes from `layout` (layouts/ls_clean.toml); facts come from the file metadata."""
    S, L = bands["S"], bands["L"]
    sS, sL = stats(S), stats(L)
    lay = Layout(layout, build_context(scene, bands, {"S": sS, "L": sL}, per_band=False))
    lims = shared_lims([S, L])
    rS, rL = fcc_rgba(S, lims_in=lims)[0], fcc_rgba(L, lims_in=lims)[0]
    ext = utm_extent(S)
    xt = np.arange(np.ceil(ext[0] / 5000) * 5000, ext[1], 5000)
    yt = np.arange(np.ceil(ext[2] / 5000) * 5000, ext[3], 5000)

    with plt.rc_context(RC):
        fig = plt.figure(figsize=(W, H), facecolor="white")

        def fx(x):
            return x / W

        def fy(y):
            return y / H

        def text(x, y, s, **kw):
            return fig.text(fx(x), fy(y), s, **kw)

        def hline(y, x0=0.8, x1=13.72, color=RULE, lw=0.9):
            fig.add_artist(plt.Line2D([fx(x0), fx(x1)], [fy(y), fy(y)], transform=fig.transFigure, color=color, lw=lw))

        # Header
        text(0.8, 9.2, lay.text("header.title"), fontsize=21, weight="bold", va="center")
        text(0.8, 8.84, lay.text("header.subtitle"), fontsize=11.5, color=MUTED, va="center")
        text(13.72, 9.2, lay.text("header.date"), fontsize=12, weight="bold", ha="right", va="center")
        text(13.72, 8.84, lay.text("header.meta"), fontsize=11.5, color=MUTED, ha="right", va="center")
        hline(8.6, lw=1.4, color=INK)

        # Maps
        mw = (13.72 - 0.8 - 0.3) / 2
        mh = mw * (rS.shape[0] / rS.shape[1])
        my = 1.8
        panels = ((0.8, rL, lay.text("panels.L_label"), lay.text("panels.L_sub")),
                  (0.8 + mw + 0.3, rS, lay.text("panels.S_label"), lay.text("panels.S_sub")))
        for x0, img, band, sub in panels:
            ax = fig.add_axes([fx(x0), fy(my), fx(mw), fy(mh)])
            ax.imshow(img, extent=ext, origin="upper", interpolation="antialiased", aspect="auto")
            ax.set_xlim(ext[0], ext[1])
            ax.set_ylim(ext[2], ext[3])
            ax.set_xticks(xt)
            ax.set_yticks(yt)
            ax.set_xticklabels([f"{v / 1000:.0f}" for v in xt])
            ax.set_yticklabels([f"{v / 1000:.0f}" for v in yt] if x0 < 5 else [], rotation=90, va="center")
            ax.set_xlabel(f"Easting, {lay.ctx['crs']} (km)", fontsize=10, weight="semibold", labelpad=4)
            if x0 < 5:
                ax.set_ylabel("Northing (km)", fontsize=10, weight="semibold", labelpad=4)
            ax.tick_params(labelsize=9, length=3.5, width=0.8, pad=3)
            for s in ax.spines.values():
                s.set_linewidth(1.0)
                s.set_color(INK)
            ax.text(0.02, 0.985, band, transform=ax.transAxes, fontsize=14, weight="bold", color="white", va="top", ha="left",
                    bbox=dict(boxstyle="square,pad=0.45", fc="#000000", ec="none", alpha=0.78))
            ax.text(0.02, 0.925, sub, transform=ax.transAxes, fontsize=10.5, weight="semibold", color="white", va="top", ha="left",
                    bbox=dict(boxstyle="square,pad=0.35", fc="#000000", ec="none", alpha=0.78))
            scalebar(ax, ext, 5, y_frac=0.045, x_frac=0.04, fs=10)

        # Footer, two columns
        hline(1.3)
        text(0.8, 1.1, lay.text("footer.channels_title"), fontsize=10.5, weight="bold", va="center")
        text(0.8 + mw + 0.3, 1.1, lay.text("footer.quality_title"), fontsize=10.5, weight="bold", va="center")
        labels = lay.raw("footer.channel_labels")
        if len(labels) != 3:
            raise ValueError(f"{lay.path} [footer.channel_labels]: need exactly 3 labels (R, G, B)")
        chans = [("#d93636", labels[0], lims["HH"]), ("#2f9e4f", labels[1], lims["HV"]), ("#3b5bdb", labels[2], lims["ratio"])]
        for i, (col, label, (lo, hi)) in enumerate(chans):
            x = 0.8 + i * 2.1
            fig.add_artist(Rectangle((fx(x), fy(0.76)), fx(0.18), fy(0.18), transform=fig.transFigure, fc=col, ec=INK, lw=0.7))
            text(x + 0.26, 0.85, label, fontsize=10, weight="semibold", va="center")
            text(x + 0.26, 0.62, f"{lo:.0f} to {hi:.0f} dB", fontsize=9.3, color=MUTED, va="center")
        text(0.8, 0.30, lay.text("footer.legend_line"), fontsize=9.3, color=MUTED, va="center")
        x1 = 0.8 + mw + 0.3
        text(x1, 0.85, lay.text("footer.quality_line"), fontsize=10, weight="semibold", va="center")
        for note in lay.lines("footer.note", limit=1):
            text(x1, 0.62, note, fontsize=9.3, color=MUTED, va="center")
        text(x1, 0.30, lay.text("footer.credit"), fontsize=9.3, color=MUTED, va="center")

        out = Path(out_dir) / FILENAME.format(scene=f"NISAR_{scene.name}")
        fig.savefig(out, dpi=250, facecolor="white")
        plt.close(fig)
    return [out]
