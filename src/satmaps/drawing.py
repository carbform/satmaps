"""Theme-independent drawing helpers for data panels."""
from __future__ import annotations

import matplotlib.patheffects as pe


def scalebar(ax, ext, km: float, y_frac: float = 0.045, x_frac: float = 0.035, fs: float = 10) -> None:
    """White-over-black bar of `km` kilometres with a stroked label, in axes-data (metre) coordinates."""
    x0 = ext[0] + x_frac * (ext[1] - ext[0])
    y0 = ext[2] + y_frac * (ext[3] - ext[2])
    ax.plot([x0, x0 + km * 1000], [y0, y0], color="white", lw=4.5, solid_capstyle="butt", zorder=15)
    ax.plot([x0, x0 + km * 1000], [y0, y0], color="black", lw=1.8, solid_capstyle="butt", zorder=16)
    ax.text(x0 + km * 500, y0 + 0.014 * (ext[3] - ext[2]), f"{km:g} km", ha="center", fontsize=fs,
            weight="bold", color="white", path_effects=[pe.withStroke(linewidth=2.5, foreground="black")], zorder=17)
