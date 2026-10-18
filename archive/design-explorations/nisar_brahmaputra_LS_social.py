#!/usr/bin/env python3
"""L-band vs S-band split-view, retro-space social graphic (4:5): 70s/80s space-programme look (deep-space navy, mission patch,
orbit lines, shuttle-stripe band) with subtle neo-brutal structure (bento grid, hard offset shadows).
Data panels are never styled. Usage: python3 nisar_brahmaputra_LS_social.py [outdir]
"""
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Ellipse
from matplotlib.transforms import offset_copy
from nisar_brahmaputra_pipeline import load_roi, fcc_rgba, shared_lims, stats, HERE
from nisar_brahmaputra_figures import utm_extent

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


# Zoom windows (rows, cols in the 10 m ROI grid): 300 x 780 px = 3.0 x 7.8 km each
ZOOMS = (("A", "HILL EDGE", (520, 820), (560, 1340)),
         ("B", "SAND BARS", (2500, 2800), (1200, 1980)),
         ("C", "SOUTH BANK", (2600, 2900), (2000, 2780)))


def render():
    S, L = load_roi("S"), load_roi("L")
    sS, sL = stats(S), stats(L)
    lims = shared_lims([S, L])
    rS, rL = fcc_rgba(S, lims_in=lims)[0], fcc_rgba(L, lims_in=lims)[0]
    ext = utm_extent(S)
    H, W = rS.shape[:2]
    split = W // 2
    hero = rL.copy(); hero[:, split:] = rS[:, split:]
    xsplit = ext[0] + (ext[1] - ext[0]) * split / W

    fig = plt.figure(figsize=(12, 15), facecolor=SPACE)
    bg = fig.add_axes([0, 0, 1, 1], zorder=-10); bg.axis("off"); bg.set_xlim(0, 1); bg.set_ylim(0, 1)
    rng = np.random.default_rng(7)
    n = 380
    bg.scatter(rng.random(n), rng.random(n), s=rng.choice([0.6, 1.2, 2.4], n, p=[.6, .3, .1]), c=CREAM,
               alpha=rng.uniform(.25, .8, n), lw=0)
    for k, (w, h, a) in enumerate(((1.5, 0.30, -8), (1.9, 0.42, -8))):
        bg.add_patch(Ellipse((0.86, 0.935), w, h, angle=a, fc="none", ec=CREAM, lw=0.8, alpha=0.34 - 0.1 * k))

    def stripes(y, h=0.0028, x=0.04, w=0.92):
        for i, col in enumerate((RED, ORG, AMB, CYAN)):
            fig.add_artist(Rectangle((x, y + (3 - i) * h), w, h, transform=fig.transFigure, fc=col, ec="none", zorder=3))

    # Header
    block(fig, 0.04, 0.885, 0.92, 0.09)
    for dx, col in ((3.6, RED), (1.8, ORG)):
        fig.text(0.06, 0.945, "ONE RIVER, TWO RADARS", fontsize=36, color=col, va="center", weight="bold",
                 transform=offset_copy(fig.transFigure, fig=fig, x=dx, y=-dx, units="points"), zorder=3)
    fig.text(0.06, 0.945, "ONE RIVER, TWO RADARS", fontsize=36, color=CREAM, va="center", weight="bold", zorder=4)
    fig.text(0.062, 0.903, "THE BRAHMAPUTRA IN NISAR'S L-BAND AND S-BAND, SAME PASS", fontsize=13, color=AMB, va="center", zorder=4)
    bsz = 0.082
    bd = fig.add_axes([0.955 - 0.012 - bsz * 15 / 12, 0.8905, bsz * 15 / 12, bsz], zorder=5)
    bd.set_aspect("equal"); bd.set_xlim(-1.08, 1.08); bd.set_ylim(-1.08, 1.08); bd.axis("off")
    disc = Circle((0, 0), 1, fc=SPACE, ec=CREAM, lw=1.8); bd.add_patch(disc)
    for p in ((-.55, .55), (.5, .7), (.15, .35), (-.2, .8), (.7, .2)):
        bd.plot(*p, ".", ms=2.5, color=CREAM)
    planet = Circle((0, -0.95), 0.95, fc="#2c5db8", ec=CYAN, lw=1.4); planet.set_clip_path(disc); bd.add_patch(planet)
    bd.add_patch(Ellipse((0, 0.0), 2.0, 0.62, angle=18, fc="none", ec=AMB, lw=1.6))
    th = np.deg2rad(40); ca, sa = np.cos(np.deg2rad(18)), np.sin(np.deg2rad(18))
    ex, ey = np.cos(th), np.sin(th) * 0.31
    bd.plot(ex * ca - ey * sa, ex * sa + ey * ca, "o", ms=6, mfc=CREAM, mec=SPACE, mew=1)
    bd.add_patch(Circle((0, 0), 0.9, fc="none", ec=CREAM, lw=0.7, alpha=0.6))
    stripes(0.8715)
    x = 0.04
    for t, col, tc in (("NASA-ISRO NISAR", CYAN, SPACE), ("L ≈24 CM · S ≈9 CM", AMB, SPACE),
                       ("25 SEP 2026 · 22:57 UTC", PANEL, CREAM), ("HH/HV · 10 M", PANEL, CREAM)):
        x = tag(fig, x, 0.853, t, col, tc=tc)

    # Hero: L-band left, S-band right, same pixels
    hy, hw, hx = 0.255, 0.677, 0.04
    hh = hw * 12 / 15 * (H / W)
    ax = img_axes(fig, hx, hy, hw, hh, sh=RED)
    ax.imshow(hero, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
    ax.set_xticks(np.arange(np.ceil(ext[0] / 5000) * 5000, ext[1], 5000)); ax.set_yticks(np.arange(np.ceil(ext[2] / 5000) * 5000, ext[3], 5000))
    ax.tick_params(direction="in", length=7, width=1.3, top=True, right=True, labelbottom=False, labelleft=False, colors=CREAM)
    ax.axvline(xsplit, color=CREAM, lw=2.2, zorder=12)
    ax.text(xsplit, ext[2] + 0.5 * (ext[3] - ext[2]), "◄ L   S ►", ha="center", va="center", fontsize=11, color=SPACE, zorder=13,
            bbox=dict(boxstyle="square,pad=0.45", fc=CREAM, ec=SPACE, lw=1.2))
    xx0 = lambda c: ext[0] + (ext[1] - ext[0]) * c / W
    yy0 = lambda r: ext[3] - (ext[3] - ext[2]) * r / H
    for key, _, (r0, r1), (c0, c1) in ZOOMS:
        ax.add_patch(Rectangle((xx0(c0), yy0(r1)), xx0(c1) - xx0(c0), yy0(r0) - yy0(r1), fc="none", ec=CREAM, lw=1.4, zorder=11))
        ax.text(xx0(c0), yy0(r0) + 0.006 * (ext[3] - ext[2]), key, ha="left", va="bottom", fontsize=10.5, color=SPACE, zorder=13,
                bbox=dict(boxstyle="square,pad=0.2", fc=CREAM, ec=SPACE, lw=1.0))
    x0 = ext[0] + 0.05 * (ext[1] - ext[0]); y0 = ext[2] + 0.05 * (ext[3] - ext[2])
    for i in range(5):
        ax.add_patch(Rectangle((x0 + i * 1000, y0), 1000, 700, fc=SPACE if i % 2 == 0 else CREAM, ec=CREAM, lw=1.0, zorder=14))
    ax.text(x0 + 2500, y0 + 1100, "5 KM", ha="center", fontsize=12, color=SPACE, zorder=15,
            bbox=dict(boxstyle="square,pad=0.2", fc=CREAM, ec=SPACE, lw=1.0))
    fig.text(hx + 0.012, hy + hh - 0.014, "L-BAND  ≈24 CM", fontsize=11, color=SPACE, va="top", zorder=20,
             bbox=dict(boxstyle="square,pad=0.35", fc=AMB, ec=SPACE, lw=1.2))
    fig.text(hx + hw - 0.012, hy + hh - 0.014, "S-BAND  ≈9 CM", fontsize=11, color=SPACE, va="top", ha="right", zorder=20,
             bbox=dict(boxstyle="square,pad=0.35", fc=CYAN, ec=SPACE, lw=1.2))

    # Zoom cells: L above S for each window
    px, pw = hx + hw + 0.02, 0.96 - (hx + hw + 0.02)
    gap, lab = 0.009, 0.019
    ch = (hh - 2 * gap) / 3
    ih = (ch - lab) / 2
    for i, (key, name, (r0, r1), (c0, c1)) in enumerate(ZOOMS):
        top = hy + hh - i * (ch + gap)
        fig.text(px + 0.006, top - lab / 2, f"{key}  {name}", fontsize=10.5, color=AMB, va="center", zorder=20)
        for j, (rg, bandname, col) in enumerate(((rL, "L", AMB), (rS, "S", CYAN))):
            py = top - lab - (j + 1) * ih
            a = img_axes(fig, px, py, pw, ih - (0.003 if j == 0 else 0))
            a.imshow(rg[r0:r1, c0:c1], aspect="auto", interpolation="antialiased")
            fig.text(px + 0.006, py + ih - 0.009, bandname, fontsize=10, color=SPACE, va="top", zorder=20,
                     bbox=dict(boxstyle="square,pad=0.25", fc=col, ec=SPACE, lw=1.0))

    # How to read
    block(fig, 0.04, 0.135, 0.92, 0.095)
    for i, col in enumerate((RED, ORG, AMB, CYAN)):
        fig.add_artist(Rectangle((0.04 + i * 0.0045, 0.135), 0.0045, 0.095, transform=fig.transFigure, fc=col, ec="none", zorder=3))
    fig.text(0.067, 0.213, "HOW TO READ  ·  SAME COLOURS AND STRETCH IN BOTH BANDS", fontsize=11, color=AMB, va="center")
    items = [("#d4574f", "RED = HH  (SURFACE)"), ("#5fb673", "GREEN = HV  (VOLUME)"), ("#6580d6", "BLUE = HH−HV  (RATIO)"),
             ("#a05cb5", "PURPLE = HV LOW, SURFACE-LIKE"), ("#a8c25c", "LIME = HV HIGH, VOLUME-LIKE"),
             (GREY, f"GREY = NOISE (HV: L {100 * sL['noisy_hv_frac_of_valid']:.0f}% · S {100 * sS['noisy_hv_frac_of_valid']:.0f}%)")]
    for i, (col, t) in enumerate(items):
        xx = 0.067 + (i % 3) * 0.298
        yy = 0.188 - (i // 3) * 0.0265
        fig.add_artist(Rectangle((xx, yy - 0.008), 0.016, 0.016, transform=fig.transFigure, fc=col, ec=CREAM, lw=1.0, zorder=6))
        fig.text(xx + 0.024, yy, t, fontsize=9.6, color=CREAM, va="center", zorder=6)

    # Honesty strip + credits
    block(fig, 0.04, 0.072, 0.92, 0.047, SPACE, shadow=False, lw=1.0)
    fig.text(0.05, 0.1075, "S-BAND CALIBRATION METADATA NOT YET POPULATED: S-BAND dB VALUES ARE PROVISIONAL AND RELATIVE.",
             fontsize=9.3, color=AMB, va="center")
    fig.text(0.05, 0.0835, "L-BAND SCALE FACTORS ARE PRESENT. BOTH BANDS: NOISE-SCREENED (SNR < 3 dB GREY), NO SPECKLE FILTER.",
             fontsize=9.3, color=AMB, va="center")
    fig.text(0.04, 0.052, "DATA  NISAR L2 GCOV, L-SAR + S-SAR · TRACK 112 · FRAME 16 · ASC · γ⁰ · UTM 46N, TICKS 5 KM",
             fontsize=9, color=DIM, va="center")
    stripes(0.0075)
    fig.text(0.04, 0.032, "VIZ   SARAT (NRSC/ISRO)  ·  www.carbform.github.io", fontsize=9, color=DIM, va="center")

    p = os.path.join(OUT, "NISAR_Brahmaputra_LvsS_Social.png")
    fig.savefig(p, dpi=180, facecolor=SPACE)
    plt.close(fig)
    return p


if __name__ == "__main__":
    print(render())
