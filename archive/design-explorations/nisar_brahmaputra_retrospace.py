#!/usr/bin/env python3
"""Retro-space social graphic (4:5): 70s/80s space-programme look (deep-space navy, mission patch,
orbit lines, shuttle-stripe band) with subtle neo-brutal structure (bento grid, hard offset shadows).
Data panels are never styled. Usage: python3 nisar_brahmaputra_retrospace.py [outdir]
"""
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Ellipse
from matplotlib.transforms import offset_copy
from nisar_brahmaputra_pipeline import load_roi, coarsen, fcc_rgba, db, stats, HERE
from nisar_brahmaputra_figures import utm_extent, to_xy, CALLOUTS

OUT = sys.argv[1] if len(sys.argv) > 1 else HERE
SPACE, PANEL, CREAM, DIM = "#0b1135", "#151d4d", "#f4ead2", "#9aa3c7"
RED, ORG, AMB, CYAN = "#e5533d", "#f08a3c", "#f4b942", "#5ec4d4"
SHADOW = "#2f43a6"
GREY = "#3a3a40"
SHX, SHY = 0.0045, -0.0036  # hard shadow offset, figure fraction
plt.rcParams.update({"font.family": "DejaVu Sans Mono", "font.weight": "normal"})


def block(fig, x, y, w, h, fc=PANEL, lw=1.3, shadow=True, sh=SHADOW):
    if shadow:
        fig.add_artist(Rectangle((x + SHX, y + SHY), w, h, transform=fig.transFigure, fc=sh, ec="none", zorder=0))
    fig.add_artist(Rectangle((x, y), w, h, transform=fig.transFigure, fc=fc, ec=CREAM, lw=lw, zorder=1))


def tag(fig, x, y, text, fc, tc=SPACE, fs=11.5, pad=0.012):
    t = fig.text(x + pad, y, text, fontsize=fs, color=tc, va="center", ha="left", zorder=5)
    fig.canvas.draw()
    bb = t.get_window_extent().transformed(fig.transFigure.inverted())
    block(fig, x, y - bb.height / 2 - 0.006, bb.width + 2 * pad, bb.height + 0.012, fc, lw=1.1, sh=SHADOW)
    return x + bb.width + 2 * pad + 0.015


def img_axes(fig, x, y, w, h, sh=SHADOW):
    fig.add_artist(Rectangle((x + SHX, y + SHY), w, h, transform=fig.transFigure, fc=sh, ec="none", zorder=0))
    ax = fig.add_axes([x, y, w, h], zorder=2)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(1.3); s.set_color(CREAM)
    return ax


def sticker(ax, text, xy, xytext, fc=CREAM):
    ax.annotate(text, xy, xytext=xytext, textcoords="offset points", fontsize=11.5, color=SPACE, zorder=12,
                bbox=dict(boxstyle="square,pad=0.45", fc=fc, ec=SPACE, lw=1.2),
                arrowprops=dict(arrowstyle="-|>", color=CREAM, lw=1.5, shrinkA=0, shrinkB=2, mutation_scale=13))
    ax.plot(*xy, "o", ms=7, mfc=fc, mec=SPACE, mew=1.5, zorder=11)


