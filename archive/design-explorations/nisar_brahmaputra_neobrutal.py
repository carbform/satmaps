#!/usr/bin/env python3
"""Neo-brutalist bento social graphic (4:5) for the Brahmaputra S-band scene.

Palette is carried over from the earlier visualize_river.py attempt. Data come from the
shared, noise-screened pipeline. Usage: python3 nisar_brahmaputra_neobrutal.py [outdir]
"""
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle
from nisar_brahmaputra_pipeline import load_roi, coarsen, fcc_rgba, db, stats, HERE
from nisar_brahmaputra_figures import utm_extent, to_xy, CALLOUTS

OUT = sys.argv[1] if len(sys.argv) > 1 else HERE
BG, PINK, TEAL, BLUE, WHITE, INK = "#ece6d8", "#d49a86", "#a9c2b3", "#9db3c2", "#faf7ef", "#1f1f1f"
GREY = "#3a3a40"
SHX, SHY = 0.003, -0.0024  # hard shadow offset, figure fraction
plt.rcParams.update({"font.family": "DejaVu Sans Mono", "font.weight": "normal"})


def block(fig, x, y, w, h, fc, lw=1.6, shadow=True):
    if shadow:
        fig.add_artist(Rectangle((x + SHX, y + SHY), w, h, transform=fig.transFigure, fc=INK, ec=INK, lw=0, zorder=0))
    fig.add_artist(Rectangle((x, y), w, h, transform=fig.transFigure, fc=fc, ec=INK, lw=lw, zorder=1))


def tag(fig, x, y, text, fc, fs=15, pad=0.012):
    t = fig.text(x + pad, y, text, fontsize=fs, color=INK, va="center", ha="left", zorder=5)
    fig.canvas.draw()
    bb = t.get_window_extent().transformed(fig.transFigure.inverted())
    block(fig, x, y - bb.height / 2 - 0.006, bb.width + 2 * pad, bb.height + 0.012, fc, lw=1.4)
    return x + bb.width + 2 * pad + 0.015


def img_axes(fig, x, y, w, h, shadow=True):
    if shadow:
        fig.add_artist(Rectangle((x + SHX, y + SHY), w, h, transform=fig.transFigure, fc=INK, lw=0, zorder=0))
    ax = fig.add_axes([x, y, w, h], zorder=2)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(1.6); s.set_color(INK)
    return ax


def sticker(ax, text, xy, xytext, fc=WHITE):
    ax.annotate(text, xy, xytext=xytext, textcoords="offset points", fontsize=11.5, color=INK, zorder=12,
                bbox=dict(boxstyle="square,pad=0.45", fc=fc, ec=INK, lw=1.4),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.5, shrinkA=0, shrinkB=2, mutation_scale=13))
    ax.plot(*xy, "o", ms=7, mfc=fc, mec=INK, mew=1.5, zorder=11)


