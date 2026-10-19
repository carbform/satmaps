from pathlib import Path

import pytest

from satviz.config import DATA_DIR_ENV, load_scene

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "brahmaputra.toml"


def test_brahmaputra_config_parses():
    s = load_scene(CONFIG, "/data")
    assert s.name == "Brahmaputra" and set(s.bands) == {"L", "S"}
    assert [z.key for z in s.zooms] == ["A", "B", "C"]
    assert set(s.callouts) == {"simen", "bars"}
    assert s.bands["S"].rows[1] - s.bands["S"].rows[0] == s.bands["L"].rows[1] - s.bands["L"].rows[0]
    assert s.bands["S"].cols[1] - s.bands["S"].cols[0] == s.bands["L"].cols[1] - s.bands["L"].cols[0]


def test_data_dir_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "env"))
    assert load_scene(CONFIG).data_dir == tmp_path / "env"
    assert load_scene(CONFIG, tmp_path / "arg").data_dir == tmp_path / "arg"
    monkeypatch.delenv(DATA_DIR_ENV)
    monkeypatch.delenv("NISAR_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert load_scene(CONFIG).data_dir == Path.cwd()
    (tmp_path / "data").mkdir()
    assert load_scene(CONFIG).data_dir == Path("data")  # ./data is picked up when present


def test_band_path_joins_data_dir(tmp_path):
    s = load_scene(CONFIG, tmp_path)
    assert s.band_path("L") == tmp_path / s.bands["L"].file


def test_missing_key_is_reported():
    with pytest.raises(KeyError):
        load_scene(CONFIG, "/data").bands["X"]


def test_legacy_env_var_still_honoured(tmp_path, monkeypatch):
    monkeypatch.delenv("SATVIZ_DATA_DIR", raising=False)
    monkeypatch.setenv("NISAR_DATA_DIR", str(tmp_path / "legacy"))
    assert load_scene(CONFIG).data_dir == tmp_path / "legacy"


def test_inputs_form_and_legacy_bands_form_agree(tmp_path):
    new = load_scene(CONFIG, tmp_path)
    assert list(new.inputs) == ["S", "L"] and new.inputs["S"].sensor == "nisar_gcov"
    legacy = tmp_path / "legacy.toml"
    text = CONFIG.read_text()
    text = text.replace('[[inputs]]\nid = "S"\nsensor = "nisar_gcov"\n', "[bands.S]\n").replace('[[inputs]]\nid = "L"\nsensor = "nisar_gcov"\n', "[bands.L]\n")
    legacy.write_text(text)
    old = load_scene(legacy, tmp_path)
    assert old.inputs == new.inputs and old.bands == new.bands


def test_scene_needs_inputs(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[scene]\nname="x"\nreach="x"\nlocality="x"\nregion="x"\ncallout_caption="x"\nauthor="x"\nwebsite="x"\n')
    with pytest.raises(KeyError, match="inputs"):
        load_scene(cfg)
