"""L-band vs S-band social graphic (4:5): neo-retro chrome around a split-view hero and three zoom pairs."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from satviz.config import Scene
from satviz.core import THEMES
from satviz.geo import utm_extent
from satviz.layout import Layout, LayoutError, build_context
from satviz.recipes.sar_fcc import fcc_rgba, shared_lims
from satviz.registry import load_builtin
from satviz.sensors.nisar_gcov.processing import stats
from satviz.themes.base import chip, img_axes, social_footer, social_header

FILENAME = "{scene}_LvsS_Social_{tag}.png"


def render(scene: Scene, bands: dict, out_dir: Path, layout: dict, per_band: bool | None = None, theme: str = "neo_retro") -> list[Path]:
    """Wording comes from `layout` (layouts/ls_social.toml); facts come from the file metadata.

    `per_band` overrides `[style] stretch`: True stretches each band to its own percentiles (punchier S-band, colours
    not comparable), False uses one stretch pooled over both bands, as in the publication figure."""
    load_builtin()
    t = THEMES.get_or_raise(theme)
    S, L = bands["S"], bands["L"]
    if per_band is None:
        mode = layout.get("style", {}).get("stretch", "per-band")
        if mode not in ("per-band", "pooled"):
            raise LayoutError(f"{layout.get('_path')}: [style] stretch must be 'per-band' or 'pooled', not {mode!r}")
        per_band = mode == "per-band"
    sS, sL = stats(S), stats(L)
    lay = Layout(layout, build_context(scene, bands, {"S": sS, "L": sL}, per_band))
    lims = None if per_band else shared_lims([S, L])
    rS, rL = fcc_rgba(S, lims_in=lims)[0], fcc_rgba(L, lims_in=lims)[0]
    ext = utm_extent(S)
    H, W = rS.shape[:2]
    split = W // 2
    hero = rL.copy()
    hero[:, split:] = rS[:, split:]
    xsplit = ext[0] + (ext[1] - ext[0]) * split / W

    with plt.rc_context({"font.family": list(t.body_font), "font.weight": "normal"}):
        fig = plt.figure(figsize=(12, 15), facecolor=t.paper)

        social_header(fig, t, lay)

        # Hero: L-band left, S-band right, same pixels
        hy, hw, hx = 0.255, 0.677, 0.04
        hh = hw * 12 / 15 * (H / W)
        ax = img_axes(fig, t, hx, hy, hw, hh)
        ax.imshow(hero, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
        ax.axvline(xsplit, color=t.card, lw=t.lw(2.2), zorder=12)
        ax.text(xsplit, ext[2] + 0.5 * (ext[3] - ext[2]), "◄ L   S ►", ha="center", va="center", fontsize=10.5, color=t.ink,
                zorder=13, bbox=dict(boxstyle="square,pad=0.45", fc=t.card, ec=t.ink, lw=t.lw(1.3)))

        def xx0(c):
            return ext[0] + (ext[1] - ext[0]) * c / W

        def yy0(r):
            return ext[3] - (ext[3] - ext[2]) * r / H

        for z in scene.zooms:
            (r0, r1), (c0, c1) = z.rows, z.cols
            ax.add_patch(Rectangle((xx0(c0), yy0(r1)), xx0(c1) - xx0(c0), yy0(r0) - yy0(r1), fc="none", ec=t.card, lw=t.lw(1.4), zorder=11))
            ax.text(xx0(c0), yy0(r0) + 0.006 * (ext[3] - ext[2]), z.key, ha="left", va="bottom", fontsize=10.5, color=t.ink, zorder=13,
                    bbox=dict(boxstyle="square,pad=0.2", fc=t.card, ec=t.ink, lw=t.lw(1.0)))
        x0 = ext[0] + 0.05 * (ext[1] - ext[0])
        y0 = ext[2] + 0.05 * (ext[3] - ext[2])
        for i in range(5):
            ax.add_patch(Rectangle((x0 + i * 1000, y0), 1000, 700, fc=t.ink if i % 2 == 0 else t.card, ec=t.ink, lw=t.lw(1.0), zorder=14))
        ax.text(x0 + 2500, y0 + 1100, "5 KM", ha="center", fontsize=11, color=t.ink, zorder=15,
                bbox=dict(boxstyle="square,pad=0.2", fc=t.card, ec=t.ink, lw=t.lw(1.0)))
        chip(fig, t, hx + 0.012, hy + hh - 0.014, lay.text("panels.L"), t.chip_l, va="top", ha="left")
        chip(fig, t, hx + hw - 0.012, hy + hh - 0.014, lay.text("panels.S"), t.chip_s, va="top", ha="right")

        # Zoom cells: L above S for each window
        px, pw = hx + hw + 0.02, 0.96 - (hx + hw + 0.02)
        gap, lab = 0.009, 0.019
        ch = (hh - 2 * gap) / 3
        ih = (ch - lab) / 2
        for i, z in enumerate(scene.zooms):
            (r0, r1), (c0, c1) = z.rows, z.cols
            top = hy + hh - i * (ch + gap)
            fig.text(px + 0.002, top - lab / 2, f"{z.key}  {z.name}", fontsize=10.5, color=t.ink, weight="semibold", va="center", zorder=20)
            for j, (rg, bandname, col) in enumerate(((rL, "L", t.chip_l), (rS, "S", t.chip_s))):
                py = top - lab - (j + 1) * ih
                a = img_axes(fig, t, px, py, pw, ih - (0.003 if j == 0 else 0))
                a.imshow(rg[r0:r1, c0:c1], aspect="auto", interpolation="antialiased")
                chip(fig, t, px + 0.006, py + ih - 0.008, bandname, col, fs=10, va="top")

        social_footer(fig, t, lay)

        out = Path(out_dir) / FILENAME.format(scene=f"NISAR_{scene.name}", tag=t.tag)
        fig.savefig(out, dpi=180, facecolor=t.paper)
        plt.close(fig)
    return [out]
