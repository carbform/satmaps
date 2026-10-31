"""`scan`, the large-area error, and the local app driven headless (Streamlit's AppTest) on the synthetic granules."""
import importlib.util
from pathlib import Path

import pytest

from satviz.api import TooLarge, _check_size, build_job, job_toml, scan
from satviz.area import Area
from tests.conftest import make_raw, write_granule

APP = Path(__file__).resolve().parents[1] / "src" / "satviz" / "app.py"
needs_streamlit = pytest.mark.skipif(importlib.util.find_spec("streamlit") is None, reason='pip install -e ".[app]"')


# --- scan --------------------------------------------------------------------------------------------------------------------

def test_scan_lists_products_flags_zips_and_skips_the_rest(scene, tmp_path):
    (scene.data_dir / "scene.zip").write_bytes(b"PK")
    (scene.data_dir / "outputs").mkdir()
    (scene.data_dir / "notes.txt").write_text("hello")
    (scene.data_dir / ".hidden").mkdir()
    rows = scan(scene.data_dir)
    assert [(r["name"], r["sensor"]) for r in rows] == [("L.h5", "nisar"), ("S.h5", "nisar"), ("scene.zip", None)]
    assert rows[0]["kind"] == "sar" and rows[2]["note"] == "unzip it"
    with pytest.raises(ValueError, match="not a folder"):
        scan(tmp_path / "nope")


def test_scan_does_not_read_pixels_or_footprints(scene, monkeypatch):
    from satviz.core import SENSORS

    monkeypatch.setattr(SENSORS["nisar"], "describe", lambda *a, **k: pytest.fail("scan must not describe a product"))
    assert len(scan(scene.data_dir)) == 2


# --- the large-area error carries its suggestion ---------------------------------------------------------------------------------

def test_the_large_area_error_carries_a_box_the_app_can_prefill():
    with pytest.raises(TooLarge) as e:
        _check_size(Area(32646, 500000, 3000000, 700000, 3190000))
    w, s, east, n = e.value.suggestion
    assert w < east and s < n and "--bbox" in str(e.value) and isinstance(e.value, ValueError)
    assert f"--bbox {w:.2f} {s:.2f} {east:.2f} {n:.2f}" in str(e.value)


def test_job_toml_is_the_saved_job(scene):
    _, raw = build_job([scene.data_dir / "L.h5"], data_dir=scene.data_dir)
    text = job_toml(raw)
    assert text.startswith("# Written by") and 'sensor = "nisar"' in text and "[[figures]]" in text


# --- the app, headless --------------------------------------------------------------------------------------------------------