def render():
    d = load_roi()
    s = stats(d)
    rgba, lims, ok = fcc_rgba(d)
    c = coarsen(d, 4)
    ext = utm_extent(d)
    cext = utm_extent(c)

    fig = plt.figure(figsize=(12, 15), facecolor=SPACE)

    # Deep-space background: starfield + orbit lines (chrome only)
    bg = fig.add_axes([0, 0, 1, 1], zorder=-10); bg.axis("off"); bg.set_xlim(0, 1); bg.set_ylim(0, 1)
    rng = np.random.default_rng(7)
    n = 380
    sx, sy = rng.random(n), rng.random(n)
    bg.scatter(sx, sy, s=rng.choice([0.6, 1.2, 2.4], n, p=[.6, .3, .1]), c=CREAM, alpha=rng.uniform(.25, .8, n), lw=0)
    for k, (w, h, a) in enumerate(((1.5, 0.30, -8), (1.9, 0.42, -8))):
        bg.add_patch(Ellipse((0.86, 0.935), w, h, angle=a, fc="none", ec=CREAM, lw=0.8, alpha=0.34 - 0.1 * k))

    def stripes(y, h=0.0028, x=0.04, w=0.92):
        for i, col in enumerate((RED, ORG, AMB, CYAN)):
            fig.add_artist(Rectangle((x, y + (3 - i) * h), w, h, transform=fig.transFigure, fc=col, ec="none", zorder=3))

    # Header: title with two-step extrusion
    block(fig, 0.04, 0.885, 0.92, 0.09)
    for dx, col in ((3.6, RED), (1.8, ORG)):
        fig.text(0.06, 0.945, "THE BRAHMAPUTRA", fontsize=42, color=col, va="center", weight="bold",
                 transform=offset_copy(fig.transFigure, fig=fig, x=dx, y=-dx, units="points"), zorder=3)
    fig.text(0.06, 0.945, "THE BRAHMAPUTRA", fontsize=42, color=CREAM, va="center", weight="bold", zorder=4)
    fig.text(0.062, 0.903, "SEEN FROM ORBIT BY NISAR'S S-BAND RADAR", fontsize=14, color=AMB, va="center", zorder=4)

    # Mission patch: planet limb, orbit ring, satellite
    bsz = 0.082
    bd = fig.add_axes([0.955 - 0.012 - bsz * 15 / 12, 0.8905, bsz * 15 / 12, bsz], zorder=5)
    bd.set_aspect("equal"); bd.set_xlim(-1.08, 1.08); bd.set_ylim(-1.08, 1.08); bd.axis("off")
    disc = Circle((0, 0), 1, fc=SPACE, ec=CREAM, lw=1.8); bd.add_patch(disc)
    for p in ((-.55, .55), (.5, .7), (.15, .35), (-.2, .8), (.7, .2)):
        bd.plot(*p, ".", ms=2.5, color=CREAM)
    planet = Circle((0, -0.95), 0.95, fc="#2c5db8", ec=CYAN, lw=1.4); planet.set_clip_path(disc); bd.add_patch(planet)
    orb = Ellipse((0, 0.0), 2.0, 0.62, angle=18, fc="none", ec=AMB, lw=1.6); bd.add_patch(orb)
    th = np.deg2rad(40)
    ex, ey = np.cos(th) * 1.0, np.sin(th) * 0.31
    ca, sa = np.cos(np.deg2rad(18)), np.sin(np.deg2rad(18))
    bd.plot(ex * ca - ey * sa, ex * sa + ey * ca, "o", ms=6, mfc=CREAM, mec=SPACE, mew=1)
    bd.add_patch(Circle((0, 0), 0.9, fc="none", ec=CREAM, lw=0.7, alpha=0.6))
    stripes(0.8715)
    x = 0.04
    for t, col, tc in (("NASA-ISRO NISAR", CYAN, SPACE), ("10 M PIXELS", AMB, SPACE),
                       ("25 SEP 2026 · 22:58 UTC", PANEL, CREAM), ("S-BAND · HH/HV", PANEL, CREAM)):
        x = tag(fig, x, 0.853, t, col, tc=tc)

    # Hero: false-colour composite (left) + the three bands it is built from (right)
    hy, hw, hx = 0.255, 0.677, 0.04
    hh = hw * 12 / 15 * (rgba.shape[0] / rgba.shape[1])
    ax = img_axes(fig, hx, hy, hw, hh, sh=RED)
    ax.imshow(rgba, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
    ax.set_xticks(np.arange(np.ceil(ext[0] / 5000) * 5000, ext[1], 5000)); ax.set_yticks(np.arange(np.ceil(ext[2] / 5000) * 5000, ext[3], 5000))
    ax.tick_params(direction="in", length=7, width=1.3, top=True, right=True, labelbottom=False, labelleft=False, colors=CREAM)
    sticker(ax, "SIMEN RIVER\njoins the\nBrahmaputra", to_xy(d, *CALLOUTS["simen"]), (-95, 75))
    sticker(ax, "SAND BARS", to_xy(d, *CALLOUTS["bars"]), (-40, -60), fc=AMB)
    x0 = ext[0] + 0.05 * (ext[1] - ext[0]); y0 = ext[2] + 0.05 * (ext[3] - ext[2])
    for i in range(5):
        ax.add_patch(Rectangle((x0 + i * 1000, y0), 1000, 700, fc=SPACE if i % 2 == 0 else CREAM, ec=CREAM, lw=1.0, zorder=14))
    ax.text(x0 + 2500, y0 + 1100, "5 KM", ha="center", fontsize=12, color=SPACE, zorder=15,
            bbox=dict(boxstyle="square,pad=0.2", fc=CREAM, ec=SPACE, lw=1.0))
    fig.text(hx + 0.012, hy + hh - 0.014, "R+G+B  COMPOSITE", fontsize=11, color=SPACE, va="top", zorder=20,
             bbox=dict(boxstyle="square,pad=0.35", fc=AMB, ec=SPACE, lw=1.2))

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
        fig.text(px + 0.008, py + ph - 0.01, f"CH{i + 1}  {name}", fontsize=10.5, color=SPACE, va="top", zorder=20,
                 bbox=dict(boxstyle="square,pad=0.3", fc=CH[ch], ec=SPACE, lw=1.2))

    # How to read
    block(fig, 0.04, 0.135, 0.92, 0.095)
    for i, col in enumerate((RED, ORG, AMB, CYAN)):
        fig.add_artist(Rectangle((0.04 + i * 0.0045, 0.135), 0.0045, 0.095, transform=fig.transFigure, fc=col, ec="none", zorder=3))
    fig.text(0.067, 0.213, "HOW TO READ", fontsize=11, color=AMB, va="center")
    items = [(CH["R"], "RED = HH  (SURFACE)"), (CH["G"], "GREEN = HV  (VOLUME)"), (CH["B"], "BLUE = HH−HV  (RATIO)"),
             ("#a05cb5", "PURPLE = FIELDS · SAND"), ("#a8c25c", "LIME = FOREST · HILLS"),
             (GREY, f"DARK GREY = NOISE ({100 * s['noisy_hv_frac_of_valid']:.0f}% OF PX)")]
    for i, (col, t) in enumerate(items):
        xx = 0.067 + (i % 3) * 0.298
        yy = 0.188 - (i // 3) * 0.0265
        fig.add_artist(Rectangle((xx, yy - 0.008), 0.016, 0.016, transform=fig.transFigure, fc=col, ec=CREAM, lw=1.0, zorder=6))
        fig.text(xx + 0.024, yy, t, fontsize=10, color=CREAM, va="center", zorder=6)

    # Honesty strip + credits
    block(fig, 0.04, 0.083, 0.92, 0.036, SPACE, shadow=False, lw=1.0)
    fig.text(0.05, 0.101, "RELATIVE BACKSCATTER: S-BAND CALIBRATION METADATA NOT YET POPULATED. dB VALUES PROVISIONAL.",
             fontsize=9.6, color=AMB, va="center")
    fig.text(0.04, 0.056, "DATA  NISAR S-SAR L2 GCOV · TRACK 112 · FRAME 16 · ASCENDING · γ⁰ NOISE-SCREENED · UTM 46N, TICKS 5 KM",
             fontsize=9, color=DIM, va="center")
    stripes(0.0075)
    fig.text(0.04, 0.034, "VIZ   SARAT (NRSC/ISRO)  ·  www.carbform.github.io", fontsize=9, color=DIM, va="center")

    p = os.path.join(OUT, "NISAR_Brahmaputra_Social_RetroSpace.png")
    fig.savefig(p, dpi=180, facecolor=SPACE)
    plt.close(fig)
    return p


if __name__ == "__main__":
    print(render())
