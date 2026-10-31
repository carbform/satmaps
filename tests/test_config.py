from pathlib import Path

from satmaps.config import DATA_DIR_ENV, BandSpec, InputSpec, Scene
from satmaps.job import load_job
from tests.test_job import JOB


def write_job(tmp_path):
    p = tmp_path / "job.toml"
    p.write_text(JOB)
    return p


def test_data_dir_precedence_for_a_job(monkeypatch, tmp_path):
    p = write_job(tmp_path)
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "env"))
    assert load_job(p).scene.data_dir == tmp_path / "env"  # the environment beats the default
    assert load_job(p, tmp_path / "arg").scene.data_dir == tmp_path / "arg"  # an argument beats the environment
    monkeypatch.delenv(DATA_DIR_ENV)
    monkeypatch.chdir(tmp_path)
    assert load_job(p).scene.data_dir == tmp_path.resolve()  # no ./data: next to the job file
    (tmp_path / "data").mkdir()
    assert load_job(p).scene.data_dir == Path("data")  # ./data is picked up when present


def test_inputs_and_nisar_bands_describe_the_same_scene(tmp_path):
    kw = dict(name="x", reach="", locality="", region="", callout_caption="", author="", website="", zooms=(), callouts={},
              data_dir=tmp_path)
    bands = {"S": BandSpec("S", "S.h5", "science/SSAR/GCOV", (0, 10), (5, 20))}
    from_bands = Scene(bands=bands, **kw)
    assert from_bands.inputs["S"] == InputSpec("S", "nisar", "S.h5", dict(group="science/SSAR/GCOV", rows=[0, 10], cols=[5, 20]))
    from_inputs = Scene(inputs=from_bands.inputs, **kw)
    assert from_inputs.bands == bands and from_inputs.input_path("S") == tmp_path / "S.h5"