@pytest.fixture
def app_env(scene, tmp_path, monkeypatch):
    monkeypatch.setenv("SATVIZ_DATA_DIR", str(scene.data_dir))
    monkeypatch.setenv("SATVIZ_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("SATVIZ_CACHE_DIR", str(tmp_path / "cache"))
    return scene


def run_app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    return at


def pick(at, *names):
    multi = at.sidebar.multiselect[0]
    multi.set_value([o for o in multi.options if o.split("  ·  ")[1] in names]).run()
    return at


def made(at) -> list:
    """The figures the app has made so far (not the example page, which is always on show)."""
    return at.session_state["results"] or []


def press(at, label):
    next(b for b in at.button if b.label == label).click().run()
    return at


@needs_streamlit
def test_the_app_lists_the_products_and_makes_a_figure(app_env):
    at = run_app()
    assert not at.exception and at.title[0].value == "satviz"
    assert {o.split("  ·  ")[1] for o in at.sidebar.multiselect[0].options} == {"L.h5", "S.h5"}
    assert next(b for b in at.button if b.label == "Make the figure").disabled  # nothing chosen yet
    assert any("choose a product" in c.value for c in at.warning)  # and the page says what to do
    pick(at, "L.h5", "S.h5")
    assert not at.warning and not at.success  # ready says nothing: the button is simply live
    press(at, "Make the figure")
    assert not at.exception and not at.error and len(made(at)) == 1
    assert [b.proto.label for b in at.get("download_button")] == ["Download PNG", "Download job file"]  # quick: no PDF


@needs_streamlit
def test_two_products_that_share_no_ground_are_refused_before_anything_is_drawn(app_env, tmp_path):
    far = make_raw(seed=5)
    far["x"] = far["x"] + 400_000  # a few degrees east: the same zone, no shared ground
    write_granule(app_env.data_dir / "F.h5", "science/LSAR/GCOV", far, instrument="LSAR", freq_hz=1.239e9)
    at = run_app()
    pick(at, "L.h5", "F.h5")
    assert any("do not overlap" in e.value for e in at.error)
    assert any("different ground" in w.value for w in at.warning)  # and the button says why it waits
    assert next(b for b in at.button if b.label == "Make the figure").disabled


@needs_streamlit
def test_only_two_products_can_be_chosen(app_env):
    assert at_max(run_app()) == 2


def at_max(at) -> int:
    return at.sidebar.multiselect[0].proto.max_selections


@needs_streamlit
def test_a_box_that_misses_a_product_says_so_and_can_leave_it_out(app_env):
    far = make_raw(seed=5)
    far["x"] = far["x"] + 400_000
    write_granule(app_env.data_dir / "F.h5", "science/LSAR/GCOV", far, instrument="LSAR", freq_hz=1.239e9)
    at = run_app()
    pick(at, "L.h5", "F.h5")
    at.radio(key="area_mode").set_value("A box I choose").run()
    from satviz.api import inspect

    w, s, e, n = inspect(app_env.data_dir / "L.h5")["bbox"]
    for key, value in zip(("box_w", "box_s", "box_e", "box_n"), (w, s, e, n), strict=True):
        at.number_input(key=key).set_value(value)
    at.run()
    assert any("outside" in e.value for e in at.error)
    assert next(b for b in at.button if b.label == "Make the figure").disabled
    press(at, "Leave out the products outside the box")
    assert not at.error and len(at.multiselect[0].value) == 1


@needs_streamlit
def test_a_large_area_offers_the_suggested_box(app_env, monkeypatch):
    monkeypatch.setattr("satviz.api.MAX_AUTO_KM2", 0.5)
    at = run_app()
    pick(at, "L.h5")
    press(at, "Make the figure")
    assert any("slow" in e.value for e in at.error)
    press(at, "Use the suggested box")
    assert at.radio(key="area_mode").value == "A box I choose"
    assert all(at.number_input(key=k).value != 0.0 for k in ("box_w", "box_s", "box_e", "box_n"))
    press(at, "Make the figure")  # the suggested box is now given, so the size check no longer applies
    assert not at.exception and not at.error and len(made(at)) == 1


@needs_streamlit
def test_publication_offers_a_pdf(app_env):
    at = run_app()
    pick(at, "L.h5")
    next(r for r in at.selectbox if r.label == "Quality").set_value("Quality: publication").run()
    press(at, "Make the figure")
    assert [b.proto.label for b in at.get("download_button")] == ["Download PNG", "Download PDF", "Download job file"]


@needs_streamlit
def test_the_launcher_makes_no_outside_connection_for_the_version_check():
    """Streamlit asks PyPI for its latest version on start-up; `satviz app` starts it through a line that stops that."""
    import subprocess
    import sys

    from satviz.cli import STREAMLIT_LAUNCH

    disable = "v.should_show_new_version_notice = lambda: False\n"
    assert disable.strip() in STREAMLIT_LAUNCH
    head = ("import socket\nattempts = []\n"
            "def watch(self, addr, *a):\n    attempts.append(addr)\n    raise OSError('blocked')\n"
            "socket.socket.connect = watch\n"
            "import streamlit.version as v\n"
            "v.CHECK_PYPI_PROBABILITY = 1.0\n")  # make the check certain, so a leak cannot hide behind the one-in-ten
    tail = "from streamlit.web import bootstrap\nbootstrap._print_new_version_message()\nprint('attempts', attempts)\n"
    run = lambda code: subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)  # noqa: E731
    out = run(head + disable + tail)
    assert out.stdout.strip().endswith("attempts []"), out.stdout + out.stderr
    leaky = run(head + tail)  # the check left on does try to connect, so the probe above can fail
    assert "443" in leaky.stdout, leaky.stdout + leaky.stderr  # connections to PyPI's https port


# --- the controls: theme, layout, the layout preview, the folder button, the area map ---------------------------------------------

def test_layout_choices_follow_what_is_chosen():
    from satviz.api import auto_layout, layout_choices

    assert list(layout_choices([])) == ["single", "compare", "bands"]  # nothing chosen yet: every layout
    assert list(layout_choices(["sar"])) == ["single"]
    assert list(layout_choices(["sar", "sar"])) == ["single", "compare"]
    assert list(layout_choices(["optical"])) == ["single", "bands"]
    assert list(layout_choices(["optical", "optical"])) == ["single", "compare", "bands"]
    assert list(layout_choices(["sar", "optical"])) == ["compare"]  # mixed kinds are never one figure each
    assert [auto_layout(k) for k in (["sar"], ["sar", "optical"])] == ["single", "compare"]


