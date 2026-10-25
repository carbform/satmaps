import numpy as np
import pytest
from pyproj import Transformer

from satviz.area import AreaError
from satviz.cli import main
from satviz.job import JobError, load_job
from satviz.run import run_job
from tests.conftest import H, W

# the synthetic granules cover x 500000..501100, y 3000000..2998800 (UTM 46N, 10 m)
LON, LAT = Transformer.from_crs(32646, 4326, always_xy=True).transform(500550.0, 2999400.0)

JOB = f"""
[scene]
name = "Testland"
author = "Tester"

[area]
center = [{LAT}, {LON}]
size_km = [1.0, 1.0]

[[inputs]]
id = "L"
sensor = "nisar"
source = {{ path = "L.h5" }}

[[inputs]]
id = "S"
sensor = "nisar"
source = {{ path = "S.h5" }}

[[zooms]]
key = "A"
name = "ONE"
center = [{LAT}, {LON}]
size_km = [0.4, 0.3]
"""


@pytest.fixture
def job_file(scene, tmp_path):
    p = tmp_path / "job.toml"
    p.write_text(JOB)
    return p


def test_job_defaults_to_a_figure_for_the_inputs(job_file, scene):
    job = load_job(job_file, scene.data_dir)
    assert [f.template for f in job.figures] == ["sar"] and job.figures[0].inputs == ("L", "S")
    assert job.scene.name == "Testland" and list(job.inputs) == ["L", "S"]


@pytest.mark.parametrize("edit, msg", [
    (lambda t: t.replace("[area]", "[aera]"), "unknown section"),
    (lambda t: t.replace("center = [", "colour = 1\n# [").replace("size_km", "# size_km"), "area is automatic"),
    (lambda t: t + '\n[[figures]]\ntemplate = "sar"\ninputs = ["nope"]\n', "unknown input"),
    (lambda t: t + '\n[[figures]]\ninputs = ["L"]\n', "needs `template`"),
    (lambda t: t + '\n[[figures]]\ntemplate = "sar"\ncolour = "red"\n', "unknown key"),
    (lambda t: t.replace('id = "S"', 'id = "L"'), "appears twice"),
])
def test_bad_jobs_are_explained(tmp_path, edit, msg):
    p = tmp_path / "j.toml"
    p.write_text(edit(JOB))
    with pytest.raises(JobError, match=msg):
        load_job(p, tmp_path)


def test_extends_merges_tables_and_replaces_lists(tmp_path):
    (tmp_path / "base.toml").write_text('[scene]\nauthor = "Base"\nwebsite = "b.org"\n')
    (tmp_path / "j.toml").write_text('extends = "base.toml"\n' + JOB)
    job = load_job(tmp_path / "j.toml", tmp_path)
    assert job.scene.author == "Tester" and job.scene.website == "b.org"  # job wins, base fills the gaps


def test_nisar_on_a_canvas_equals_the_source_where_grids_align(job_file, scene, tmp_path):
    from satviz.core import SENSORS
    from satviz.registry import load_builtin
    from satviz.run import choose_canvas
    from satviz.sensors.sar.nisar.io import read_roi

    load_builtin()
    job = load_job(job_file, scene.data_dir)
    canvas, infos = choose_canvas(job, ["S"])
    assert canvas.res == 10 and infos["S"].epsg == 32646
    prod = SENSORS["nisar"].open(job.inputs["S"], canvas, job.area, scene.data_dir)
    assert prod.layers["hh"].shape == (canvas.height, canvas.width)
    raw = read_roi(scene.data_dir / "S.h5", scene.bands["S"])
    # canvas pixel -> source pixel by coordinates; compare every canvas pixel that lies inside the file
    cols = np.rint((canvas.x - raw["x"][0]) / 10).astype(int)
    rows = np.rint((raw["y"][0] - canvas.y) / 10).astype(int)
    rr, cc = np.meshgrid(rows, cols, indexing="ij")
    inside = (rr >= 0) & (rr < H) & (cc >= 0) & (cc < W)
    assert inside.any()
    assert np.array_equal(prod.layers["hh"][inside], raw["hh"][rr[inside], cc[inside]])
    assert (~prod.valid[~inside]).all()  # outside the file: not valid


