from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from satviz.config import InputSpec
from satviz.core import TEMPLATES, Product
from satviz.job import FigureSpec, JobError, load_job
from satviz.registry import load_builtin
from satviz.relations import relate, time_gap
from satviz.run import run_job
from satviz.templates import TemplateError, default_recipe, pick_recipes
from tests.test_eos04 import product_folder as eos_folder
from tests.test_geotiff_sensors import needs_rasterio
from tests.test_liss4 import product_folder as liss_folder

load_builtin()
T0 = datetime(2026, 9, 25, 12, 0)


def sar(key, platform, band, wl, when=T0, backscatter="gamma0, terrain-corrected", **meta):
    z = np.ones((2, 2), np.float32)
    return Product(key=key, layers={"co": z, "cross": z}, x=np.arange(2.0), y=np.arange(2.0), epsg=32646, valid=z > 0, kind="sar",
                   meta=dict(platform=platform, label=platform, start=when, end=when, radar_band=band, wavelength_cm=wl,
                             backscatter=backscatter, **meta))


def optical(key, platform, when=T0, layers=("red", "green", "blue", "nir")):
    z = np.ones((2, 2), np.float32)
    return Product(key=key, layers={n: z for n in layers}, x=np.arange(2.0), y=np.arange(2.0), epsg=32646, valid=z > 0,
                   kind="optical", meta=dict(platform=platform, label=platform, start=when, end=when))


def test_sar_relation_kinds_are_read_from_the_products():
    l, s = sar("L", "NISAR", "L", 24.2), sar("S", "NISAR", "S", 9.4)
    c_eos = sar("E", "EOS-04", "C", 5.55, backscatter="gamma0, terrain-normalised")
    c_s1 = sar("S1", "Sentinel-1D", "C", 5.55, backscatter="sigma0, ellipsoid")
    assert relate([l, s]).kind == "same_sensor_different_bands" and relate([l, s]).label == "SAME SENSOR · L VS S BAND"
    assert relate([c_eos, c_s1]).kind == "same_band_different_sensors"
    assert relate([c_eos, c_s1]).label == "SAME BAND (C) · DIFFERENT SENSORS"
    assert relate([l, c_s1]).kind == "different_sensors_different_bands"
    assert relate([sar("a", "Sentinel-1D", "C", 5.55), sar("b", "Sentinel-1D", "C", 5.55)]).kind == "same_sensor_same_band"
    assert relate([l]).kind == "single"


def test_notes_state_wavelengths_time_gap_and_backscatter_mismatch():
    l = sar("L", "NISAR", "L", 24.2)
    s1 = sar("S1", "Sentinel-1D", "C", 5.55, when=T0 + timedelta(hours=11, minutes=9), backscatter="sigma0, ellipsoid")
    notes = " | ".join(relate([l, s1]).notes)
    assert "L-band 24.2 cm" in notes and "C-band 5.55 cm" in notes and "11 h 9 min" in notes
    assert "Backscatter differs (gamma0 vs sigma0)" in notes
    same = relate([sar("E", "EOS-04", "C", 5.55), sar("S", "Sentinel-1D", "C", 5.55)])
    assert not any("Backscatter" in n for n in same.notes)  # equal conventions: nothing to warn about


@pytest.mark.parametrize("hours, text", [(0, "same pass"), (2.5, "2 h 30 min apart"), (30, "1 day apart"), (24 * 6, "6 days apart")])
def test_time_gap_wording(hours, text):
    a, b = optical("a", "X"), optical("b", "Y", when=T0 + timedelta(hours=hours))
    assert text in time_gap([a, b])


def test_radar_and_optical_and_optical_relations():
    r = relate([sar("E", "EOS-04", "C", 5.55), optical("L4", "ResourceSat-2", when=T0 - timedelta(days=6))])
    assert r.kind == "sar_optical" and r.label == "RADAR AND OPTICAL" and r.notes == ("Acquired 6 days apart",)
    assert relate([optical("a", "Sentinel-2"), optical("b", "Sentinel-2")]).kind == "optical_same_sensor"
    assert relate([optical("a", "Sentinel-2"), optical("b", "Landsat 9")]).kind == "optical_different_sensors"


def test_a_date_without_time_compares_days_only():
    a = optical("a", "X")
    b = optical("b", "Y", when=T0 + timedelta(days=2))
    b.meta["time_known"] = False
    assert time_gap([a, b]) == "Acquired 2 days apart"


def test_default_recipe_follows_the_layers():
    assert default_recipe(optical("o", "S2")) == "true_colour"
    assert default_recipe(optical("o", "LISS-IV", layers=("green", "red", "nir"))) == "nir_fcc"  # no blue band
    assert default_recipe(sar("s", "EOS-04", "C", 5.55)) == "sar_fcc"
    with pytest.raises(TemplateError, match="no default recipe fits"):
        default_recipe(optical("o", "X", layers=("red",)), "o")
    named = pick_recipes({"default": "ndvi", "a": "true_colour"}, {"a": optical("a", "S2"), "b": optical("b", "S2")}, ("a", "b"))
    assert named == {"a": "true_colour", "b": "ndvi"}  # an input's own entry wins over `default`


def job_with(**kinds):
    inputs = {k: InputSpec(k, sensor, "", {}) for k, sensor in kinds.items()}
    return SimpleNamespace(inputs=inputs, path="job.toml")