@pytest.mark.parametrize("theme", ["minimal", "neo_retro", "neo_brutal", "newspaper", "xkcd"])
@pytest.mark.parametrize("layout", ["single", "compare", "grid", "bands"])
def test_every_layout_and_theme_draws_an_example_page(layout, theme):
    import io

    from PIL import Image

    from satviz.preview import render_example

    page = Image.open(io.BytesIO(render_example(None, layout, theme)))
    assert page.size == (1200, 1500) and page.getbbox() is not None


def test_the_example_page_follows_the_kinds_chosen_and_says_it_is_an_example():
    import io

    import numpy as np
    from PIL import Image

    from satviz.preview import render_example

    sar = np.asarray(Image.open(io.BytesIO(render_example(["sar", "sar"], "compare", "minimal"))).convert("RGB"))
    mixed = np.asarray(Image.open(io.BytesIO(render_example(["sar", "optical"], "compare", "minimal"))).convert("RGB"))
    assert (sar != mixed).any()  # the right-hand panel is optical when an optical product is chosen
    from satviz.preview import example_product

    p = example_product("A1", "sar", 0)
    assert "Example notice" in p.caveats[0] and p.meta["label"] == "product A" and p.meta["platform"].startswith("Example")


@needs_streamlit
def test_the_theme_and_layout_controls(app_env):
    at = run_app()
    assert [s.label for s in at.selectbox] == ["Quality", "Theme", "Layout"]
    assert at.selectbox[1].value == "minimal" and "xkcd" in at.selectbox[1].options
    assert at.selectbox[2].options[0] == "Automatic" and len(at.selectbox[2].options) == 4  # Automatic + the three layouts
    pick(at, "L.h5", "S.h5")
    layout = next(s for s in at.selectbox if s.label == "Layout")
    assert layout.options == ["Automatic", "One figure per product", "Side by side"]
    layout.set_value("One figure per product").run()
    press(at, "Make the figure")
    assert not at.exception and not at.error and len(made(at)) == 2  # a figure for each product


@needs_streamlit
def test_the_example_page_is_on_show_before_anything_is_made(app_env):
    at = run_app()
    assert not at.exception and len(at.get("imgs")) == 1 and made(at) == []  # one pane, with the example page in it
    assert not at.get("tab")  # no separate preview pane
    assert any("page your settings give" in i.value for i in at.info)
    at.selectbox[1].set_value("newspaper").run()
    assert not at.exception and made(at) == []  # another theme draws another example page without making a figure


@needs_streamlit
def test_the_figure_gives_way_to_the_example_when_settings_change(app_env):
    at = run_app()
    pick(at, "L.h5")
    press(at, "Make the figure")
    assert len(made(at)) == 1 and len(at.get("imgs")) == 1 and not any("settings have changed" in i.value for i in at.info)
    at.selectbox[1].set_value("xkcd").run()  # a new theme: the figure on show is out of date
    assert not at.exception and any("settings have changed" in i.value for i in at.info)
    assert len(at.get("imgs")) >= 2  # the example page in this theme, and the earlier figure kept under "made before"
    at.selectbox[1].set_value("minimal").run()  # back to what the figure was made with: it is current again
    assert not any("settings have changed" in i.value for i in at.info) and len(at.get("imgs")) == 1


@needs_streamlit
def test_the_wording_is_the_same_for_every_sensor_and_reaches_the_job(app_env):
    at = run_app()
    pick(at, "L.h5")
    labels = [t.label for t in at.text_input]
    assert labels[1:8] == ["Title", "Subtitle", "Place", "Author", "Website", "Extra credit"][:7] or "Title" in labels
    for label, value in (("Title", "Brahmaputra at Dibrugarh"), ("Subtitle", "Seen by L-band"), ("Place", "Dibrugarh, Assam"),
                         ("Author", "Tester"), ("Website", "example.org"), ("Extra credit", "Photo {x} by me")):
        next(t for t in at.text_input if t.label == label).set_value(value)
    at.run()
    press(at, "Make the figure")
    assert not at.exception and not at.error and len(made(at)) == 1
    toml = made(at)[0]["toml"]
    for expected in ('name = "Brahmaputra at Dibrugarh"', 'region = "Dibrugarh, Assam"', 'author = "Tester"', 'website = "example.org"',
                     'subtitle = "Seen by L-band"', '"credits.lines"', "Photo {{x}} by me"):
        assert expected in toml, expected


