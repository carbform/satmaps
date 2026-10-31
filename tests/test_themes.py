"""Themes style the chrome and nothing else: they all render, stay readable, and leave the data pixels alone."""
import dataclasses

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

from satmaps.arrangements import compare, grid, single  # noqa: E402
from satmaps.core import THEMES  # noqa: E402
from satmaps.layout import default_layout  # noqa: E402
from satmaps.registry import load_builtin  # noqa: E402
from satmaps.sensors.sar.nisar import load as load_product  # noqa: E402

load_builtin()
ALL = sorted(THEMES)


def luminance(hex_: str) -> float:
    c = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_five_looks_are_registered():
    assert ALL == ["minimal", "neo_brutal", "neo_retro", "newspaper", "xkcd"]


@pytest.mark.parametrize("name", ALL)
def test_text_tokens_are_readable_on_their_backgrounds(name):
    t = THEMES[name]
    # WCAG 2.2: 4.5:1 for normal text. Ink carries the titles and labels, muted the secondary lines (info line, credits).
    for text, ground, role in ((t.ink, t.paper, "ink on paper"), (t.ink, t.card, "ink on card"), (t.muted, t.paper, "muted on paper"),
                               (t.muted, t.card, "muted on card"), (t.ink, t.chip_a, "ink on chip a"), (t.ink, t.chip_b, "ink on chip b"),
                               (t.ink, t.note, "ink on notice strip")):
        assert contrast(text, ground) >= 4.5, f"{name}: {role} is {contrast(text, ground):.2f}:1"


@pytest.mark.parametrize("name", ALL)
@pytest.mark.parametrize("arrangement", ["single", "compare", "grid"])
def test_every_theme_renders_every_arrangement(name, arrangement, scene, tmp_path):
    prods = {b: load_product(scene, b) for b in "LS"}
    lay = default_layout(arrangement)
    if arrangement == "single":
        paths = single.render(scene, prods, tmp_path, lay, input="S", theme=name)
    elif arrangement == "compare":
        paths = compare.render(scene, prods, tmp_path, lay, inputs=("L", "S"), theme=name)
    else:
        paths = grid.render(scene, prods, tmp_path, lay, inputs=("L", "S"), theme=name)
    assert paths[0].exists() and paths[0].stat().st_size > 5000 and THEMES[name].tag in paths[0].name


def test_sketch_is_taken_off_everything_in_a_data_axes_but_kept_on_the_chrome():
    t = THEMES["xkcd"]
    with plt.rc_context(t.rc_params()):
        fig = plt.figure()
        chrome = fig.add_artist(Rectangle((0.1, 0.1), 0.2, 0.2, transform=fig.transFigure))
        ax = fig.add_axes([0.2, 0.2, 0.6, 0.6])
        ax.imshow(np.zeros((4, 4)))
        bar = ax.add_patch(Rectangle((0, 0), 1, 1))  # a scale bar or zoom box
        line = ax.axvline(1.0)  # the split line
        label = ax.text(1, 1, "2 KM", bbox=dict(boxstyle="square", fc="w"))
        assert chrome.get_sketch_params() is not None and bar.get_sketch_params() is not None  # the effect is really on
        t.finish(fig)
    for artist in (bar, line, label, label.get_bbox_patch(), *ax.spines.values()):
        assert artist.get_sketch_params() is None and not artist.get_path_effects(), artist
    assert chrome.get_sketch_params() is not None  # chrome keeps the look
    plt.close(fig)


def test_the_other_themes_do_not_sketch():
    for name in ("minimal", "neo_brutal", "neo_retro", "newspaper"):
        assert not THEMES[name].sketch and "path.sketch" not in THEMES[name].rc_params()


def test_data_pixels_are_identical_in_every_theme(scene, tmp_path, monkeypatch):
    """The picture inside the hero axes must not depend on the theme: compare the same patch of it across all five."""
    scene = dataclasses.replace(scene, zooms=())
    prods = {b: load_product(scene, b) for b in "LS"}
    boxes = []
    original = compare.img_axes

    def recording(fig, t, x, y, w, h):
        boxes.append((x, y, w, h))
        return original(fig, t, x, y, w, h)

    monkeypatch.setattr(compare, "img_axes", recording)
    patches = {}
    for name in ALL:
        boxes.clear()
        out = compare.render(scene, prods, tmp_path, default_layout("compare"), inputs=("L", "S"), theme=name)[0]
        x, y, w, h = boxes[0]
        im = np.asarray(Image.open(out).convert("RGB")).astype(int)
        H, W = im.shape[:2]
        x0, x1 = x * W, (x + w) * W
        top, bot = (1 - (y + h)) * H, (1 - y) * H
        rows = slice(int(top + 0.3 * (bot - top)), int(top + 0.7 * (bot - top)))  # clear of chips, scale bar and split label
        left = im[rows, int(x0 + 0.12 * (x1 - x0)):int(x0 + 0.4 * (x1 - x0))]
        right = im[rows, int(x0 + 0.62 * (x1 - x0)):int(x0 + 0.88 * (x1 - x0))]
        patches[name] = (left, right)
    ref = patches["minimal"]
    assert ref[0].std() > 5 and ref[1].std() > 5  # the patches hold picture, not flat background
    assert not np.array_equal(ref[0], ref[1])
    for name, (left, right) in patches.items():
        assert left.shape == ref[0].shape
        assert np.array_equal(left, ref[0]) and np.array_equal(right, ref[1]), f"{name} changed the data pixels"


@pytest.mark.parametrize("theme", sorted(THEMES))
@pytest.mark.parametrize("layout", ["single", "compare", "grid", "bands"])
def test_every_figure_carries_the_made_with_banner_in_its_top_right_corner(layout, theme, monkeypatch):
    import io

    import numpy as np
    from PIL import Image

    from satmaps.preview import render_example
    from satmaps.themes import base

    def corner():
        page = np.asarray(Image.open(io.BytesIO(render_example(None, layout, theme))).convert("RGB"))
        return page[:46, 900:]  # above the header box, right of centre

    with_banner = corner()
    monkeypatch.setattr(base, "MADE_WITH", "")
    assert base.MADE_WITH == "" and (with_banner != corner()).any()  # the banner is what fills that corner
    assert (with_banner != with_banner[0, 0]).any()