def test_run_writes_figures_and_lock_file(job_file, scene, tmp_path):
    out = tmp_path / "out"
    job = load_job(job_file, scene.data_dir)
    paths = run_job(job, out)
    assert [p.name for p in paths] == ["NISAR_Testland_LvsS_Social_NeoRetro.png"]
    assert paths[0].stat().st_size > 5000
    import json

    lock = json.loads((out / "job.lock.json").read_text())
    assert lock["canvas"]["epsg"] == 32646 and set(lock["inputs"]) == {"L", "S"}


def test_every_pair_and_per_figure_themes_and_text(scene, tmp_path):
    text = JOB + '''
[[inputs]]
id = "X"
sensor = "nisar"
source = { path = "S.h5" }

[[figures]]
template = "sar"
inputs = ["L", "S", "X"]
theme = ["minimal", "neo_brutal"]
text = { title = "A CUSTOM TITLE" }
'''
    p = tmp_path / "j.toml"
    p.write_text(text)
    paths = run_job(load_job(p, scene.data_dir), tmp_path / "out")
    assert len(paths) == 6  # 3 pairs x 2 themes
    assert {x.name.split("_")[2] for x in paths} == {"LvsS", "LvsX", "SvsX"}


def test_single_figure_with_stem(scene, tmp_path):
    p = tmp_path / "j.toml"
    p.write_text(JOB + '\n[[figures]]\ntemplate = "sar"\ninputs = ["S"]\nname = "my_fig"\n')
    paths = run_job(load_job(p, scene.data_dir), tmp_path / "out")
    assert [x.name for x in paths] == ["my_fig_NeoRetro.png"]


def test_area_outside_the_file_is_explained(scene, tmp_path):
    p = tmp_path / "j.toml"
    p.write_text(JOB.replace(f"center = [{LAT}, {LON}]\nsize_km", "center = [10.0, 94.87]\nsize_km", 1).replace("[[zooms]]", "[[xx]]").split("[[xx]]")[0])
    with pytest.raises(AreaError, match="outside"):
        run_job(load_job(p, scene.data_dir), tmp_path / "out")


def test_cli_run_and_errors(job_file, scene, tmp_path, capsys):
    assert main(["run", str(job_file), "--data-dir", str(scene.data_dir), "--out", str(tmp_path / "o"), "--no-cache"]) == 0
    assert "Social_NeoRetro.png" in capsys.readouterr().out
    assert main(["run", str(tmp_path / "missing.toml")]) == 2
    assert "not found" in capsys.readouterr().err


def test_init_lists_and_writes_presets_that_parse(tmp_path, capsys):
    assert main(["init"]) == 0
    listed = capsys.readouterr().out
    assert all(n in listed for n in ("sar", "optical", "sar-optical"))
    for name in ("sar", "optical", "sar-optical"):
        dest = tmp_path / f"{name}.toml"
        assert main(["init", name, "-o", str(dest)]) == 0
        load_job(dest, tmp_path)  # every preset is a valid job
    assert main(["init", "sar", "-o", str(dest)]) == 2  # no silent overwrite
    assert main(["init", "nope"]) == 2


