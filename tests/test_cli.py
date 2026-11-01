import pytest

from satmaps.cli import build_parser, main
from tests.test_job import JOB


def test_parser_knows_the_job_commands_and_nothing_else():
    p = build_parser()
    assert p.parse_args(["run", "job.toml", "--out", "o"]).cmd == "run"
    assert p.parse_args(["placeholders", "job.toml"]).job == "job.toml"
    assert p.parse_args(["check", "job.toml"]).job == "job.toml"
    assert p.parse_args(["quick", "a.h5", "--open"]).open is True
    assert p.parse_args(["run", "job.toml", "--open"]).open is True
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
    assert "themes: minimal, neo_brutal, newspaper, retro_80s, xkcd" in out and "sar_optical" in out and "figures:" not in out


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


def test_cli_quick_supports_fcc_presets(scene, tmp_path):
    rc = main(["quick", str(scene.data_dir / "L.h5"), "--sar-fcc", "vegetation", "--out", str(tmp_path),
               "--no-cache", "--data-dir", str(scene.data_dir)])
    assert rc == 0
    pngs = list(tmp_path.glob("*.png"))
    assert len(pngs) >= 1


def test_cli_check_valid_job(scene, tmp_path, capsys):
    job = tmp_path / "valid.toml"
    job.write_text(JOB)
    rc = main(["check", str(job), "--data-dir", str(scene.data_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Result: OK" in out
    assert "TOML syntax: valid" in out
    assert "L: nisar (sar)" in out
    assert "S: nisar (sar)" in out


def test_cli_check_missing_job_file(tmp_path, capsys):
    rc = main(["check", str(tmp_path / "nonexistent.toml")])
    assert rc == 2
    out = capsys.readouterr().out
    assert "Job file not found" in out
    assert "Result: FAILED" in out


def test_cli_check_invalid_toml(tmp_path, capsys):
    job = tmp_path / "broken.toml"
    job.write_text("broken = [")
    rc = main(["check", str(job)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "TOML syntax error" in out
    assert "Result: FAILED" in out


def test_cli_check_missing_input_file(scene, tmp_path, capsys):
    job = tmp_path / "missing_input.toml"
    job.write_text(JOB.replace("L.h5", "not_there.h5"))
    rc = main(["check", str(job), "--data-dir", str(scene.data_dir)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "Result: FAILED" in out
    assert "nothing matches" in out or "not found" in out


def test_cli_check_invalid_theme(scene, tmp_path, capsys):
    bad_theme_job = JOB + '\n[[figures]]\ntemplate = "sar"\ntheme = "cyberpunk_neon"\n'
    job = tmp_path / "bad_theme.toml"
    job.write_text(bad_theme_job)
    rc = main(["check", str(job), "--data-dir", str(scene.data_dir)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "unknown theme 'cyberpunk_neon'" in out
    assert "Result: FAILED" in out


def test_cli_open_flag_in_quick_and_run(scene, tmp_path, monkeypatch):
    opened = []

    def mock_open(path):
        opened.append(path)
        return True

    monkeypatch.setattr("satmaps.cli.open_in_viewer", mock_open)

    # Test satmaps quick --open
    rc = main(["quick", str(scene.data_dir / "L.h5"), "--out", str(tmp_path / "q"),
               "--open", "--no-cache", "--data-dir", str(scene.data_dir)])
    assert rc == 0
    assert len(opened) == 1
    assert opened[0].suffix == ".png"

    # Test satmaps run --open
    job = tmp_path / "j.toml"
    job.write_text(JOB)
    rc = main(["run", str(job), "--out", str(tmp_path / "r"),
               "--open", "--no-cache", "--data-dir", str(scene.data_dir)])
    assert rc == 0
    assert len(opened) == 2


def test_progress_reporter():
    import io

    from satmaps.progress import Progress, get_progress

    buf = io.StringIO()
    with Progress(stream=buf, verbose=True) as p:
        assert get_progress() is p
        p.update("Processing step A")
        p.ticker(5, 10, "Decimating")
        p.done("Finished")

    assert get_progress() is None
    out = buf.getvalue()
    assert "[satmaps] Processing step A\n" in out
    assert "Decimating" in out
    assert "Finished\n" in out

    # Test quiet mode
    quiet_buf = io.StringIO()
    with Progress(stream=quiet_buf, quiet=True) as p:
        p.update("Silent")
        p.ticker(1, 2)
        p.done()
    assert quiet_buf.getvalue() == ""

