"""Smoke tests: the wording examples (jobs/layouts) render through the arrangements from small synthetic granules."""
import matplotlib
import pytest

matplotlib.use("Agg")

from satmaps.layout import load_layout  # noqa: E402
from satmaps.sensors.sar.nisar import load as load_product  # noqa: E402

EXAMPLES = {"ls_social": ("compare", ("L", "S")), "sband_social": ("single", ("S",))}


def render_example(name, scene, out, layouts_dir, **kw):
    from satmaps.arrangements import compare, single

    arrangement, ids = EXAMPLES[name]
    prods = {b: load_product(scene, b) for b in ids}
    lay = load_layout(layouts_dir, name)
    if arrangement == "compare":
        return compare.render(scene, prods, out, lay, inputs=ids, **kw)
    return single.render(scene, prods, out, lay, input=ids[0], chip_slot="b", **kw)


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_wording_example_renders(name, scene, tmp_path, layouts_dir):
    paths = render_example(name, scene, tmp_path, layouts_dir)
    assert paths and all(p.exists() and p.stat().st_size > 5000 for p in paths)


def test_social_pooled_stretch_variant(scene, tmp_path, layouts_dir):
    from satmaps.arrangements import compare as ls_social

    bands = {b: load_product(scene, b) for b in "LS"}
    assert ls_social.render(scene, bands, tmp_path, load_layout(layouts_dir, "ls_social"), per_band=False)[0].exists()


@pytest.mark.parametrize("theme", ["minimal", "neo_brutal", "newspaper", "retro_80s", "xkcd"])
@pytest.mark.parametrize("name", list(EXAMPLES))
def test_wording_examples_render_in_every_theme(name, theme, scene, tmp_path, layouts_dir):
    from satmaps.core import THEMES

    paths = render_example(name, scene, tmp_path, layouts_dir, theme=theme)
    assert paths[0].exists() and paths[0].stat().st_size > 5000 and THEMES[theme].tag in paths[0].name


def test_unknown_theme_lists_available(scene, tmp_path, layouts_dir):
    from satmaps.arrangements import compare as ls_social

    bands = {b: load_product(scene, b) for b in "LS"}
    with pytest.raises(KeyError, match="neo_brutal"):
        ls_social.render(scene, bands, tmp_path, load_layout(layouts_dir, "ls_social"), theme="nope")


def test_compare_takes_inputs_in_any_order(scene, tmp_path, layouts_dir):
    from satmaps.arrangements import compare

    prods = {b: load_product(scene, b) for b in "LS"}
    out = compare.render(scene, prods, tmp_path, load_layout(layouts_dir, "ls_social"), inputs=("S", "L"))[0]
    assert out.name == "NISAR_Testland_SvsL_Social_Retro80s.png"


def test_compare_rejects_inputs_on_different_grids(scene, tmp_path, layouts_dir):
    from satmaps.arrangements import compare

    prods = {b: load_product(scene, b) for b in "LS"}
    prods["L"].x = prods["L"].x + 500.0
    with pytest.raises(ValueError, match="one grid"):
        compare.render(scene, prods, tmp_path, load_layout(layouts_dir, "ls_social"))


def test_layout_without_legend_and_notes_uses_the_recipe_and_product(scene, tmp_path, layouts_dir):
    import copy

    from satmaps.arrangements import single

    lay = copy.deepcopy(load_layout(layouts_dir, "sband_social"))
    del lay["how_to_read"]["items"], lay["notes"]
    out = single.render(scene, {"S": load_product(scene, "S")}, tmp_path, lay, input="S")[0]
    assert out.exists()
