"""The lat/lon grid with labels, the north arrow and the scale bar: drawn from the projection, optional, and off or on as before."""
import math

import matplotlib
import numpy as np
import pytest
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from satmaps.api import build_job  # noqa: E402
from satmaps.furniture import DEFAULT, Furniture, graticule, graticule_lines, lonlat_window, nice_step, true_north  # noqa: E402
from satmaps.job import load_job  # noqa: E402
from satmaps.run import run_job  # noqa: E402
from satmaps.themes.base import Theme  # noqa: E402

# a 12 x 10 km window near Dibrugarh in UTM zone 46N (central meridian 93E)
EXT = [660000.0, 672000.0, 3050000.0, 3060000.0]
EPSG = 32646


def test_nice_steps_give_about_four_lines():
    assert nice_step(0.2) == 0.05 and nice_step(1.0) == 0.5 and nice_step(2.0) == 0.5 and nice_step(0.09) == 0.05
    assert nice_step(0.04) == 0.01  # 0.04 / 4 lines = 0.01
    assert nice_step(100) == 20 and nice_step(1e-6) == 0.001  # and it never runs off the ends of the list


def test_the_window_in_degrees_matches_the_extent():
    w, s, e, n = lonlat_window(EXT, EPSG)
    assert 94.5 < w < e < 95.0 and 27.5 < s < n < 27.7 and (e - w) > 0.1 and (n - s) > 0.08


def test_grid_lines_are_whole_steps_labelled_as_such():
    g = graticule_lines(EXT, EPSG)
    assert g["step"] == 0.05
    labels = [m[3] for m in g["meridians"]] + [p[3] for p in g["parallels"]]
    assert labels and all(l.endswith(("°E", "°N")) for l in labels)
    for lon, xs, ys, label in g["meridians"]:
        assert abs(lon / 0.05 - round(lon / 0.05)) < 1e-6 and label == f"{lon:.2f}°E"
        assert xs.max() - xs.min() < 3000 and np.ptp(ys) > np.ptp(EXT[2:])  # almost straight up, and longer than the panel
    for lat, _xs, _ys, label in g["parallels"]:
        assert abs(lat / 0.05 - round(lat / 0.05)) < 1e-6 and label == f"{lat:.2f}°N"


def test_lines_are_tilted_by_the_projection_not_drawn_square():
    _, xs, ys, _ = graticule_lines(EXT, EPSG)["meridians"][0]
    assert abs(xs[-1] - xs[0]) > 1  # a UTM meridian away from the central one is not exactly vertical


def test_the_grid_puts_labels_at_the_panel_edges():
    t = Theme(name="t", tag="T", paper="white", card="white", ink="black", muted="grey", chip_a="r", chip_b="b", note="w")
    wide = [650000.0, 680000.0, 3040000.0, 3065000.0]  # 30 x 25 km: several lines each way
    fig, ax = plt.subplots()
    ax.imshow(np.zeros((10, 12)), extent=wide, origin="upper", aspect="auto")
    before = (ax.get_xlim(), ax.get_ylim())
    graticule(ax, t, wide, EPSG)
    assert (ax.get_xlim(), ax.get_ylim()) == before  # the lines run past the panel but do not move its edges
    texts = [(x.get_text(), x.get_position()) for x in ax.texts]
    lon = [(s, p) for s, p in texts if s.endswith("°E")]
    lat = [(s, p) for s, p in texts if s.endswith("°N")]
    assert len(lon) >= 2 and len(lat) >= 2
    assert all(abs(p[1] - wide[2]) < 0.02 * (wide[3] - wide[2]) for _, p in lon)  # longitudes sit on the bottom edge
    assert all(abs(p[0] - wide[0]) < 0.02 * (wide[1] - wide[0]) for _, p in lat)  # latitudes on the left edge
    plt.close(fig)


@pytest.mark.parametrize("lon, leans", [(94.9, "west"), (91.1, "east")])
def test_true_north_leans_toward_the_central_meridian(lon, leans):
    from pyproj import Transformer

    x, y = Transformer.from_crs(4326, EPSG, always_xy=True).transform(lon, 27.6)
    dx, dy = true_north([x - 5000, x + 5000, y - 5000, y + 5000], EPSG)
    assert dy > 0.999 and math.isclose(math.hypot(dx, dy), 1.0)
    assert (dx < 0) == (leans == "west")  # east of the central meridian (93E) true north points up and to the west
    expected = math.sin(math.radians(27.6)) * math.radians(abs(lon - 93.0))  # the meridian convergence
    assert abs(abs(dx) - expected) < 0.004


def test_defaults_keep_the_scale_bar_and_leave_the_rest_out():
    assert DEFAULT == Furniture(scale=True, north=False, grid=False)


def pixels(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(int)


def test_each_option_changes_the_figure_and_the_default_is_unchanged(scene, tmp_path):
    paths = [scene.data_dir / "L.h5"]
    made = {}
    for name, opts in {"default": {}, "grid": {"grid": True}, "north": {"north": True}, "noscale": {"scalebar": False},
                       "all": {"grid": True, "north": True}}.items():
        job, _ = build_job(paths, data_dir=scene.data_dir, resolution_m=10.0, **opts)
        (png,) = run_job(job, tmp_path / name)
        made[name] = pixels(png)
    base = made["default"]
    for name in ("grid", "north", "noscale", "all"):
        assert not (made[name] == base).all(), name  # each option shows
    again, _ = build_job(paths, data_dir=scene.data_dir, resolution_m=10.0, scalebar=True)
    (png,) = run_job(again, tmp_path / "again")
    assert (pixels(png) == base).all()  # asking for what is already the default changes nothing


def test_the_options_are_in_the_job_file_and_come_back(scene, tmp_path):
    from satmaps.api import job_toml

    job, raw = build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir, grid=True, north=True, scalebar=False)
    fig = raw["figures"][0]
    assert fig["grid"] is True and fig["north"] is True and fig["scalebar"] is False
    (tmp_path / "j.toml").write_text(job_toml(raw))
    again = load_job(tmp_path / "j.toml", scene.data_dir).figures[0]
    assert (again.grid, again.north, again.scalebar) == (True, True, False)
    plain = build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir)[1]["figures"][0]
    assert not {"grid", "north", "scalebar"} & set(plain)  # nothing written for the defaults


def test_the_command_line_flags(scene, tmp_path):
    from satmaps.cli import main

    out = tmp_path / "o"
    assert main(["quick", str(scene.data_dir / "L.h5"), "--grid", "--north", "--no-scale", "--out", str(out), "--no-cache",
                 "--save-job", str(tmp_path / "s.toml")]) == 0
    text = (tmp_path / "s.toml").read_text()
    assert "grid = true" in text and "north = true" in text and "scalebar = false" in text


@pytest.mark.parametrize("layout", ["single", "compare", "grid", "bands"])
def test_every_layout_can_carry_the_furniture(layout):
    import io

    from satmaps.preview import render_example

    plain = np.asarray(Image.open(io.BytesIO(render_example(None, layout, "minimal"))).convert("RGB")).astype(int)
    full = np.asarray(Image.open(io.BytesIO(render_example(None, layout, "minimal",
                                                           furniture=Furniture(scale=True, north=True, grid=True)))).convert("RGB")).astype(int)
    assert not (plain == full).all()