def test_an_extra_credit_joins_the_author_line_and_never_replaces_the_required_ones():
    from satviz.api import details
    from satviz.layout import Layout, apply_text, default_layout
    from satviz.themes.base import assemble_credits

    required = [("Copernicus", "Contains modified Copernicus Sentinel data 2026")]

    def lines(**words):
        return assemble_credits(Layout(apply_text(default_layout("compare"), details(**words)[1]), {"byline": "X"}), required)

    both = lines(author="Tester", website="example.org", credits="Photo {x} by me")
    assert both[0] == "VIZ   TESTER  ·  example.org   ·   Photo {x} by me"  # one line: it costs a page with many notices no room
    assert len(both) == 2 and both[-1].startswith("DATA") and "COPERNICUS" in both[-1]  # the sensor's credit is still there
    assert lines(credits="Photo by me")[0] == "Photo by me"  # no author: the credit alone, not labelled as a visualisation credit
    assert lines() == ["VIZ   X", "DATA  CONTAINS MODIFIED COPERNICUS SENTINEL DATA 2026"]  # nothing typed: the layout's own


def test_details_and_the_saved_job(scene, tmp_path):
    from satviz.api import build_job, details
    from satviz.job import load_job

    assert details() == ({}, {}) and details("  ", None, "", None, None, " ") == ({}, {})  # blanks are nothing
    paths = [scene.data_dir / "L.h5"]
    job, raw = build_job(paths, data_dir=scene.data_dir, title="T", subtitle="S", place="P", author="A", website="w.org",
                         credits="C {x}")
    (tmp_path / "j.toml").write_text(__import__("satviz.api", fromlist=["job_toml"]).job_toml(raw))
    again = load_job(tmp_path / "j.toml", scene.data_dir)  # the saved file reads back to the same wording
    assert again.scene.name == "T" and again.scene.region == "P" and again.scene.author == "A" and again.scene.website == "w.org"
    assert again.figures[0].text == job.figures[0].text and again.figures[0].text["credits.lines"] == ["VIZ   A  ·  w.org   ·   C {{x}}"]


@needs_streamlit
def test_the_browse_button_sets_the_folder_from_the_system_dialog(app_env, tmp_path, monkeypatch):
    other = tmp_path / "elsewhere"
    other.mkdir()
    write_granule(other / "X.h5", "science/LSAR/GCOV", make_raw(seed=9), instrument="LSAR", freq_hz=1.239e9)
    monkeypatch.setattr("satviz.desktop.choose_folder", lambda start, title="": str(other))
    at = run_app()
    press(at, "Browse…")
    assert at.sidebar.text_input[0].value == str(other)
    assert [o.split("  ·  ")[1] for o in at.sidebar.multiselect[0].options] == ["X.h5"]


@needs_streamlit
def test_the_browse_button_says_what_to_do_when_no_dialog_can_open(app_env, monkeypatch):
    from satviz.desktop import DesktopError

    def no_desktop(start, title=""):
        raise DesktopError("could not open a folder dialog here (no display); type the folder's path instead")

    monkeypatch.setattr("satviz.desktop.choose_folder", no_desktop)
    at = run_app()
    press(at, "Browse…")
    assert not at.exception and any("type the folder's path" in c.value for c in at.sidebar.caption)
    assert at.sidebar.text_input[0].value == str(app_env.data_dir)  # unchanged


def test_choose_folder_runs_the_dialog_in_its_own_process(monkeypatch, tmp_path):
    import subprocess

    from satviz import desktop

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=f"{tmp_path}\n", stderr="")

    monkeypatch.setattr(desktop.subprocess, "run", fake_run)
    assert desktop.choose_folder(tmp_path) == str(tmp_path) and calls[0][-2] == str(tmp_path)
    monkeypatch.setattr(desktop.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="\n", stderr=""))
    assert desktop.choose_folder(tmp_path) is None  # cancelled
    monkeypatch.setattr(desktop.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 1, stdout="", stderr="_tkinter.TclError: no display name and no $DISPLAY environment variable"))
    with pytest.raises(desktop.DesktopError, match="type the folder's path"):
        desktop.choose_folder(tmp_path)


def test_a_drawn_box_fills_the_fields_and_clear_goes_back_to_the_overlap():
    pytest.importorskip("streamlit")
    from satviz.app import BOX, BOX_KEYS, OVERLAP, apply_drawn

    state = {"last_draw": 0, "area_mode": OVERLAP, **dict.fromkeys(BOX_KEYS, 0.0)}
    assert not apply_drawn(state, None) and state["area_mode"] == OVERLAP  # the map has sent nothing yet
    assert apply_drawn(state, {"box": [94.12345678, 27.2, 94.3, 27.4], "n": 1})
    assert [state[k] for k in BOX_KEYS] == [94.1235, 27.2, 94.3, 27.4] and state["area_mode"] == BOX
    state["box_w"] = 90.0  # the person edits a field by hand...
    assert not apply_drawn(state, {"box": [94.12345678, 27.2, 94.3, 27.4], "n": 1})  # ...and the map's old value does not undo it
    assert state["box_w"] == 90.0
    assert apply_drawn(state, {"box": None, "n": 2}) and state["area_mode"] == OVERLAP  # Clear
