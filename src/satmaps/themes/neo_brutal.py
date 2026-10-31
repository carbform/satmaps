"""Neo-brutal: thick black outlines, big offset shadows, flat saturated colour, heavy type."""
from satmaps.core import theme
from satmaps.themes.base import Theme

NEO_BRUTAL = theme("neo_brutal")(Theme(
    name="neo_brutal", tag="NeoBrutal", paper="#f3efe6", card="#ffffff", ink="#000000", muted="#3d3d3d",
    accent="#ff5d8f", header_fc="#ffd93d", chip_a="#ff9f68", chip_b="#5ad6ff", note="#d6ff5c",
    title_font=("Space Grotesk", "DejaVu Sans"), body_font=("Space Grotesk", "DejaVu Sans"),
    title_size=44, shadow=(0.0065, -0.0052), line_scale=2.0,
))
