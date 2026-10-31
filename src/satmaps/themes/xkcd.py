"""xkcd: white page, hand-drawn lines and a comic typeface, after matplotlib's own `plt.xkcd()` settings.

The sketch effect is applied to the chrome (frames, chips, rules, text). `Theme.finish` takes it off every artist inside a data
axes, so scale bars, zoom boxes and the split line stay exact, and the pictures themselves are never touched.
"""
from matplotlib import patheffects

from satmaps.core import theme
from satmaps.themes.base import Theme, installed

FONTS = installed("xkcd", "xkcd Script", "Humor Sans", "Comic Neue", "Comic Sans MS", "DejaVu Sans")  # the comic fonts found here

XKCD = theme("xkcd")(Theme(
    name="xkcd", tag="Xkcd", paper="#ffffff", card="#ffffff", ink="#000000", muted="#4a4a4a",
    chip_a="#ffe08a", chip_b="#a9d6f0", note="#fff6c2",
    title_font=FONTS, body_font=FONTS, title_size=40, line_scale=1.3,
    rc={"path.sketch": (1.0, 100.0, 2.0), "path.effects": [patheffects.withStroke(linewidth=4, foreground="w")]},
    sketch=True,
))
