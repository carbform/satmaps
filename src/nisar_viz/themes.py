"""Design tokens. The 'neo-retro' look: warm paper, ink outlines, small hard shadows, one muted accent pair.

Only the chrome around the data is styled; data panels are never filtered, glowed or recoloured.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NeoRetro:
    paper: str = "#ece4d3"
    card: str = "#f7f2e7"
    ink: str = "#23211f"
    muted: str = "#6b655b"
    orange: str = "#c4673a"  # title offset
    mustard: str = "#e0b872"  # L-band chips
    teal: str = "#8fbfb7"  # S-band chips
    note: str = "#f0dfb0"  # calibration notice strip
    noise_grey: str = "#3a3a40"
    title_font: tuple[str, ...] = ("Gillius ADF", "DejaVu Sans")  # optional; falls back to DejaVu Sans
    body_font: tuple[str, ...] = ("IBM Plex Mono", "DejaVu Sans Mono")  # optional; falls back to DejaVu Sans Mono
    shadow: tuple[float, float] = (0.0028, -0.0022)  # hard shadow offset, figure fraction


NEO_RETRO = NeoRetro()
