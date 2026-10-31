"""The optional zoom side panels: up to three windows beside the picture, chosen by a centre and size or by rows and columns."""
import io

import numpy as np
import pytest
from PIL import Image

from satmaps.area import Area, AreaError
from satmaps.zoompanels import fit_window


def test_a_window_is_widened_to_its_panels_shape_around_its_centre_and_kept_inside_the_picture():
    assert fit_window((10, 20), (10, 20), 2.0, (100, 200)) == ((10, 20), (5, 25))  # a square becomes twice as wide as high
    assert fit_window((0, 10), (0, 10), 0.5, (100, 200)) == ((0, 20), (0, 10))  # and a tall panel makes it taller
    assert fit_window((90, 100), (190, 200), 2.0, (100, 200)) == ((90, 100), (180, 200))  # pushed in at the corner
    (r0, r1), (c0, c1) = fit_window((0, 100), (0, 200), 0.9, (100, 200))  # larger than the picture: shrunk, shape kept
    assert 0 <= r0 < r1 <= 100 and 0 <= c0 < c1 <= 200 and (c1 - c0) / (r1 - r0) == pytest.approx(0.9, abs=0.02)


def test_a_box_that_overhangs_the_area_is_moved_in_and_one_whose_centre_is_outside_is_refused():
    area = Area.from_config(dict(center=[27.0, 94.0], size_km=[10, 10], resolution_m=100))
    canvas = area.canvas(100)
    rows, cols = canvas.window_around(27.0, 94.0, (4, 4), clamp=True)
    assert (rows[1] - rows[0], cols[1] - cols[0]) == (40, 40)
    edge_lat = 27.0 + 4.9 / 110.57  # near the north edge: a 4 km box would overhang
    rows, cols = canvas.window_around(edge_lat, 94.0, (4, 4), clamp=True)
    assert rows[0] == 0 and rows[1] - rows[0] == 40  # slid down, not shrunk
    with pytest.raises(AreaError, match="outside the area"):
        canvas.window_around(28.0, 94.0, (4, 4), clamp=True)
    with pytest.raises(AreaError):
        canvas.window_around(edge_lat, 94.0, (4, 4))  # without `clamp` an overhang is still refused


def test_zoom_tables_from_boxes_and_from_centres_and_the_limit_of_three():
    from satmaps.api import zoom_tables

    out = zoom_tables([(94.0, 27.0, 94.1, 27.1), {"center": (27.5, 94.5), "size_km": (3, 2)},
                       {"box": (94.0, 27.0, 94.1, 27.1), "name": " hill edge "}])
    assert [z["key"] for z in out] == ["A", "B", "C"] and out[2]["name"] == "HILL EDGE" and out[2]["center"] == out[0]["center"]
    assert out[0]["center"] == [27.05, 94.05] and out[0]["size_km"][1] == pytest.approx(11.057, abs=0.01)
    assert out[1] == {"key": "B", "center": [27.5, 94.5], "size_km": [3.0, 2.0]}
    with pytest.raises(ValueError, match="room for three"):
        zoom_tables([(0, 0, 1, 1)] * 4)


def test_the_command_line_zoom_flag():
    from satmaps.cli import _zoom

    assert _zoom("27.5,94.1,6") == {"center": [27.5, 94.1], "size_km": [6.0, 6.0]}
    assert _zoom("27.5,94.1,6,3") == {"center": [27.5, 94.1], "size_km": [6.0, 3.0]}
    assert _zoom("27.5,94.1,6=Hill edge") == {"center": [27.5, 94.1], "size_km": [6.0, 6.0], "name": "Hill edge"}
    for bad in ("27.5,94.1", "a,b,c", "27.5,94.1,0"):
        with pytest.raises(ValueError, match="LAT,LON,KM"):
            _zoom(bad)


def page(arrangement, kinds, **kw):
    from satmaps.preview import render_example

    return np.asarray(Image.open(io.BytesIO(render_example(kinds, arrangement, "minimal", **kw))).convert("RGB"))


@pytest.mark.parametrize("kind", ["sar", "optical"])
def test_zoom_panels_are_optional_one_to_three_of_them_for_a_single_product_sar_or_optical(kind):
    plain = page("single", [kind])
    pages = {n: page("single", [kind], zoom_panels=n) for n in (1, 2, 3)}
    assert (page("single", [kind], zoom_panels=0) == plain).all()  # none asked for: the page is as before
    assert all(p.shape == plain.shape and (p != plain).any() for p in pages.values())
    assert not (pages[1] == pages[2]).all() and not (pages[2] == pages[3]).all()  # each extra panel shows
    column = lambda p: (p[300:1150, 1000:1160] != 255).mean()  # noqa: E731  where the column of panels sits
    assert column(pages[1]) < column(pages[2]) < column(pages[3])


def test_side_by_side_figures_have_no_zoom_panels():
    plain = page("compare", ["sar", "sar"])
    assert (page("compare", ["sar", "sar"], zoom_panels=3) == plain).all()


def test_the_job_file_keeps_the_zooms_and_runs(scene, tmp_path):
    from satmaps.api import build_job, job_toml
    from satmaps.job import load_job

    job, raw = build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir, zooms=[{"center": (27.1, 93.0), "size_km": (0.3, 0.3)}])
    assert raw["zooms"][0]["key"] == "A" and len(job.zoom_specs) == 1
    (tmp_path / "j.toml").write_text(job_toml(raw), encoding="utf-8")
    assert load_job(tmp_path / "j.toml", scene.data_dir).zoom_specs[0]["size_km"] == [0.3, 0.3]
    with pytest.raises(ValueError, match="room for three"):
        build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir, zooms=[(0, 0, 1, 1)] * 4)


def test_a_figure_with_zoom_panels_is_drawn_from_a_product_and_a_zoom_outside_the_area_is_named(scene, tmp_path):
    from satmaps.api import inspect, render
    from satmaps.job import JobError

    w, s, e, n = inspect(scene.data_dir / "L.h5")["bbox"]
    here = {"center": ((s + n) / 2, (w + e) / 2), "size_km": (0.3, 0.3)}
    plain = render([scene.data_dir / "L.h5"], out=tmp_path / "a", cache=None)
    zoomed = render([scene.data_dir / "L.h5"], out=tmp_path / "b", cache=None, zooms=[here])
    assert plain[0].read_bytes() != zoomed[0].read_bytes()
    with pytest.raises(JobError, match="zoom B: .*outside the area"):
        render([scene.data_dir / "L.h5"], out=tmp_path / "c", cache=None, zooms=[here, {"center": (s - 5, w - 5), "size_km": (1, 1)}])


def test_zoom_panels_are_refused_for_two_products(scene):
    from satmaps.api import build_job

    with pytest.raises(ValueError, match="one product at a time"):
        build_job([scene.data_dir / "L.h5", scene.data_dir / "S.h5"], data_dir=scene.data_dir, zooms=[(94.0, 27.0, 94.1, 27.1)])


def test_a_named_zoom_is_annotated_on_the_main_picture(scene, tmp_path):
    from satmaps.api import inspect, render

    w, s, e, n = inspect(scene.data_dir / "L.h5")["bbox"]
    at = {"center": ((s + n) / 2, (w + e) / 2), "size_km": (0.3, 0.3)}
    a = render([scene.data_dir / "L.h5"], out=tmp_path / "a", cache=None, zooms=[at])
    b = render([scene.data_dir / "L.h5"], out=tmp_path / "b", cache=None, zooms=[{**at, "name": "Hill edge"}])
    assert a[0].read_bytes() != b[0].read_bytes()  # the name is printed above the panel and beside the letter on the picture
