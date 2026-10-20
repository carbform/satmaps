"""Smoke tests: every figure renders from small synthetic granules and writes non-empty files."""
import importlib

import matplotlib
import pytest

matplotlib.use("Agg")

from satviz.cli import FIGURES  # noqa: E402
from satviz.layout import load_layout  # noqa: E402
from satviz.sensors.nisar_gcov import load as load_product  # noqa: E402
from tests.conftest import inputs_for  # noqa: E402


@pytest.mark.parametrize("name", list(FIGURES))
def test_figure_renders(name, scene, tmp_path, layouts_dir):
    fig = FIGURES[name]
    mod = importlib.import_module(fig.module)
    bands = inputs_for(scene, fig)
    out = tmp_path / "out"
    out.mkdir()
    paths = mod.render(scene, bands, out, load_layout(layouts_dir, fig.layout), **fig.kwargs)
    assert paths and all(p.exists() and p.stat().st_size > 5000 for p in paths)


def test_social_pooled_stretch_variant(scene, tmp_path, layouts_dir):
    from satviz.arrangements import compare as ls_social

    bands = {b: load_product(scene, b) for b in "LS"}
    assert ls_social.render(scene, bands, tmp_path, load_layout(layouts_dir, "ls_social"), per_band=False)[0].exists()


@pytest.mark.parametrize("theme", ["minimal", "neo_brutal", "neo_retro"])
@pytest.mark.parametrize("name", ["ls-social", "sband-social"])
def test_social_figures_render_in_every_theme(name, theme, scene, tmp_path, layouts_dir):
    fig = FIGURES[name]
    mod = importlib.import_module(fig.module)
    bands = inputs_for(scene, fig)
    paths = mod.render(scene, bands, tmp_path, load_layout(layouts_dir, fig.layout), theme=theme, **fig.kwargs)
    assert paths[0].exists() and paths[0].stat().st_size > 5000
    from satviz.core import THEMES

    assert THEMES[theme].tag in paths[0].name


def test_unknown_theme_lists_available(scene, tmp_path, layouts_dir):
    from satviz.arrangements import compare as ls_social

    bands = {b: load_product(scene, b) for b in "LS"}
    with pytest.raises(KeyError, match="neo_brutal"):
        ls_social.render(scene, bands, tmp_path, load_layout(layouts_dir, "ls_social"), theme="nope")


def test_compare_takes_inputs_in_any_order(scene, tmp_path, layouts_dir):
    from satviz.arrangements import compare

    prods = {b: load_product(scene, b) for b in "LS"}
    out = compare.render(scene, prods, tmp_path, load_layout(layouts_dir, "ls_social"), inputs=("S", "L"))[0]
    assert out.name == "NISAR_Testland_SvsL_Social_NeoRetro.png"


def test_compare_rejects_inputs_on_different_grids(scene, tmp_path, layouts_dir):
    from satviz.arrangements import compare

    prods = {b: load_product(scene, b) for b in "LS"}
    prods["L"].x = prods["L"].x + 500.0
    with pytest.raises(ValueError, match="one grid"):
        compare.render(scene, prods, tmp_path, load_layout(layouts_dir, "ls_social"))


def test_layout_without_legend_and_notes_uses_the_recipe_and_product(scene, tmp_path, layouts_dir):
    import copy

    from satviz.arrangements import single

    lay = copy.deepcopy(load_layout(layouts_dir, "sband_social"))
    del lay["how_to_read"]["items"], lay["notes"]
    out = single.render(scene, {"S": load_product(scene, "S")}, tmp_path, lay, input="S")[0]
    assert out.exists()