def test_legend_items_name_their_product_when_several_are_shown():
    import datetime as dt
    from types import SimpleNamespace

    from satviz.core import LegendItem as L
    from satviz.legend import named_legend

    def prod(platform, label, day):
        return SimpleNamespace(meta={"platform": platform, "label": label, "start": dt.datetime(2026, 9, day)})

    nisar = [L("#r", "RED = HH  (SURFACE)"), L("#g", "GREEN = HV  (VOLUME)"), L("#b", "BLUE = HH−HV  (RATIO)"), L("noise", "GREY = NOISE")]
    s1 = [L("#r", "RED = VV  (SURFACE)"), L("#g", "GREEN = VH  (VOLUME)"), L("#b", "BLUE = VV−VH  (RATIO)")]
    opt = [L("#r", "RED = B04 (665 NM)"), L("#g", "GREEN = B03 (560 NM)"), L("#b", "BLUE = B02 (490 NM)"), L("noise", "STRETCH 0.02–0.3")]
    n1, n2, s, o = prod("NISAR", "L-band", 1), prod("NISAR", "L-band", 8), prod("Sentinel-1D", "IW GRD", 2), prod("Sentinel-2C", "L2A", 3)
    assert named_legend([(n1, nisar)])[0].text == "RED = HH  (SURFACE)"  # one product: unchanged
    same = named_legend([(n1, nisar), (n2, nisar)])  # two passes of one product: one legend, named
    assert [i.text for i in same][:2] == ["NISAR L-BAND · RED = HH  (SURFACE)", "NISAR L-BAND · GREEN = HV  (VOLUME)"] and len(same) == 4
    two = named_legend([(n1, nisar), (o, opt)])  # two kinds: a row of three each
    assert [i.text.split(" · ")[0] for i in two] == ["NISAR L-BAND"] * 3 + ["SENTINEL-2C L2A"] * 3
    many = named_legend([(n1, nisar), (s, s1), (o, opt), (prod("NISAR", "L-band", 9), nisar)])  # three legends: a line each
    assert [i.text for i in many] == ["NISAR L-BAND · R HH · G HV · B HH−HV", "SENTINEL-1D IW GRD · R VV · G VH · B VV−VH",
                                      "SENTINEL-2C L2A · R B04 · G B03 · B B02"]
    twice = named_legend([(n1, nisar), (n2, nisar[:3])])  # same product, different legends: told apart by date
    assert {i.text.split(" · ")[0] for i in twice} == {"NISAR L-BAND 1 SEP", "NISAR L-BAND 8 SEP"}


def test_grid_template_renders_in_a_job(scene, tmp_path):
    text = JOB + '''
[[inputs]]
id = "X"
sensor = "nisar"
source = { path = "S.h5" }

[[figures]]
template = "sar"
arrangement = "grid"
inputs = ["L", "S", "X"]
theme = "minimal"
'''
    p = tmp_path / "j.toml"
    p.write_text(text)
    paths = run_job(load_job(p, scene.data_dir), tmp_path / "out")
    assert [x.name for x in paths] == ["NISAR_Testland_grid3_Social_Minimal.png"]
    bad = tmp_path / "k.toml"
    bad.write_text(text.replace('inputs = ["L", "S", "X"]', 'inputs = ["L"]'))
    with pytest.raises(JobError, match="at least two"):
        run_job(load_job(bad, scene.data_dir), tmp_path / "out2")


def test_inputs_from_different_passes_are_shown_together_unless_the_figure_asks_for_one_pass(scene, tmp_path):
    from satviz.layout import LayoutError
    from tests.conftest import make_raw, write_granule

    write_granule(tmp_path / "S2.h5", "science/SSAR/GCOV", make_raw(3), track=113)
    base = JOB.replace('source = { path = "S.h5" }', 'source = { path = "S2.h5" }')
    p = tmp_path / "j.toml"
    p.write_text(base)
    assert run_job(load_job(p, scene.data_dir), tmp_path / "out")[0].exists()  # any passes, by default
    p.write_text(base + '\n[[figures]]\ntemplate = "sar"\ninputs = ["L", "S"]\nsame_pass = true\n')
    with pytest.raises(LayoutError, match="same_pass"):
        run_job(load_job(p, scene.data_dir), tmp_path / "out2")


def test_layout_files_are_found_next_to_the_job_whatever_the_working_directory(scene, tmp_path, monkeypatch, layouts_dir):
    import shutil

    job_dir = tmp_path / "jobs"
    (job_dir / "layouts").mkdir(parents=True)
    shutil.copy(layouts_dir / "ls_social.toml", job_dir / "layouts" / "ls_social.toml")
    p = job_dir / "j.toml"
    p.write_text(JOB + '\n[[figures]]\ntemplate = "sar"\ninputs = ["L", "S"]\nlayout = "layouts/ls_social.toml"\n')
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert run_job(load_job(p, scene.data_dir), tmp_path / "out")[0].exists()
    p.write_text(JOB + '\n[[figures]]\ntemplate = "sar"\ninputs = ["L", "S"]\nlayout = "nope.toml"\n')
    with pytest.raises(JobError, match="not found; looked in"):
        run_job(load_job(p, scene.data_dir), tmp_path / "out3")
