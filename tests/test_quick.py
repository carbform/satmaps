"""The zero-config path: detecting sensors, the automatic area, quality profiles, `render` and `satviz quick`."""
import numpy as np
import pytest
from PIL import Image

from satviz import render
from satviz.area import Area, AreaError
from satviz.autoarea import common_area, largest_rectangle, pick_resolution
from satviz.cli import main
from satviz.detect import DetectError, detect, input_id
from satviz.job import JobError, load_job
from satviz.quality import PROFILES, profile_of
from satviz.registry import load_builtin
from satviz.run import run_job
from tests.rasters import needs_rasterio

load_builtin()


def ring(w, s, e, n):
    return [(w, s), (e, s), (e, n), (w, n), (w, s)]


# --- detection ---------------------------------------------------------------------------------------------------------------

def test_detects_a_nisar_file_and_names_its_input_by_band(scene):
    assert detect(scene.data_dir / "L.h5") == "nisar" and detect(scene.data_dir / "S.h5") == "nisar"
    assert input_id("nisar", scene.data_dir / "L.h5", set()) == "L" and input_id("nisar", scene.data_dir / "S.h5", set()) == "S"


def test_ids_are_numbered_on_a_collision():
    assert input_id("sentinel1", "x", set()) == "S1"
    assert input_id("sentinel1", "x", {"S1"}) == "S1_2" and input_id("sentinel1", "x", {"S1", "S1_2"}) == "S1_3"


def test_detection_refuses_what_it_cannot_read_and_says_what_it_reads(tmp_path):
    (tmp_path / "scene.zip").write_bytes(b"PK")
    with pytest.raises(DetectError, match="unzip it"):
        detect(tmp_path / "scene.zip")
    (tmp_path / "empty").mkdir()
    with pytest.raises(DetectError, match="nisar .*GCOV"):
        detect(tmp_path / "empty")
    with pytest.raises(DetectError, match="no such file"):
        detect(tmp_path / "nope")


@needs_rasterio
def test_detects_every_other_sensor_from_its_folder(tmp_path):
    from tests.test_eos04 import product_folder as eos
    from tests.test_liss4 import product_folder as liss
    from tests.test_sentinel1 import safe_folder as s1
    from tests.test_sentinel2 import safe_folder as s2

    a, b, c, d = (tmp_path / n for n in "abcd")
    for p in (a, b, c, d):
        p.mkdir()
    folder = s1(c)
    (folder / "manifest.safe").write_text("<x/>")  # the fixture leaves the manifest out
    assert detect(eos(a)) == "eos04" and detect(liss(b)) == "liss4" and detect(folder) == "sentinel1" and detect(s2(d)) == "sentinel2"


def test_a_job_input_without_a_sensor_is_detected_from_its_source(scene, tmp_path):
    job = tmp_path / "j.toml"
    job.write_text('[area]\ncenter = [27.0, 94.9]\nsize_km = [1, 1]\n[[inputs]]\nid = "L"\nsource = { path = "L.h5" }\n')
    assert load_job(job, scene.data_dir).inputs["L"].sensor == "nisar"
    job.write_text('[area]\ncenter = [27.0, 94.9]\nsize_km = [1, 1]\n[[inputs]]\nid = "L"\nsource = { path = "nope.h5" }\n')
    with pytest.raises(JobError, match="no `sensor`"):
        load_job(job, scene.data_dir)


# --- automatic area ----------------------------------------------------------------------------------------------------------

def test_the_largest_rectangle_in_a_mask():
    m = np.zeros((6, 8), bool)
    m[1:5, 2:7] = True
    m[3, 4] = False  # a hole splits the big block
    r0, r1, c0, c1 = largest_rectangle(m)
    assert m[r0:r1, c0:c1].all() and (r1 - r0) * (c1 - c0) == 10  # rows 1-2 across the top of the hole
    assert largest_rectangle(np.zeros((3, 3), bool)) is None


def test_common_area_sits_inside_every_footprint():
    a = common_area({"a": ring(94.0, 27.0, 95.0, 28.0), "b": ring(94.4, 27.3, 95.4, 28.3)})
    from satviz.area import _tf

    w, s, e, n = a.lonlat_bbox()
    assert 94.4 <= w < e <= 95.0 and 27.3 <= s < n <= 28.0  # the overlap of the two boxes
    assert (e - w) > 0.5 and (n - s) > 0.5
    assert a.epsg == 32646 and _tf(32646, 4326)


def test_a_slanted_footprint_gives_a_box_with_no_corner_outside_it():
    quad = [(94.0, 27.0), (95.0, 27.2), (95.0, 28.2), (94.0, 28.0), (94.0, 27.0)]  # a parallelogram
    a = common_area({"q": quad})
    from matplotlib.path import Path as P

    from satviz.area import _tf

    to_ll = _tf(a.epsg, 4326)
    for x, y in ((a.xmin, a.ymin), (a.xmax, a.ymin), (a.xmax, a.ymax), (a.xmin, a.ymax)):
        assert P(quad).contains_point(to_ll.transform(x, y))


