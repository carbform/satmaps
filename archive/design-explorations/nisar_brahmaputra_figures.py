#!/usr/bin/env python3
"""Brahmaputra S-band figures: social graphic and publication figure.

Usage: python3 nisar_brahmaputra_figures.py [outdir]
Both are plotted in the product's UTM 46N grid (no resampling to lat/lon); callouts are
projected into it. Grid north differs from true north by ~0.9 deg here.
"""
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import ListedColormap
from matplotlib.patches import Rectangle
from nisar_brahmaputra_pipeline import load_roi, coarsen, fcc_rgba, db, stats, HERE

OUT = sys.argv[1] if len(sys.argv) > 1 else HERE
INK, GRAY = "#1A1A1A", "#666666"
CALLOUTS = {"simen": (27.591, 94.8725), "bars": (27.565, 94.905)}


def utm_extent(d):
    dx = abs(d["x"][1] - d["x"][0]) / 2
    dy = abs(d["y"][1] - d["y"][0]) / 2
    return [d["x"][0] - dx, d["x"][-1] + dx, d["y"][-1] - dy, d["y"][0] + dy]


def to_xy(d, lat, lon):
    return d["to_utm"].transform(lon, lat)


def scalebar(ax, ext, km, y_frac=0.045, x_frac=0.035, fs=10):
    x0 = ext[0] + x_frac * (ext[1] - ext[0])
    y0 = ext[2] + y_frac * (ext[3] - ext[2])
    ax.plot([x0, x0 + km * 1000], [y0, y0], color="white", lw=4.5, solid_capstyle="butt", zorder=15)
    ax.plot([x0, x0 + km * 1000], [y0, y0], color="black", lw=1.8, solid_capstyle="butt", zorder=16)
    ax.text(x0 + km * 500, y0 + 0.014 * (ext[3] - ext[2]), f"{km} km", ha="center", fontsize=fs,
            weight="bold", color="white", path_effects=[pe.withStroke(linewidth=2.5, foreground="black")], zorder=17)


def social(d, rgba, lims):
    ext = utm_extent(d)
    fig = plt.figure(figsize=(12, 13.6), facecolor="#07090e")
    ax = fig.add_axes([0.04, 0.135, 0.92, 0.855])
    ax.imshow(rgba, extent=ext, origin="upper", aspect="equal", interpolation="bilinear")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#222f46"); s.set_linewidth(1.8)
    ax.text(0.025, 0.965, "THE BRAHMAPUTRA", transform=ax.transAxes, ha="left", va="top", fontsize=17,
            weight="bold", color="white",
            bbox=dict(boxstyle="square,pad=0.7", fc="#06090e", ec="#3b82f6", lw=1.8, alpha=0.94), zorder=10)
    ax.text(0.025, 0.882, " NISAR S-band SAR (HH/HV)  |  10 m  |  25 Sep 2026 ", transform=ax.transAxes,
            ha="left", va="top", fontsize=9.5, weight="bold", color="#93c5fd",
            bbox=dict(boxstyle="square,pad=0.4", fc="#0b1329", ec="#1d4ed8", lw=1.0, alpha=0.92), zorder=10)
    for key, label, col, off, rad in (("simen", "SIMEN RIVER\nTributary joining the Brahmaputra", "#38bdf8", (-50, 35), -0.15),
                                      ("bars", "SAND BARS", "#f43f5e", (-55, -45), 0.15)):
        x, y = to_xy(d, *CALLOUTS[key])
        ax.plot(x, y, "o", ms=6.5, color=col, mec="white", mew=1.4, zorder=12)
        ax.annotate(label, (x, y), xytext=off, textcoords="offset points", fontsize=9.5, weight="bold",
                    color="white", bbox=dict(boxstyle="round,pad=0.45", fc="#0f172a", ec=col, lw=1.5, alpha=0.92),
                    arrowprops=dict(arrowstyle="->", color=col, lw=1.8, connectionstyle=f"arc3,rad={rad}"),
                    path_effects=[pe.withStroke(linewidth=2, foreground="black")], zorder=12)
    scalebar(ax, ext, 5)

    # Channel key + honest noise note
    y = 0.095
    items = [("#ff3b3b", f"R  HH γ⁰  {lims['HH'][0]:.0f} to {lims['HH'][1]:.0f} dB"),
             ("#2fd45a", f"G  HV γ⁰  {lims['HV'][0]:.0f} to {lims['HV'][1]:.0f} dB"),
             ("#4b6bff", f"B  HH − HV  {lims['ratio'][0]:.0f} to {lims['ratio'][1]:.0f} dB"),
             ("#3a3a40", "Grey: below noise floor (water)")]
    for xp, (c, t) in zip([0.04, 0.27, 0.50, 0.70], items):
        fig.add_artist(Rectangle((xp, y - 0.010), 0.011, 0.020, transform=fig.transFigure, fc=c, ec="white", lw=0.8))
        fig.text(xp + 0.015, y, t, fontsize=9, weight="semibold", color="#e2e8f0", va="center")
    fig.text(0.04, 0.055, "Relative backscatter: S-band calibration metadata not yet populated, so dB values are provisional.",
             fontsize=8.5, color="#94a3b8", va="center")
    fig.text(0.04, 0.020, "DATA: NASA-ISRO NISAR  |  S-SAR L2 GCOV, track 112, frame 16, ascending  |  RTC γ⁰, noise-floor screened",
             fontsize=9, color="#94a3b8", weight="bold")
    fig.text(0.96, 0.020, "VISUALIZATION: Sarat (NRSC / ISRO)", ha="right", fontsize=9, color="#cbd5e1", weight="bold")
    p = os.path.join(OUT, "NISAR_Brahmaputra_Social.png")
    fig.savefig(p, dpi=200, facecolor="#07090e")
    plt.close(fig)
    return p


