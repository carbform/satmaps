import pytest

from satviz.cli import FIGURES, build_parser, main


def test_parser_accepts_all_and_named_figures():
    p = build_parser()
    assert p.parse_args(["render", "all"]).figures == ["all"]
    assert p.parse_args(["render", "ls-clean", "ls-social", "--pooled-stretch"]).pooled_stretch
    assert set(FIGURES) == {"ls-social", "ls-publication", "ls-clean", "sband-publication", "sband-social", "lband-social"}


def test_unknown_figure_is_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["render", "nope"])


def test_missing_data_gives_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="--data-dir"):
        main(["render", "ls-clean", "--data-dir", str(tmp_path), "--out", str(tmp_path / "o"), "--no-cache"])


def test_cli_list(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "sensors: nisar_gcov" in out and "themes: minimal, neo_brutal, neo_retro" in out and "figures:" in out


def test_legacy_alias_module_runs_the_same_cli():
    import importlib.util

    assert importlib.util.find_spec("nisar_viz.__main__") is not None