def render():
    d = load_roi()
    s = stats(d)
    rgba, lims, ok = fcc_rgba(d)
    c = coarsen(d, 4)
    ext = utm_extent(d)
    cext = utm_extent(c)

    fig = plt.figure(figsize=(12, 15), facecolor=BG)

    # Header
    block(fig, 0.04, 0.885, 0.92, 0.09, WHITE)
    fig.text(0.06, 0.945, "THE BRAHMAPUTRA", fontsize=42, color=INK, va="center", weight="bold")
    fig.text(0.06, 0.905, "SEEN BY NISAR'S S-BAND RADAR", fontsize=16, color=INK, va="center")
    x = 0.04
    for t, col in (("NASA-ISRO NISAR", TEAL), ("10 M PIXELS", PINK), ("25 SEP 2026 · 22:58 UTC", BLUE), ("S-BAND · HH/HV", WHITE)):
        x = tag(fig, x, 0.855, t, col, fs=12)

    # Hero: false-colour composite (left) + the three bands it is built from (right)
    hy, hw = 0.255, 0.677
    hx = 0.04
    hh = hw * 12 / 15 * (rgba.shape[0] / rgba.shape[1])
    ax = img_axes(fig, hx, hy, hw, hh)
    ax.imshow(rgba, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
    sticker(ax, "SIMEN RIVER\njoins the\nBrahmaputra", to_xy(d, *CALLOUTS["simen"]), (-95, 75))
    sticker(ax, "SAND BARS", to_xy(d, *CALLOUTS["bars"]), (-40, -60), fc=TEAL)
    x0 = ext[0] + 0.05 * (ext[1] - ext[0]); y0 = ext[2] + 0.05 * (ext[3] - ext[2])
    for i in range(5):
        ax.add_patch(Rectangle((x0 + i * 1000, y0), 1000, 700, fc=INK if i % 2 == 0 else WHITE, ec=INK, lw=1.2, zorder=14))
    ax.text(x0 + 2500, y0 + 1100, "5 KM", ha="center", fontsize=12, color=INK, zorder=15,
            bbox=dict(boxstyle="square,pad=0.2", fc=WHITE, ec=INK, lw=1.2))
    fig.text(hx + 0.012, hy + hh - 0.014, "FALSE COLOUR COMPOSITE", fontsize=11, color=INK, va="top", zorder=20,
             bbox=dict(boxstyle="square,pad=0.35", fc=PINK, ec=INK, lw=1.4))

    # RGB bands, each tinted in its channel colour. Noise-dominated pixels stay dark in every band.
    CH = {"R": "#d4574f", "G": "#5fb673", "B": "#6580d6"}
    hh_db_, hv_db_ = db(c["hh"]), db(c["hv_ns"])
    okc = c["valid"] & ~c["noisy_hv"] & np.isfinite(hv_db_)
    bands = (("R", "HH", hh_db_, lims["HH"], 0.94), ("G", "HV", hv_db_, lims["HV"], 0.94),
             ("B", "HH−HV", hh_db_ - hv_db_, lims["ratio"], 1.05))
    px, pw = hx + hw + 0.02, 0.96 - (hx + hw + 0.02)
    gap = 0.009
    ph = (hh - 2 * gap) / 3
    for i, (ch, name, arr, (lo, hi), gam) in enumerate(bands):
        v = np.where(okc, np.power(np.clip((arr - lo) / (hi - lo), 0, 1), gam), np.nan)
        tint = np.array([int(CH[ch][k:k + 2], 16) for k in (1, 3, 5)]) / 255.0
        img = np.where(np.isfinite(v)[..., None], v[..., None] * tint, 0.12)
        py = hy + hh - (i + 1) * ph - i * gap
        a = img_axes(fig, px, py, pw, ph)
        a.imshow(img, extent=cext, origin="upper", aspect="auto", interpolation="nearest")
        fig.text(px + 0.008, py + ph - 0.01, f"{ch}  {name}", fontsize=10.5, color=INK, va="top", zorder=20,
                 bbox=dict(boxstyle="square,pad=0.3", fc=CH[ch], ec=INK, lw=1.4))

    # How to read
    block(fig, 0.04, 0.135, 0.92, 0.095, WHITE)
    fig.text(0.055, 0.213, "HOW TO READ", fontsize=11, color=INK, va="center")
    items = [(CH["R"], "RED = HH  (SURFACE)"), (CH["G"], "GREEN = HV  (VOLUME)"), (CH["B"], "BLUE = HH−HV  (RATIO)"),
             ("#a05cb5", "PURPLE = FIELDS · SAND"), ("#a8c25c", "LIME = FOREST · HILLS"),
             (GREY, f"DARK GREY = NOISE ({100 * s['noisy_hv_frac_of_valid']:.0f}% OF PX)")]
    for i, (col, t) in enumerate(items):
        xx = 0.055 + (i % 3) * 0.30
        yy = 0.188 - (i // 3) * 0.0265
        fig.add_artist(Rectangle((xx, yy - 0.008), 0.016, 0.016, transform=fig.transFigure, fc=col, ec=INK, lw=1.2, zorder=6))
        fig.text(xx + 0.024, yy, t, fontsize=10, color=INK, va="center", zorder=6)

    # Honesty strip + credits
    block(fig, 0.04, 0.083, 0.92, 0.036, BG, shadow=False)
    fig.text(0.05, 0.101, "RELATIVE BACKSCATTER: S-BAND CALIBRATION METADATA NOT YET POPULATED. dB VALUES PROVISIONAL.",
             fontsize=9.6, color=INK, va="center")
    fig.text(0.04, 0.052, "DATA  NISAR S-SAR L2 GCOV · TRACK 112 · FRAME 16 · ASCENDING · γ⁰ NOISE-SCREENED",
             fontsize=9, color=INK, va="center")
    fig.text(0.04, 0.030, "VIZ   SARAT (NRSC/ISRO)  ·  www.carbform.github.io", fontsize=9, color=INK, va="center")

    p = os.path.join(OUT, "NISAR_Brahmaputra_Social_NeoBrutal.png")
    fig.savefig(p, dpi=180, facecolor=BG)
    plt.close(fig)
    return p


if __name__ == "__main__":
    print(render())
