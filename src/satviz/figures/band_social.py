"""Single-band social graphic (4:5): full-width false-colour composite plus the three bands it is built from.

Used for both bands: `band="S"` or `band="L"`. Same neo-retro chrome as `ls_social`; wording in the band's layout file.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from satviz.config import Scene
from satviz.geo import to_xy, utm_extent
from satviz.layout import Layout, LayoutError, build_context
from satviz.recipes.sar_fcc import CHANNEL_COLORS, channel_panels, fcc_rgba
from satviz.sensors.nisar_gcov.processing import coarsen, stats
from satviz.themes.neo_retro import NEO_RETRO, chip, img_axes, social_footer, social_header

FILENAME = "{scene}_{band}band_Social_NeoRetro.png"


def _sticker(ax, t, text, xy, xytext, fc) -> None:
    ax.annotate(text, xy, xytext=xytext, textcoords="offset points", fontsize=11.5, color=t.ink, zorder=12,
                bbox=dict(boxstyle="square,pad=0.45", fc=fc, ec=t.ink, lw=1.4),
                arrowprops=dict(arrowstyle="-|>", color=t.ink, lw=1.5, shrinkA=0, shrinkB=2, mutation_scale=13))
    ax.plot(*xy, "o", ms=7, mfc=fc, mec=t.ink, mew=1.5, zorder=11)


def render(scene: Scene, bands: dict, out_dir: Path, layout: dict, band: str = "S") -> list[Path]:
    """Wording comes from `layout` (layouts/sband_social.toml or lband_social.toml); facts come from the file metadata."""
    t = NEO_RETRO
    d = bands[band]
    st = stats(d)
    rgba, lims, _ = fcc_rgba(d)
    lim = SimpleNamespace(**{f"{k}_{e}": v for k, (lo, hi) in lims.items() for e, v in (("lo", lo), ("hi", hi))})
    lay = Layout(layout, build_context(scene, {band: d}, {band: st}, per_band=True, extra={"lim": lim}))
    chip_color = t.mustard if band == "L" else t.teal
    ext = utm_extent(d)
    c = coarsen(d, 4)
    cext = utm_extent(c)

    with plt.rc_context({"font.family": list(t.body_font), "font.weight": "normal"}):
        fig = plt.figure(figsize=(12, 15), facecolor=t.paper)
        social_header(fig, t, lay)

        # Hero composite
        hy, hw, hx = 0.255, 0.677, 0.04
        hh = hw * 12 / 15 * (rgba.shape[0] / rgba.shape[1])
        ax = img_axes(fig, t, hx, hy, hw, hh)
        ax.imshow(rgba, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
        for i, co in enumerate(lay.get("callouts", [])):
            if co["key"] not in scene.callouts:
                raise LayoutError(f"{lay.path} [[callouts]] #{i + 1}: unknown callout {co['key']!r}; scene has {list(scene.callouts)}")
            xy = to_xy(d, *scene.callouts[co["key"]])
            _sticker(ax, t, lay.render(co["text"], f"callouts[{i}]"), xy, (co.get("dx", -60), co.get("dy", 60)),
                     t.card if co.get("fill", "card") == "card" else chip_color)
        x0 = ext[0] + 0.05 * (ext[1] - ext[0])
        y0 = ext[2] + 0.05 * (ext[3] - ext[2])
        for i in range(5):
            ax.add_patch(Rectangle((x0 + i * 1000, y0), 1000, 700, fc=t.ink if i % 2 == 0 else t.card, ec=t.ink, lw=1.0, zorder=14))
        ax.text(x0 + 2500, y0 + 1100, "5 KM", ha="center", fontsize=11, color=t.ink, zorder=15,
                bbox=dict(boxstyle="square,pad=0.2", fc=t.card, ec=t.ink, lw=1.0))
        chip(fig, t, hx + 0.012, hy + hh - 0.014, lay.text("panels.band"), chip_color, va="top", ha="left")
        chip(fig, t, hx + hw - 0.012, hy + hh - 0.014, lay.text("panels.composite"), t.card, va="top", ha="right")

        # The three bands the composite is built from, each tinted in its channel colour
        px, pw = hx + hw + 0.02, 0.96 - (hx + hw + 0.02)
        gap = 0.009
        ph = (hh - 2 * gap) / 3
        labels = lay.raw("channels.labels")
        if len(labels) != 3:
            raise LayoutError(f"{lay.path} [channels.labels]: need exactly 3 labels (R, G, B)")
        for i, (key, img) in enumerate(channel_panels(c, lims)):
            py = hy + hh - (i + 1) * ph - i * gap
            a = img_axes(fig, t, px, py, pw, ph)
            a.imshow(img, extent=cext, origin="upper", aspect="auto", interpolation="nearest")
            chip(fig, t, px + 0.008, py + ph - 0.01, lay.render(labels[i], f"channels.labels[{i}]"), CHANNEL_COLORS[key],
                 fs=10.5, va="top")

        social_footer(fig, t, lay)
        out = Path(out_dir) / FILENAME.format(scene=f"NISAR_{scene.name}", band=band)
        fig.savefig(out, dpi=180, facecolor=t.paper)
        plt.close(fig)
    return [out]
