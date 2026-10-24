import pytest

from satviz.cli import build_parser, main
from tests.test_job import JOB


def test_parser_knows_the_job_commands_and_nothing_else():
    p = build_parser()
    assert p.parse_args(["run", "job.toml", "--out", "o"]).cmd == "run"
    assert p.parse_args(["placeholders", "job.toml"]).job == "job.toml"
    assert p.parse_args(["init"]).preset is None
    for gone in ("render", "stats"):  # the NISAR-only commands were removed with legacy/
        with pytest.raises(SystemExit):
            p.parse_args([gone])


def test_missing_data_gives_actionable_error(tmp_path, capsys):
    job = tmp_path / "j.toml"
    job.write_text(JOB)
    assert main(["run", str(job), "--data-dir", str(tmp_path), "--out", str(tmp_path / "o"), "--no-cache"]) == 2
    assert "--data-dir" in capsys.readouterr().err


def test_cli_list(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "sensors: eos04, liss4, nisar, sentinel1, sentinel2" in out
    assert "themes: minimal, neo_brutal, neo_retro, newspaper, xkcd" in out and "sar_optical" in out and "figures:" not in out


def test_placeholders_lists_what_a_wording_file_of_the_job_can_use(scene, tmp_path, capsys):
    job = tmp_path / "j.toml"
    job.write_text(JOB)
    assert main(["placeholders", str(job), "--data-dir", str(scene.data_dir), "--no-cache"]) == 0
    out = capsys.readouterr().out
    for placeholder in ("{name} =", "{date} =", "{crs} =", "{L.wavelength_cm}", "{S.freq_ghz}", "{S.noisy_hv_pct}"):
        assert placeholder in out, placeholder
    assert "_upper" not in out  # the upper-case forms are implied, not listed


def test_placeholders_reports_a_bad_job_instead_of_a_traceback(tmp_path, capsys):
    assert main(["placeholders", str(tmp_path / "missing.toml")]) == 2
    assert "not found" in capsys.readouterr().err
