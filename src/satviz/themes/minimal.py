"""Minimal: white page, hairline rules, no shadows, no title offset, quiet pastel chips."""
from satviz.core import theme
from satviz.themes.base import Theme

MINIMAL = theme("minimal")(Theme(
    name="minimal", tag="Minimal", paper="#ffffff", card="#ffffff", ink="#141414", muted="#6e6e6e",
    chip_l="#efe6d2", chip_s="#d7e6e3", note="#f2f2f2",
    title_font=("Inter", "DejaVu Sans"), body_font=("Inter", "DejaVu Sans"),
    title_size=36, line_scale=0.55,
))
