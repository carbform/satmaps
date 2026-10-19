"""Smoke tests: every figure renders from small synthetic granules and writes non-empty files."""
import importlib

import matplotlib
import pytest

matplotlib.use("Agg")

from satviz.cli import FIGURES  # noqa: E402
from satviz.layout import load_layout  # noqa: E402
from satviz.sensors.nisar_gcov.io import load_roi  # noqa: E402


@pytest.mark.parametrize("name", list(FIGURES))
def test_figure_renders(name, scene, tmp_path, layouts_dir):
    fig = FIGURES[name]
    mod = importlib.import_module(fig.module)
    bands = {b: load_roi(scene, b) for b in fig.bands}
    out = tmp_path / "out"
    out.mkdir()
    paths = mod.render(scene, bands, out, load_layout(layouts_dir, fig.layout), **fig.kwargs)
    assert paths and all(p.exists() and p.stat().st_size > 5000 for p in paths)


def test_social_pooled_stretch_variant(scene, tmp_path, layouts_dir):
    from satviz.figures import ls_social

    bands = {b: load_roi(scene, b) for b in "LS"}
    assert ls_social.render(scene, bands, tmp_path, load_layout(layouts_dir, "ls_social"), per_band=False)[0].exists()
