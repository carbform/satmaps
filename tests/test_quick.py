"""The zero-config path: detecting sensors, the automatic area, quality profiles, `render` and `satmaps quick`."""
import numpy as np
import pytest
from PIL import Image

from satmaps import render
from satmaps.area import Area, AreaError
from satmaps.autoarea import common_area, largest_rectangle, pick_resolution
from satmaps.cli import main
from satmaps.detect import DetectError, detect, input_id
from satmaps.job import JobError, load_job
from satmaps.quality import PROFILES, profile_of
from satmaps.registry import load_builtin
from satmaps.run import run_job
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
    from satmaps.area import _tf

    w, s, e, n = a.lonlat_bbox()
    assert 94.4 <= w < e <= 95.0 and 27.3 <= s < n <= 28.0  # the overlap of the two boxes
    assert (e - w) > 0.5 and (n - s) > 0.5
    assert a.epsg == 32646 and _tf(32646, 4326)


def test_a_slanted_footprint_gives_a_box_with_no_corner_outside_it():
    quad = [(94.0, 27.0), (95.0, 27.2), (95.0, 28.2), (94.0, 28.0), (94.0, 27.0)]  # a parallelogram
    a = common_area({"q": quad})
    from matplotlib.path import Path as P

    from satmaps.area import _tf

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
    from satmaps.api import build_job

    one, _ = build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir)
    two, _ = build_job([scene.data_dir / "L.h5", scene.data_dir / "S.h5"], data_dir=scene.data_dir)
    assert (one.figures[0].arrangement, two.figures[0].arrangement) == ("single", "compare")
    assert two.figures[0].template == "sar" and list(two.inputs) == ["L", "S"]
    with pytest.raises(ValueError, match="one product, or two that overlap"):
        build_job([scene.data_dir / "L.h5"] * 3, data_dir=scene.data_dir)


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
    assert (tmp_path / "o" / "nisar_quick_Xkcd.png").exists() and (tmp_path / "o" / "nisar_quick.lock.json").exists()
    assert main(["quick", str(tmp_path / "missing.h5")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_a_box_you_give_beats_the_overlap(scene, tmp_path):
    w, s, e, n = Area.from_config({"center": [27.0, 94.9], "size_km": [1, 1]}).lonlat_bbox()
    from satmaps.api import build_job

    job, raw = build_job([scene.data_dir / "L.h5"], area=(w, s, e, n), data_dir=scene.data_dir)
    assert job.area is not None and raw["area"]["size_km"][0] > 0.5


def test_a_box_you_give_gets_a_pixel_size_for_the_profile_too(scene, monkeypatch):
    from satmaps.api import build_job
    from satmaps.quality import Profile

    box = Area.from_config({"center": [27.0, 94.9], "size_km": [1, 1]}).lonlat_bbox()
    job, _ = build_job([scene.data_dir / "L.h5"], area=box, data_dir=scene.data_dir)
    assert job.area.resolution_m == 10.0  # a small box: the data's own size, not coarser than it has to be
    monkeypatch.setitem(PROFILES, "quick", Profile("quick", 40, 100, False))  # about 1 km / 40 px = 25 m -> 30 m
    job, _ = build_job([scene.data_dir / "L.h5"], area=box, data_dir=scene.data_dir)
    assert job.area.resolution_m == 30.0


# --- the quick-look polish: titles, file names, profiles, size check, cloud-free stretch ----------------------------------------

def test_a_quick_figure_is_titled_by_what_it_shows_and_a_given_title_wins(scene, tmp_path):
    from satmaps.api import build_job
    from satmaps.run import read_products
    from satmaps.templates.base import auto_title

    job, _ = build_job([scene.data_dir / "L.h5", scene.data_dir / "S.h5"], data_dir=scene.data_dir)
    assert job.scene.name == ""
    _, _, products = read_products(job, ["L", "S"])
    assert auto_title([products["L"]]) == "NISAR L-band · 25 Sep 2026"
    assert auto_title(list(products.values())) == "NISAR L-band and NISAR S-band"  # the platform repeats: the label tells them apart

    def fake(kind, platform, label=""):
        from types import SimpleNamespace

        return SimpleNamespace(kind=kind, meta={"platform": platform, "label": label})

    s1, s2, liss, eos = fake("sar", "Sentinel-1D"), fake("optical", "Sentinel-2C"), fake("optical", "ResourceSat-2A"), fake("sar", "EOS-04")
    assert auto_title([s1, s2]) == "Sentinel-1D and Sentinel-2C"
    assert auto_title([eos, s1, products["L"]]) == "EOS-04, Sentinel-1D and NISAR"  # a list, when it fits the header
    assert auto_title([s1, eos, s2, liss]) == "Radar and optical"  # too long to list
    assert auto_title([s1, eos, products["L"], products["S"]]) == "Radar compared"
    assert auto_title([s2, liss, fake("optical", "Landsat 9"), fake("optical", "Planet SkySat")]) == "Optical compared"


def test_a_title_that_repeats_the_subtitle_drops_the_subtitle(scene, tmp_path):
    from types import SimpleNamespace

    from satmaps.core import TEMPLATES

    def fake(kind, platform, band):
        meta = dict(platform=platform, label="", sensor="x", radar_band=band, wavelength_cm=5.0, backscatter="sigma0, ellipsoid",
                    start=__import__("datetime").datetime(2026, 9, 25), end=__import__("datetime").datetime(2026, 9, 25), resolution_m=10, crs="UTM 46N")
        return SimpleNamespace(kind=kind, meta=meta, layers={}, caveats=[], shared={}, bands=(), valid=np.ones((2, 2), bool))

    many = {k: fake(kind, f"Platform-{k}-xxxxxxxx", "C") for k, kind in (("a", "sar"), ("b", "sar"), ("c", "optical"))}
    r = TEMPLATES["sar_optical"].resolve(SimpleNamespace(arrangement="grid", recipes={"default": "sar_fcc"}), ("a", "b", "c"), many,
                                         SimpleNamespace(name="", region=""))
    assert r.text["title"] == "Radar and optical" and "subtitle" not in r.text


def test_a_job_file_with_a_name_keeps_it_as_the_title(scene, tmp_path):
    job = tmp_path / "named.toml"
    job.write_text('[scene]\nname = "Mine"\n[[inputs]]\nid = "L"\nsource = { path = "L.h5" }\n')
    assert load_job(job, scene.data_dir).scene.name == "Mine"
    job.write_text('[[inputs]]\nid = "L"\nsource = { path = "L.h5" }\n')  # no name at all: the file's stem, as before
    assert load_job(job, scene.data_dir).scene.name == "named"


def test_files_are_named_after_the_figure(scene, tmp_path):
    (png,) = render([scene.data_dir / "L.h5"], out=tmp_path, cache=None)
    assert png.name == "nisar_quick_Minimal.png" and (tmp_path / "nisar_quick.lock.json").exists()
    (png,) = render([scene.data_dir / "L.h5"], out=tmp_path, cache=None, quality="medium")
    assert png.name == "nisar_medium_Minimal.png" and not png.with_suffix(".pdf").exists()


def test_the_medium_profile_sits_between_quick_and_publication():
    q, m, p = (PROFILES[n] for n in ("quick", "medium", "publication"))
    assert q.target_px < m.target_px < p.target_px and q.dpi < m.dpi < p.dpi and not m.pdf and p.pdf


def test_a_very_large_automatic_area_asks_for_a_bbox(scene, tmp_path):
    from satmaps.api import _check_size, _figure_name

    big = Area(32646, 500000, 3000000, 700000, 3190000)  # 200 x 190 km
    with pytest.raises(ValueError, match=r"--bbox W S E N .*--bbox \d+\.\d\d \d+\.\d\d \d+\.\d\d \d+\.\d\d.*--allow-large"):
        _check_size(big)
    _check_size(Area(32646, 500000, 3000000, 560000, 3060000))  # 60 x 60 km passes
    assert _figure_name(["nisar", "nisar", "eos04"], "quick") == "nisar_eos04_quick"
    assert _figure_name(["a", "b", "c", "d"], "publication") == "overview"


def test_a_given_box_or_allow_large_skips_the_size_check(scene, monkeypatch):
    from satmaps import api

    monkeypatch.setattr(api, "MAX_AUTO_KM2", 0.5)  # the synthetic scene is about 1.3 km2: "large" for this test
    with pytest.raises(ValueError, match="slow"):
        api.build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir)
    api.build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir, allow_large=True)
    w, s, e, n = Area.from_config({"center": [27.0, 94.9], "size_km": [1, 1]}).lonlat_bbox()
    api.build_job([scene.data_dir / "L.h5"], area=(w, s, e, n), data_dir=scene.data_dir)


