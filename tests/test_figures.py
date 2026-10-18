"""Smoke tests: every figure renders from small synthetic granules and writes non-empty files."""
import importlib

import matplotlib
import pytest

matplotlib.use("Agg")

from nisar_viz.cli import FIGURES  # noqa: E402
from nisar_viz.io import load_roi  # noqa: E402


@pytest.mark.parametrize("name", list(FIGURES))
def test_figure_renders(name, scene, tmp_path):
    mod = importlib.import_module(FIGURES[name][0])
    bands = {b: load_roi(scene, b) for b in FIGURES[name][1]}
    out = tmp_path / "out"
    out.mkdir()
    paths = mod.render(scene, bands, out)
    assert paths and all(p.exists() and p.stat().st_size > 5000 for p in paths)


def test_social_pooled_stretch_variant(scene, tmp_path):
    from nisar_viz.figures import ls_social

    bands = {b: load_roi(scene, b) for b in "LS"}
    assert ls_social.render(scene, bands, tmp_path, per_band=False)[0].exists()