def fig(template, ids, **kw):
    return FigureSpec(template=template, inputs=tuple(ids), **kw)


JOB = job_with(L="nisar_gcov", S="nisar_gcov", S1="sentinel1_grd", E="eos04", L4="liss4", O="sentinel2_l2a")


def test_plans_of_the_four_scenarios():
    t = TEMPLATES
    assert t["sar"].plan(fig("sar", "LSE"), JOB) == [("L",), ("S",), ("E",)]
    assert t["optical"].plan(fig("optical", ["L4", "O"]), JOB) == [("L4",), ("O",)]
    assert t["sar_vs_sar"].plan(fig("sar_vs_sar", ["L", "S", "S1"]), JOB) == [("L", "S"), ("L", "S1"), ("S", "S1")]
    assert t["sar_vs_sar"].plan(fig("sar_vs_sar", ["L", "S", "S1"], arrangement="grid"), JOB) == [("L", "S", "S1")]
    assert t["optical_sar"].plan(fig("optical_sar", ["L4", "E", "S1", "O"]), JOB) == [
        ("E", "L4"), ("E", "O"), ("S1", "L4"), ("S1", "O")]  # SAR on the left, whatever the listed order
    assert t["optical"].plan(fig("optical", ["L4", "O"], arrangement="compare"), JOB) == [("L4", "O")]


@pytest.mark.parametrize("template, ids, kw, match", [
    ("sar_vs_sar", ["L", "L4"], {}, "input 'L4' is optical"),
    ("sar", ["E", "L4"], {}, "takes sar inputs only"),
    ("optical_sar", ["E", "S1"], {}, "at least one SAR and one optical"),
    ("sar_vs_sar", ["L"], {}, "at least two SAR"),
    ("sar_vs_sar", ["L", "S"], {"arrangement": "single"}, "use arrangement 'compare' or 'grid'"),
    ("sar", ["L"], {"arrangement": "compare"}, "at least two inputs"),
    ("sar", ["L"], {"arrangement": "poster"}, "arrangement must be one of"),
])
def test_inputs_that_do_not_fit_are_refused_with_a_pointer(template, ids, kw, match):
    with pytest.raises(TemplateError, match=match):
        TEMPLATES[template].plan(fig(template, ids, **kw), JOB)


def test_generic_templates_add_no_scenario_wording():
    products = {"L": sar("L", "NISAR", "L", 24.2), "S": sar("S", "NISAR", "S", 9.4)}
    r = TEMPLATES["compare"].resolve(fig("compare", "LS"), ("L", "S"), products, SimpleNamespace(region="Somewhere"))
    assert r.text == {} and r.caveats == () and r.arrangement == "compare"
    r = TEMPLATES["sar_vs_sar"].resolve(fig("sar_vs_sar", "LS"), ("L", "S"), products, SimpleNamespace(region="Somewhere"))
    assert r.text["subtitle"] == "SAME SENSOR · L VS S BAND  ·  SOMEWHERE" and "L-band 24.2 cm" in r.caveats[0]


@needs_rasterio
def test_job_renders_radar_and_optical_from_two_isro_products(tmp_path):
    from pyproj import Transformer

    from tests.test_geotiff_sensors import EPSG, X0, Y0

    eos_folder(tmp_path)
    liss_folder(tmp_path)
    lon, lat = Transformer.from_crs(f"EPSG:{EPSG}", "EPSG:4326", always_xy=True).transform(X0 + 500, Y0 - 500)
    job = tmp_path / "job.toml"
    job.write_text(f'''
[scene]
name = "Test"
region = "Nowhere"
[area]
center = [{lat}, {lon}]
size_km = [0.6, 0.6]
resolution_m = 10
[[inputs]]
id = "E"
sensor = "eos04"
source = {{ path = "E04_scene" }}
[[inputs]]
id = "L4"
sensor = "liss4"
source = {{ path = "R2F_scene" }}
[[figures]]
name = "pair"
template = "optical_sar"
inputs = ["L4", "E"]
theme = ["minimal", "neo_retro"]
''')
    paths = run_job(load_job(job, tmp_path), tmp_path / "out")
    assert [p.name for p in paths] == ["pair_Minimal.png", "pair_NeoRetro.png"] and all(p.stat().st_size > 10_000 for p in paths)


def test_template_error_becomes_a_job_error(tmp_path):
    from tests.test_job import JOB as BASE  # NISAR L and S inputs

    p = tmp_path / "j.toml"
    p.write_text(BASE + '\n[[figures]]\ntemplate = "optical_sar"\ninputs = ["L", "S"]\n')
    with pytest.raises(JobError, match="at least one SAR and one optical"):
        run_job(load_job(p), tmp_path / "out")


def test_every_shipped_preset_loads_and_plans(tmp_path):
    """The starter job files (`satviz init <preset>`) must name templates and inputs that fit together."""
    from importlib.resources import files

    from satviz.run import plan_figure

    found = [p for p in files("satviz").joinpath("presets").iterdir() if p.name.endswith(".toml")]
    assert len(found) >= 5
    for preset in found:
        copy = tmp_path / preset.name
        copy.write_text(preset.read_text())
        job = load_job(copy, tmp_path)
        for f in job.figures:
            assert f.template in TEMPLATES and plan_figure(f, job), preset.name