def test_cloud_does_not_set_the_stretch_but_is_still_drawn():
    from types import SimpleNamespace

    from satmaps.recipes.bands import cloud_left_out, usable
    from satmaps.recipes.optical import _pooled_percentiles

    rng = np.random.default_rng(0)
    land = rng.uniform(0.02, 0.12, (100, 100)).astype(np.float32)
    cloud = np.zeros((100, 100), np.float32)
    cloud[:15] = 1  # 15% cloud, bright
    land[:15] = 0.7
    p = SimpleNamespace(layers={"red": land, "green": land, "blue": land, "cloud": cloud}, valid=np.ones((100, 100), bool))
    assert usable(p).sum() == 8500 and cloud_left_out(p)
    few = SimpleNamespace(layers={"red": land, "cloud": np.where(np.arange(10000).reshape(100, 100) < 30, 1.0, 0.0).astype(np.float32)},
                          valid=np.ones((100, 100), bool))
    assert usable(few).sum() == 9970 and not cloud_left_out(few)  # 0.3 % cloud: dropped from the stretch, not worth a notice
    lo, hi = _pooled_percentiles([p], ("red", "green", "blue"))
    assert hi < 0.13  # the land sets the limits; with clouds in, the 98th percentile would be 0.7
    clear = SimpleNamespace(layers={"red": land}, valid=np.ones((100, 100), bool))
    assert not cloud_left_out(clear) and usable(clear).all()
    mostly = SimpleNamespace(layers={"red": land, "cloud": np.ones((100, 100), np.float32)}, valid=np.ones((100, 100), bool))
    assert usable(mostly).all()  # nothing clear: keep the cloud rather than stretch on nothing


