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


def press(at, label):
    next(b for b in at.button if b.label == label).click().run()
    return at


@needs_streamlit
def test_the_app_lists_the_products_and_makes_a_figure(app_env):
    at = run_app()
    assert not at.exception and at.title[0].value == "satviz"
    assert {o.split("  ·  ")[1] for o in at.sidebar.multiselect[0].options} == {"L.h5", "S.h5"}
    assert next(b for b in at.button if b.label == "Make the figure").disabled  # nothing chosen yet
    pick(at, "L.h5", "S.h5")
    press(at, "Make the figure")
    assert not at.exception and not at.error and len(at.get("imgs")) == 1
    assert [b.proto.label for b in at.get("download_button")] == ["Download PNG", "Download job file"]  # quick: no PDF


@needs_streamlit
def test_the_app_shows_a_missing_overlap_as_a_message_not_a_traceback(app_env, tmp_path):
    far = make_raw(seed=5)
    far["x"] = far["x"] + 5_000_000  # another UTM zone's worth of metres away
    write_granule(app_env.data_dir / "F.h5", "science/LSAR/GCOV", far, instrument="LSAR", freq_hz=1.239e9)
    at = run_app()
    pick(at, "L.h5", "F.h5")
    press(at, "Make the figure")
    assert not at.exception and any("do not overlap" in e.value for e in at.error) and not at.get("imgs")


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
    assert not at.exception and not at.error and len(at.get("imgs")) == 1


@needs_streamlit
def test_publication_offers_a_pdf(app_env):
    at = run_app()
    pick(at, "L.h5")
    at.radio[0].set_value("publication").run()
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
