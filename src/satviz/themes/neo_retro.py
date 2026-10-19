"""Neo-retro: warm paper, ink outlines, small hard shadows, one muted accent pair. See docs/design-language.md."""
from satviz.core import theme
from satviz.themes.base import Theme

NEO_RETRO = theme("neo_retro")(Theme(
    name="neo_retro", tag="NeoRetro", paper="#ece4d3", card="#f7f2e7", ink="#23211f", muted="#6b655b",
    accent="#c4673a", chip_l="#e0b872", chip_s="#8fbfb7", note="#f0dfb0",
    title_font=("Gillius ADF", "DejaVu Sans"), body_font=("IBM Plex Mono", "DejaVu Sans Mono"),
    shadow=(0.0028, -0.0022),
))
