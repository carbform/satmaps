"""Retro '80s: vibrant 1980s synthwave & arcade aesthetic. Deep midnight ink, electric hot-pink shadow,
cyan & pastel-pink chips, laser-yellow notice, and monospaced tech typography."""
from satmaps.core import THEMES, theme
from satmaps.themes.base import Theme

RETRO_80S = theme("retro_80s")(Theme(
    name="retro_80s", tag="Retro80s", paper="#f0edf6", card="#faf5ff", ink="#120c1f", muted="#5c5470",
    accent="#ff007f", chip_a="#85e3ff", chip_b="#ffb8d2", note="#fff078",
    title_font=("Space Grotesk", "DejaVu Sans"), body_font=("IBM Plex Mono", "DejaVu Sans Mono"),
    title_size=42, shadow=(0.0035, -0.0028), line_scale=1.2,
))

THEMES.alias("neo_retro", "retro_80s")
