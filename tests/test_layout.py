import pytest

from satmaps.layout import Layout, LayoutError, build_context, load_layout
from satmaps.sensors.sar.nisar.io import load_roi
from satmaps.sensors.sar.nisar.processing import stats


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


def test_different_passes_are_rejected_when_the_figure_wants_one_pass(scene, tmp_path):
    from tests.conftest import make_raw, write_granule

    write_granule(tmp_path / "L.h5", "science/LSAR/GCOV", make_raw(2), instrument="LSAR", freq_hz=1.239e9, track=113)
    bands = {b: load_roi(scene, b) for b in "LS"}
    with pytest.raises(LayoutError, match="not from the same pass"):
        build_context(scene, bands, {b: stats(d) for b, d in bands.items()}, per_band=True, strict=True)


def test_shipped_layouts_render(scene, layouts_dir, tmp_path):
    """Every wording example (jobs/layouts) must parse and use only placeholders that exist."""
    from tests.test_figures import EXAMPLES, render_example

    shipped = {p.stem for p in layouts_dir.glob("*.toml")}
    assert shipped == set(EXAMPLES), shipped  # a new example needs an entry in EXAMPLES, so it is rendered here
    for name in shipped:
        assert render_example(name, scene, tmp_path, layouts_dir), name


def test_editing_a_layout_changes_the_figure_text(scene, layouts_dir, tmp_path):
    import copy

    from satmaps.arrangements import compare as ls_social
    from satmaps.sensors.sar.nisar import load as load_product

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
    from satmaps.layout import build_context_products
    from satmaps.sensors.sar.nisar import load as load_product
    from tests.conftest import make_raw, write_granule

    write_granule(tmp_path / "L.h5", "science/LSAR/GCOV", make_raw(2), instrument="LSAR", freq_hz=1.239e9, track=113)
    prods = {b: load_product(scene, b) for b in "LS"}
    ctx = build_context_products(scene, prods, strict=False)
    assert "track" not in ctx and ctx["frame"] == 16  # the disputed value is left out, the agreed one kept
    lay = Layout({"_path": "x.toml", "h": {"t": "TRACK {track}"}}, ctx)
    with pytest.raises(LayoutError, match="unknown placeholder"):  # a layout that relies on it fails loudly
        lay.text("h.t")
    with pytest.raises(LayoutError, match="same_pass"):
        build_context_products(scene, prods, strict=True)


def test_required_credits_are_merged_into_one_data_line_and_never_dropped():
    from satmaps.themes.base import assemble_credits

    lay = Layout({"_path": "x.toml", "credits": {"lines": ["VIZ  ME"]}}, {})
    need = [("NISAR", "NISAR L2 GCOV · γ⁰"), ("Copernicus Sentinel", "Contains modified Copernicus Sentinel data 2026"),
            ("NISAR", "NISAR L2 GCOV · γ⁰")]
    out = assemble_credits(lay, need)
    assert out == ["VIZ  ME", "DATA  NISAR L2 GCOV · γ⁰  ·  CONTAINS MODIFIED COPERNICUS SENTINEL DATA 2026"]
    covered = Layout({"_path": "x.toml", "credits": {"lines": ["DATA  nisar, copernicus sentinel"]}}, {})
    assert assemble_credits(covered, need[:2]) == ["DATA  nisar, copernicus sentinel"]  # already credited: nothing added


def test_dates_form_a_range_and_times_are_not_listed_when_days_differ(scene):
    from datetime import datetime

    from satmaps.layout import _dates_label, _times, acquisition_label, build_context_products
    from satmaps.sensors.sar.nisar import load as load_product

    assert _dates_label([datetime(2026, 9, 25, 22, 57)] * 2) == "25 Sep 2026"
    assert _dates_label([datetime(2026, 9, 25, 22, 57), datetime(2026, 9, 24, 4, 30)]) == "24 – 25 Sep 2026"
    assert _dates_label([datetime(2026, 8, 28), datetime(2026, 9, 3)]) == "28 Aug – 3 Sep 2026"
    prods = {b: load_product(scene, b) for b in "LS"}
    prods["S"].meta["start"] = datetime(2026, 9, 24, 4, 30)
    ctx = build_context_products(scene, prods, strict=False)
    assert ctx["date"] == "24 – 25 Sep 2026" and ctx["times_utc"] == "" and ctx["times_label"] == ""  # no unpairable times
    assert acquisition_label(prods["S"].meta) == "24 Sep 04:30" and acquisition_label(prods["L"].meta).startswith("25 Sep")
    prods["S"].meta["time_known"] = False
    assert acquisition_label(prods["S"].meta) == "24 Sep"
    same_day = {b: load_product(scene, b) for b in "LS"}
    assert _times({k: p.meta for k, p in same_day.items()}) == "22:57"  # same day: unchanged behaviour


def test_attribution_can_require_several_fragments():
    from satmaps.themes.base import assemble_credits

    lay = Layout({"_path": "x.toml", "credits": {"lines": ["DATA  Contains modified Copernicus Sentinel data 2026"]}}, {})
    need = [(("Copernicus Sentinel", "Catalyst"), "Contains modified Copernicus Sentinel data 2026; RTC by Catalyst (CC BY 4.0)")]
    out = assemble_credits(lay, need)
    assert len(out) == 2 and "CATALYST" in out[1]  # Copernicus alone is not enough: the processor is credited too
    both = Layout({"_path": "x.toml", "credits": {"lines": ["DATA  copernicus sentinel; catalyst"]}}, {})
    assert assemble_credits(both, need) == ["DATA  copernicus sentinel; catalyst"]
