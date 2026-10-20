"""Publication figure: L-band vs S-band over the same ROI (two composites, HH scatter, HV SNR distributions)."""
from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

from satviz.config import Scene
from satviz.drawing import scalebar
from satviz.geo import utm_extent
from satviz.layout import Layout, build_context
from satviz.recipes.sar_fcc import fcc_rgba, shared_lims
from satviz.sensors.nisar_gcov.processing import coarsen, db, stats

log = logging.getLogger(__name__)
FILENAME = "{scene}_LvsS_Publication.png"
INK, GRAY = "#1A1A1A", "#666666"
CL, CS = "#c9791a", "#1f8a7e"  # L and S series colours
RC = {"font.family": "serif", "font.serif": ["DejaVu Serif", "Liberation Serif"], "font.size": 7.5, "axes.linewidth": 0.6}


def render(scene: Scene, bands: dict, out_dir: Path, layout: dict, k: int = 3) -> list[Path]:
    """Panels use k x k block means of linear power; the colour stretch is pooled over both bands.
    The caption and credit come from `layout` (legacy/layouts/ls_publication.toml); facts come from the file metadata."""
    S, L = bands["S"], bands["L"]
    sS, sL = stats(S), stats(L)
    cS, cL = coarsen(S, k), coarsen(L, k)
    lims = shared_lims([cS, cL])
    rS, rL = fcc_rgba(cS, lims_in=lims)[0], fcc_rgba(cL, lims_in=lims)[0]
    ext = utm_extent(cS)

    # HH joint distribution on pixels where both bands clear the 3 dB HH SNR threshold
    both = cS["valid"] & cL["valid"] & ~cS["noisy_hh"] & ~cL["noisy_hh"]
    hS, hL = db(cS["hh"][both]), db(cL["hh"][both])
    r = float(np.corrcoef(hS, hL)[0, 1])
    dmed = float(np.median(hL - hS))
    nboth = int(both.sum())
    nval = int((cS["valid"] & cL["valid"]).sum())
    log.info("HH L vs S: r=%.3f, median L-S=%.2f dB, both-valid=%.1f%%", r, dmed, 100 * nboth / nval)
    lay = Layout(layout, build_context(scene, bands, {"S": sS, "L": sL}, per_band=False,
                                       extra={"k": k, "block_m": k * bands["S"]["meta"].posting_m, "both_pct": 100 * nboth / nval}))
    crs = lay.ctx["crs"]
    spec_l, spec_s = lay.ctx["L"], lay.ctx["S"]

    with plt.rc_context(RC):
        fig, axes = plt.subplots(2, 2, figsize=(7.2, 8.3), facecolor="white")
        fig.subplots_adjust(left=0.085, right=0.965, top=0.965, bottom=0.22, wspace=0.22, hspace=0.20)
        xt = np.arange(np.ceil(ext[0] / 10000) * 10000, ext[1], 10000)
        yt = np.arange(np.ceil(ext[2] / 10000) * 10000, ext[3], 10000)

        def mapax(ax, img, title):
            ax.imshow(img, extent=ext, origin="upper", interpolation="nearest")
            ax.set_title(title, fontsize=8, loc="left", weight="bold")
            ax.set_xlim(ext[0], ext[1])
            ax.set_ylim(ext[2], ext[3])
            ax.set_xticks(xt)
            ax.set_yticks(yt)
            ax.set_xticklabels([f"{v / 1000:.0f}" for v in xt])
            ax.set_yticklabels([f"{v / 1000:.0f}" for v in yt], rotation=90, va="center")
            ax.tick_params(labelsize=6, length=2, width=0.5)

        mapax(axes[0, 0], rL, f"(a) L-band ({spec_l.freq_ghz:g} GHz, ≈{spec_l.wavelength_cm:.0f} cm)")
        mapax(axes[0, 1], rS, f"(b) S-band ({spec_s.freq_ghz:g} GHz, ≈{spec_s.wavelength_cm:.0f} cm)")
        axes[0, 0].text(0.02, 0.03, f"R  HH {lims['HH'][0]:.0f} to {lims['HH'][1]:.0f} dB\nG  HV {lims['HV'][0]:.0f} to {lims['HV'][1]:.0f} dB\n"
                        f"B  HH−HV {lims['ratio'][0]:.0f} to {lims['ratio'][1]:.0f} dB\ngrey: HV SNR < 3 dB", transform=axes[0, 0].transAxes,
                        fontsize=5.8, color="white", va="bottom", linespacing=1.3, bbox=dict(fc="black", ec="none", alpha=0.7, pad=2.5))
        axes[0, 0].set_ylabel("Northing (km)", fontsize=7)
        axes[0, 1].set_yticklabels([])
        scalebar(axes[0, 0], ext, 5, y_frac=0.93, x_frac=0.60, fs=6.5)
        axes[0, 1].text(0.97, 0.03, "same pixels as (a)", transform=axes[0, 1].transAxes, fontsize=6, color="white", ha="right",
                        bbox=dict(fc="black", ec="none", alpha=0.7, pad=1.5))
        for a in axes[0]:
            a.set_xlabel(f"Easting, {crs} (km)", fontsize=7)

        # (c) HH L vs S
        ax = axes[1, 0]
        ax.hist2d(hS, hL, bins=110, range=[[-32, 6], [-32, 6]], norm=LogNorm(), cmap="Greys", rasterized=True)
        ax.plot([-32, 6], [-32, 6], color="#d9531e", lw=0.7, ls="--")
        ax.set_xlim(-32, 6)
        ax.set_ylim(-32, 6)
        ax.set_aspect("equal")
        ax.set_xlabel("S-band HH γ⁰ (dB, provisional)", fontsize=7)
        ax.set_ylabel("L-band HH γ⁰ (dB)", fontsize=7)
        ax.set_title("(c) HH, L vs S", fontsize=8, loc="left", weight="bold")
        ax.text(0.03, 0.97, f"r = {r:.2f}\nmedian L−S = {dmed:+.1f} dB\nn = {nboth:,} px", transform=ax.transAxes, fontsize=6.3, va="top",
                bbox=dict(fc="white", ec="none", alpha=0.8, pad=1.5))
        ax.tick_params(labelsize=6, length=2, width=0.5)

        # (d) HV SNR distributions
        ax = axes[1, 1]
        bins = np.linspace(-10, 25, 71)
        for d_, col, name, sd in ((cL, CL, "L", sL), (cS, CS, "S", sS)):
            v = d_["snr_hv"][d_["valid"]]
            ax.hist(np.clip(v, -10, 25), bins=bins, density=True, histtype="step", color=col, lw=1.1,
                    label=f"{name}-band ({100 * sd['noisy_hv_frac_of_valid']:.0f}% < 3 dB)")
        ax.axvline(3.0, color=INK, lw=0.6, ls=":")
        ax.set_xlabel(f"HV SNR (dB), {lay.ctx['posting_m']} m NEBS/η noise floor", fontsize=7)
        ax.set_ylabel("Density", fontsize=7)
        ax.set_title("(d) HV signal-to-noise ratio", fontsize=8, loc="left", weight="bold")
        ax.legend(fontsize=6.3, frameon=False, loc="upper right")
        ax.tick_params(labelsize=6, length=2, width=0.5)

        cap = " ".join(lay.lines("figure.caption"))
        fig.text(0.085, 0.172, "\n".join(textwrap.wrap(cap, 128)), fontsize=6.0, va="top", ha="left", color=INK)
        fig.text(0.085, 0.012, lay.text("figure.credit"), fontsize=6, color=GRAY)
        png = Path(out_dir) / FILENAME.format(scene=f"NISAR_{scene.name}")
        pdf = png.with_suffix(".pdf")
        fig.savefig(png, dpi=300, facecolor="white")
        fig.savefig(pdf, facecolor="white", dpi=300)
        plt.close(fig)
    return [png, pdf]
