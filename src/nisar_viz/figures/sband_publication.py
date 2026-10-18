"""Publication figure for the S-band granule alone: HH, HV (noise-subtracted), false colour and HV SNR."""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.axes_grid1 import make_axes_locatable

from nisar_viz.chrome import scalebar
from nisar_viz.composite import fcc_rgba
from nisar_viz.config import Scene
from nisar_viz.geo import to_xy, utm_extent
from nisar_viz.layout import Layout, build_context
from nisar_viz.processing import coarsen, db, stats

FILENAME = "{scene}_Publication.png"
INK, GRAY = "#1A1A1A", "#666666"
FLAG = "#d9531e"
RC = {"font.family": "serif", "font.serif": ["DejaVu Serif", "Liberation Serif"], "font.size": 7.5, "axes.linewidth": 0.6}


def render(scene: Scene, bands: dict, out_dir: Path, layout: dict, k: int = 3) -> list[Path]:
    """Four panels; k x k block means (default 30 m) so speckle does not alias at figure size.
    The caption and credit come from `layout` (layouts/sband_publication.toml); facts come from the file metadata."""
    d = bands["S"]
    s = stats(d)
    lay = Layout(layout, build_context(scene, {"S": d}, {"S": s}, per_band=False, extra={"k": k, "block_m": k * d["meta"].posting_m}))
    c = coarsen(d, k)
    rgba, lims, _ = fcc_rgba(c)
    ext = utm_extent(c)

    with plt.rc_context(RC):
        fig, axes = plt.subplots(2, 2, figsize=(7.2, 8.7), facecolor="white")
        fig.subplots_adjust(left=0.085, right=0.915, top=0.965, bottom=0.215, wspace=0.28, hspace=0.20)

        def cbar(ax, im, label):
            cax = make_axes_locatable(ax).append_axes("right", size="4%", pad=0.06)
            cb = fig.colorbar(im, cax=cax, extend="both")
            cb.set_label(label, fontsize=7)
            cb.ax.tick_params(labelsize=6.5, width=0.5)
            return cb

        def gray_panel(ax, arr_db, lo, hi, title, label):
            cm = plt.get_cmap("gray").copy()
            cm.set_bad(FLAG)
            im = ax.imshow(np.ma.masked_invalid(arr_db), extent=ext, cmap=cm, vmin=lo, vmax=hi, origin="upper", interpolation="nearest")
            ax.set_title(title, fontsize=8, loc="left", weight="bold")
            cbar(ax, im, label)

        hh_lo, hh_hi = np.nanpercentile(db(c["hh_ns"]), [2, 98.5])
        gray_panel(axes[0, 0], db(c["hh_ns"]), hh_lo, hh_hi, "(a) HH  γ⁰, noise-subtracted", "dB")
        gray_panel(axes[0, 1], db(c["hv_ns"]), *lims["HV"], "(b) HV  γ⁰, noise-subtracted", "dB")
        for ax in axes[0]:
            ax.text(0.02, 0.03, "orange: SNR < 3 dB", transform=ax.transAxes, fontsize=6, color="white",
                    bbox=dict(fc=FLAG, ec="none", pad=1.5))
        axes[1, 0].imshow(rgba, extent=ext, origin="upper", interpolation="nearest")
        axes[1, 0].set_title("(c) False colour", fontsize=8, loc="left", weight="bold")
        axes[1, 0].text(0.02, 0.03, f"R  HH {lims['HH'][0]:.0f} to {lims['HH'][1]:.0f} dB\nG  HV {lims['HV'][0]:.0f} to {lims['HV'][1]:.0f} dB\n"
                        f"B  HH−HV {lims['ratio'][0]:.0f} to {lims['ratio'][1]:.0f} dB\ngrey: SNR < 3 dB", transform=axes[1, 0].transAxes,
                        fontsize=5.8, color="white", va="bottom", linespacing=1.3,
                        bbox=dict(fc="black", ec="none", alpha=0.7, pad=2.5))
        snr = np.clip(c["snr_hv"], -5, 20)
        im = axes[1, 1].imshow(snr, extent=ext, cmap="RdYlBu", vmin=-5, vmax=20, origin="upper", interpolation="nearest")
        axes[1, 1].contour(snr, levels=[3.0], colors="k", linewidths=0.35, extent=ext, origin="upper")
        axes[1, 1].set_title("(d) HV signal-to-noise ratio", fontsize=8, loc="left", weight="bold")
        cbar(axes[1, 1], im, "dB (line: 3 dB)")

        xt = np.arange(np.ceil(ext[0] / 10000) * 10000, ext[1], 10000)
        yt = np.arange(np.ceil(ext[2] / 10000) * 10000, ext[3], 10000)
        for ax in axes.ravel():
            ax.set_xlim(ext[0], ext[1])
            ax.set_ylim(ext[2], ext[3])
            ax.set_xticks(xt)
            ax.set_yticks(yt)
            ax.set_xticklabels([f"{v / 1000:.0f}" for v in xt])
            ax.set_yticklabels([f"{v / 1000:.0f}" for v in yt], rotation=90, va="center")
            ax.tick_params(labelsize=6, length=2, width=0.5)
            for lat, lon in scene.callouts.values():
                x, y = to_xy(d, lat, lon)
                ax.plot(x, y, "+", color="#ffd400" if ax is axes[0, 1] or ax is axes[0, 0] else "k", ms=5, mew=0.9)
        for ax in axes[1]:
            ax.set_xlabel(f"Easting, {lay.ctx['crs']} (km)", fontsize=7)
        for ax in axes[:, 0]:
            ax.set_ylabel("Northing (km)", fontsize=7)
        scalebar(axes[0, 0], ext, 5, y_frac=0.12, x_frac=0.05, fs=6.5)

        cap = " ".join(lay.lines("figure.caption"))
        fig.text(0.085, 0.165, "\n".join(textwrap.wrap(cap, 112)), fontsize=6.2, va="top", ha="left", color=INK)
        fig.text(0.085, 0.012, lay.text("figure.credit"), fontsize=6, color=GRAY)
        png = Path(out_dir) / FILENAME.format(scene=f"NISAR_{scene.name}")
        pdf = png.with_suffix(".pdf")
        fig.savefig(png, dpi=300, facecolor="white")
        fig.savefig(pdf, facecolor="white", dpi=300)
        plt.close(fig)
    return [png, pdf]