def test_coverage_is_the_share_of_a_box_inside_a_footprint():
    from satmaps.autoarea import coverage

    ring = [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]
    assert coverage(ring, (0.5, 0.5, 1.5, 1.5)) == 1.0  # inside
    assert coverage(ring, (3, 3, 4, 4)) == 0.0  # outside
    assert 0.45 < coverage(ring, (1, 0, 3, 2)) < 0.55  # half in
    assert coverage(ring, (2, 2, 1, 1)) == 0.0  # not a box


def test_products_are_grouped_by_the_ground_they_share():
    from satmaps.autoarea import group_by_ground, touches

    def box(w, s, e, n):
        return [(w, s), (e, s), (e, n), (w, n), (w, s)]

    a, b, far = box(0, 0, 2, 2), box(1, 1, 3, 3), box(10, 10, 12, 12)
    assert group_by_ground([a, far, b]) == [[0, 2], [1]]  # a and b overlap; far is a place of its own
    assert group_by_ground([a, None, far]) == [[0, 1], [2]]  # no footprint: joins the first group
    assert touches(a, (1, 1, 5, 5)) and not touches(a, (3, 3, 5, 5))


def test_channels_become_recipes_per_input_and_the_default_adds_nothing(scene):
    from satmaps.api import band_choices, build_job, channel_recipes

    assert channel_recipes({"sar": ("co", "cross", "ratio")}, {"L": "sar"}) == {}
    assert channel_recipes({"sar": ("cross", "co", "ratio"), "optical": ("nir", "red", "green")},
                           {"L": "sar", "S2": "optical"}) == {"L": "sar_fcc:cross,co,ratio", "S2": "fcc:nir,red,green"}
    job, raw = build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir, channels={"sar": ("ratio", "co", "cross")})
    assert raw["figures"][0]["recipes"] == {"L": "sar_fcc:ratio,co,cross"}
    assert [k for k, _ in band_choices(["sentinel2"])][:4] == ["blue", "green", "red", "B05"]
    assert [k for k, _ in band_choices(["sentinel2", "liss4"])] == ["green", "red", "nir"]  # only what both have


def test_a_false_colour_choice_reaches_the_figure(scene, tmp_path):
    from satmaps.api import render

    (png,) = render([scene.data_dir / "L.h5"], out=tmp_path, cache=None, data_dir=scene.data_dir,
                    channels={"sar": ("cross", "co", "ratio")}, title="FCC")
    assert png.exists()
