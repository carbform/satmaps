import pytest

from satviz.layout import Layout, LayoutError, build_context, load_layout
from satviz.sensors.nisar_gcov.io import load_roi
from satviz.sensors.nisar_gcov.processing import stats


@pytest.fixture
def ctx(scene):
    bands = {b: load_roi(scene, b) for b in "LS"}
    return build_context(scene, bands, {b: stats(d) for b, d in bands.items()}, per_band=True), bands


def test_facts_come_from_the_files(ctx):
    c, _ = ctx
    assert c["date"] == "25 Sep 2026" and c["time_utc"] == "22:57" and c["track"] == 112 and c["frame"] == 16
    assert c["crs"] == "UTM 46N" and c["posting_m"] == 10 and c["pass_direction"] == "ascending"
    assert c["L"].crid == "P05023" and c["S"].crid == "P00500"
    assert round(c["L"].wavelength_cm) == 24 and round(c["S"].wavelength_cm) == 9


def test_calibration_state_is_derived_not_typed(ctx):
    c, _ = ctx
    assert c["uncal_bands"] == "S-band" and c["cal_bands"] == "L-band"


def test_upper_variants_exist(ctx):
    c, _ = ctx
    assert c["name_upper"] == "TESTLAND" and c["date_upper"] == "25 SEP 2026"


def test_render_with_format_spec_and_attributes(ctx):
    c, _ = ctx
    lay = Layout({"_path": "x.toml", "a": {"t": "L ≈{L.wavelength_cm:.0f} cm, track {track}"}}, c)
    assert lay.text("a.t") == "L ≈24 cm, track 112"


def test_unknown_placeholder_is_reported_with_file_and_choices(ctx):
    c, _ = ctx
    lay = Layout({"_path": "x.toml", "a": {"t": "{nope}"}}, c)
    with pytest.raises(LayoutError, match=r"x\.toml.*unknown placeholder \{nope\}.*Available"):
        lay.text("a.t")


def test_bad_attribute_is_reported(ctx):
    c, _ = ctx
    lay = Layout({"_path": "x.toml", "a": {"t": "{L.nope}"}}, c)
    with pytest.raises(LayoutError, match="bad placeholder"):
        lay.text("a.t")


def test_missing_key_is_reported(ctx):
    c, _ = ctx
    with pytest.raises(LayoutError, match=r"missing key \[a.b\]"):
        Layout({"_path": "x.toml", "a": {}}, c).text("a.b")


def test_conditional_lines_follow_the_metadata(ctx):
    c, _ = ctx
    data = {"n": {"lines": [{"if": "uncal_bands", "text": "{uncal_bands} not calibrated"}, "always", {"if": "stretch_warning_none", "text": "x"}]}}
    lay = Layout({"_path": "x.toml", **data}, {**c, "stretch_warning_none": ""})
    assert lay.lines("n.lines") == ["S-band not calibrated", "always"]
    both = Layout({"_path": "x.toml", **data}, {**c, "uncal_bands": "", "stretch_warning_none": ""})
    assert both.lines("n.lines") == ["always"]  # warning disappears once the scale factors are populated


def test_line_limit(ctx):
    c, _ = ctx
    with pytest.raises(LayoutError, match="at most 1"):
        Layout({"_path": "x.toml", "n": {"lines": ["a", "b"]}}, c).lines("n.lines", limit=1)


def test_different_passes_are_rejected(scene, tmp_path):
    from tests.conftest import make_raw, write_granule

    write_granule(tmp_path / "L.h5", "science/LSAR/GCOV", make_raw(2), instrument="LSAR", freq_hz=1.239e9, track=113)
    bands = {b: load_roi(scene, b) for b in "LS"}
    with pytest.raises(LayoutError, match="not from the same pass"):
        build_context(scene, bands, {b: stats(d) for b, d in bands.items()}, per_band=True)


def test_shipped_layouts_render(scene, layouts_dir, tmp_path):
    """Every shipped layout file must parse and use only placeholders that exist."""
    import importlib

    from satviz.cli import FIGURES
    from tests.conftest import inputs_for

    for name, fig in FIGURES.items():
        mod = importlib.import_module(fig.module)
        have = inputs_for(scene, fig)
        assert mod.render(scene, have, tmp_path, load_layout(layouts_dir, fig.layout), **fig.kwargs), name


def test_editing_a_layout_changes_the_figure_text(scene, layouts_dir, tmp_path):
    import copy

    from satviz.sensors.nisar_gcov import load as load_product
    from satviz.templates import compare as ls_social

    bands = {b: load_product(scene, b) for b in "LS"}
    lay = copy.deepcopy(load_layout(layouts_dir, "ls_social"))
    lay["header"]["title"] = "A CUSTOM TITLE"
    lay["notes"]["lines"] = ["ONE NOTE ONLY"]
    lay["credits"]["lines"] = ["CREDIT {website}"]
    out = ls_social.render(scene, bands, tmp_path, lay)[0]
    assert out.exists()
    lay["how_to_read"]["items"] = lay["how_to_read"]["items"] * 2
    with pytest.raises(LayoutError, match="at most 6"):
        ls_social.render(scene, bands, tmp_path, lay)


def test_products_with_differing_passes_are_allowed_when_not_strict(scene, tmp_path):
    from satviz.layout import build_context_products
    from satviz.sensors.nisar_gcov import load as load_product
    from tests.conftest import make_raw, write_granule

    write_granule(tmp_path / "L.h5", "science/LSAR/GCOV", make_raw(2), instrument="LSAR", freq_hz=1.239e9, track=113)
    prods = {b: load_product(scene, b) for b in "LS"}
    assert build_context_products(scene, prods, strict=False)["track"] == 112  # reference input is the first in the scene