def publication(d, K=3):
    """Four-panel figure. Panels use K x K block means (30 m) so speckle does not alias."""
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    import textwrap
    s = stats(d)
    c = coarsen(d, K)
    rgba, lims, ok = fcc_rgba(c)
    ext = utm_extent(c)
    plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif", "Liberation Serif"], "font.size": 7.5,
                         "axes.linewidth": 0.6})
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 8.7), facecolor="white")
    fig.subplots_adjust(left=0.085, right=0.915, top=0.965, bottom=0.215, wspace=0.28, hspace=0.20)
    FLAG = "#d9531e"

    def cbar(ax, im, label):
        cax = make_axes_locatable(ax).append_axes("right", size="4%", pad=0.06)
        cb = fig.colorbar(im, cax=cax, extend="both")
        cb.set_label(label, fontsize=7)
        cb.ax.tick_params(labelsize=6.5, width=0.5)
        return cb

    def gray_panel(ax, arr_db, lo, hi, title, label):
        cm = plt.get_cmap("gray").copy(); cm.set_bad(FLAG)
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
        ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
        ax.set_xticks(xt); ax.set_yticks(yt)
        ax.set_xticklabels([f"{v/1000:.0f}" for v in xt]); ax.set_yticklabels([f"{v/1000:.0f}" for v in yt], rotation=90, va="center")
        ax.tick_params(labelsize=6, length=2, width=0.5)
        for lat, lon in CALLOUTS.values():
            x, y = to_xy(d, lat, lon)
            ax.plot(x, y, "+", color="#ffd400" if ax is axes[0, 1] or ax is axes[0, 0] else "k", ms=5, mew=0.9)
    for ax in axes[1]:
        ax.set_xlabel("Easting, UTM 46N (km)", fontsize=7)
    for ax in axes[:, 0]:
        ax.set_ylabel("Northing (km)", fontsize=7)
    scalebar(axes[0, 0], ext, 5, y_frac=0.12, x_frac=0.05, fs=6.5)

    cap = (f"Figure. Braided Brahmaputra reach with the Simen confluence and sand bars (crosses), NISAR S-SAR L2 GCOV, "
           f"25 Sep 2026 22:58 UTC, ascending, 37.5 MHz HH/HV mode, 10 m posting, 16 looks; panels are {K}×{K} block means (30 m) of linear power. "
           f"Radiometric-terrain-corrected γ⁰ is shown; σ⁰ = η·γ⁰ with η = {s['eta_p1_p50_p99'][0]:.2f}–{s['eta_p1_p50_p99'][2]:.2f} (1st–99th percentile) here. "
           f"The product's noise-equivalent backscatter (HV median {s['nebs_hv_db_median']:.1f} dB, consistent with the < −20 dB design goal; documented as σ⁰-referenced, so divided by η to give a γ⁰ floor) was subtracted "
           f"where SNR ≥ 3 dB; {100*s['noisy_hv_frac_of_valid']:.0f}% of 10 m HV pixels fall below that threshold ({100*s['noisy_hv_frac_if_gamma_referenced']:.0f}% if the layer were γ⁰-referenced), mostly open water, and are not interpreted. "
           f"The processor applied no ionospheric or wet-tropospheric geolocation correction (S-band is ~5× less ionosphere-sensitive than L-band) and no "
           f"shadow/layover mask (terrain is flat here). Calibration scale factors in the product metadata are unpopulated, so absolute levels are provisional. "
           f"Colour limits: 2nd–98.5th percentiles.")
    fig.text(0.085, 0.165, "\n".join(textwrap.wrap(cap, 112)), fontsize=6.2, va="top", ha="left", color=INK)
    fig.text(0.085, 0.012, "Data: NASA-ISRO NISAR, L2 GCOV (S-SAR), product spec 1.2.1, CRID P00500. Processing: Sarat (NRSC/ISRO).",
             fontsize=6, color=GRAY)
    p = os.path.join(OUT, "NISAR_Brahmaputra_Publication.png")
    fig.savefig(p, dpi=300, facecolor="white")
    fig.savefig(p.replace(".png", ".pdf"), facecolor="white", dpi=300)
    plt.close(fig)
    return p


if __name__ == "__main__":
    d = load_roi()
    rgba, lims, ok = fcc_rgba(d)
    print("limits", lims)
    print(social(d, rgba, lims))
    print(publication(d))