def test_no_overlap_is_an_error_that_names_the_inputs():
    with pytest.raises(AreaError, match="do not overlap"):
        common_area({"S": ring(74, 11, 77, 14), "S1": ring(92, 27, 95, 29)}, {"S": "S (a.h5)", "S1": "S1 (b.SAFE)"})
    # boxes that overlap but whose footprints (a thin diagonal) share nothing
    with pytest.raises(AreaError, match="do not overlap"):
        common_area({"a": [(0, 0), (1, 0), (0, 1), (0, 0)], "b": [(1, 1), (1, 0.6), (0.6, 1), (1, 1)]})


def test_pixel_size_follows_the_target_and_never_beats_the_data():
    a = Area(32646, 0, 0, 100_000, 60_000)
    assert pick_resolution(a, 10, 800) == 150.0  # 100 km / 800 = 125 m -> the next round number
    assert pick_resolution(a, 10, 20000) == 10.0
    assert pick_resolution(a, 30, 20000) == 30.0


# --- profiles and files ------------------------------------------------------------------------------------------------------

def test_profiles():
    assert profile_of(None).name == "publication" and PROFILES["quick"].dpi < PROFILES["publication"].dpi
    with pytest.raises(ValueError, match="quality must be one of"):
        profile_of("fast")


def test_publication_writes_a_pdf_next_to_the_png_and_quick_does_not(scene, tmp_path):
    made = {}
    for quality, pdf in (("quick", False), ("publication", True)):
        (png,) = made[quality] = render([scene.data_dir / "L.h5"], out=tmp_path / quality, cache=None, quality=quality)
        assert png.exists() and png.with_suffix(".pdf").exists() == pdf
    assert Image.open(made["quick"][0]).size[0] < Image.open(made["publication"][0]).size[0]
    assert made["publication"][0].with_suffix(".pdf").read_bytes()[:5] == b"%PDF-"


# --- render, quick, save-job --------------------------------------------------------------------------------------------------

def test_a_job_with_no_area_and_no_sensor_runs_on_the_overlap(scene, tmp_path):
    job = tmp_path / "auto.toml"
    job.write_text('quality = "quick"\n[[inputs]]\nid = "L"\nsource = { path = "L.h5" }\n[[inputs]]\nid = "S"\nsource = { path = "S.h5" }\n')
    loaded = load_job(job, scene.data_dir)
    assert loaded.area is None and loaded.figures[0].template == "sar"
    paths = run_job(loaded, tmp_path / "out")
    assert len(paths) == 1 and paths[0].exists()
    lock = (tmp_path / "out" / "auto.lock.json").read_text()
    assert '"quality": "quick"' in lock and '"nisar"' in lock


def test_default_arrangement_follows_the_number_of_inputs(scene, tmp_path):
    from satviz.api import build_job

    one, _ = build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir)
    two, _ = build_job([scene.data_dir / "L.h5", scene.data_dir / "S.h5"], data_dir=scene.data_dir)
    assert (one.figures[0].arrangement, two.figures[0].arrangement) == ("single", "compare")
    assert two.figures[0].template == "sar" and list(two.inputs) == ["L", "S"]
    with pytest.raises(ValueError, match="too many"):
        build_job([scene.data_dir / "L.h5"] * 7, data_dir=scene.data_dir)


def test_the_saved_job_reproduces_the_figure(scene, tmp_path):
    paths = [scene.data_dir / "L.h5", scene.data_dir / "S.h5"]
    (png,) = render(paths, out=tmp_path / "a", cache=None, save_job=tmp_path / "saved.toml", title="Round trip")
    again = run_job(load_job(tmp_path / "saved.toml"), tmp_path / "b")
    assert [p.name for p in again] == [png.name]
    a, b = (np.asarray(Image.open(p).convert("RGB")) for p in (png, again[0]))
    assert a.shape == b.shape and (a == b).all()
    text = (tmp_path / "saved.toml").read_text()
    assert 'sensor = "nisar"' in text and "size_km" in text and "resolution_m" in text and "Round trip" in text


def test_quick_and_inspect_on_the_command_line(scene, tmp_path, capsys):
    assert main(["inspect", str(scene.data_dir / "L.h5")]) == 0
    out = capsys.readouterr().out
    assert "nisar (sar), 10 m pixels, EPSG:32646" in out and "W " in out
    assert main(["quick", str(scene.data_dir / "L.h5"), "--out", str(tmp_path / "o"), "--no-cache", "--theme", "xkcd"]) == 0
    assert (tmp_path / "o" / "quick_Xkcd.png").exists()
    assert main(["quick", str(tmp_path / "missing.h5")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_a_box_you_give_beats_the_overlap(scene, tmp_path):
    w, s, e, n = Area.from_config({"center": [27.0, 94.9], "size_km": [1, 1]}).lonlat_bbox()
    from satviz.api import build_job

    job, raw = build_job([scene.data_dir / "L.h5"], area=(w, s, e, n), data_dir=scene.data_dir)
    assert job.area is not None and raw["area"]["size_km"][0] > 0.5
