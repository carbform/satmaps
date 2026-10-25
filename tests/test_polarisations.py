"""NISAR products other than HH+HV: compact-pol (RH, RV, RHRV) and VV+VH."""
import numpy as np
import pytest

from satviz.config import BandSpec
from satviz.core import RECIPES
from satviz.job import load_job
from satviz.recipes import sar_compact
from satviz.registry import load_builtin
from satviz.run import run_job
from satviz.sensors.sar.nisar import to_product
from satviz.sensors.sar.nisar.io import assemble, read_roi
from satviz.sensors.sar.nisar.metadata import read_band_metadata
from satviz.templates.base import default_recipe
from tests.conftest import H, W, make_raw, write_granule


def compact_scene(tmp_path, stokes, name="C.h5"):
    """A compact-pol granule whose every pixel has the Stokes vector `stokes` = (S0, S1, S2, S3), noise-free."""
    s0, s1, s2, s3 = stokes
    rh, rv = (s0 + s1) / 2, (s0 - s1) / 2
    raw = make_raw(seed=3)
    raw["hh"], raw["hv"] = np.full((H, W), rh, np.float32), np.full((H, W), rv, np.float32)
    z = (s2 - 1j * s3) / 2  # RHRV: S2 = 2 Re, S3 = -2 Im
    write_granule(tmp_path / name, "science/SSAR/GCOV", raw, pols=("RH", "RV"), rhrv=np.full((H, W), z))
    return tmp_path / name


def load_compact(path):
    """The working dataset of a synthetic granule (the whole ROI, no canvas)."""
    spec = BandSpec("C", path.name, "science/SSAR/GCOV", (0, H), (0, W))
    d = assemble(read_roi(path, spec), "C")
    d["meta"] = read_band_metadata(path, spec)
    return d


def test_a_compact_pol_product_is_read_with_its_own_terms_and_gets_the_compact_recipe(tmp_path):
    load_builtin()
    d = load_compact(compact_scene(tmp_path, (1.0, 0.0, 0.0, 0.0)))
    assert d["pols"] == ("RH", "RV") and {"s2", "s3"} <= set(d)
    p = to_product(d)
    assert default_recipe(p) == "sar_compact"
    with pytest.raises(ValueError, match="sar_compact"):  # the linear composite would mislabel it
        RECIPES["sar_fcc"].render(p)


def channels(tmp_path, stokes, name):
    """Median power of each mechanism for a granule whose every pixel has these Stokes parameters."""
    ok, ch = sar_compact.decompose(load_compact(compact_scene(tmp_path, stokes, name)))
    assert ok.mean() > 0.99
    return {k: float(np.median(v[ok])) for k, v in ch.items()}


def test_the_decomposition_separates_the_three_mechanisms(tmp_path):
    odd = channels(tmp_path, (1.0, 0.0, 0.0, 1.0), "odd.h5")  # S3 = -2 Im RHRV: positive is a surface return, as fixed on real ground
    assert odd["ODD"] > 0.9 and odd["DBL"] < 0.01 and odd["VOL"] < 0.01
    dbl = channels(tmp_path, (1.0, 0.0, 0.0, -1.0), "dbl.h5")
    assert dbl["DBL"] > 0.9 and dbl["ODD"] < 0.01 and dbl["VOL"] < 0.01
    vol = channels(tmp_path, (1.0, 0.0, 0.0, 0.0), "vol.h5")  # unpolarised: all volume
    assert vol["VOL"] > 0.9 and vol["ODD"] < 0.01 and vol["DBL"] < 0.01


def test_a_compact_pol_job_renders(tmp_path):
    path = compact_scene(tmp_path, (1.0, 0.2, 0.1, 0.3))
    job = tmp_path / "j.toml"
    job.write_text(f'''[scene]
name = "T"
[area]
center = [27.12, 93.0]
size_km = [0.5, 0.5]
resolution_m = 10
[[inputs]]
id = "C"
sensor = "nisar"
source = {{ path = "{path.name}" }}
[[figures]]
template = "sar"
inputs = ["C"]
''')
    assert run_job(load_job(job, tmp_path), tmp_path / "out")[0].exists()


def test_a_vv_vh_product_is_drawn_with_its_own_labels(tmp_path):
    load_builtin()
    write_granule(tmp_path / "V.h5", "science/SSAR/GCOV", make_raw(seed=4), pols=("VV", "VH"))
    p = to_product(load_compact(tmp_path / "V.h5"))
    assert default_recipe(p) == "sar_fcc"
    texts = [i.text for i in RECIPES["sar_fcc"].render(p).legend]
    assert texts[:3] == ["RED = VV  (SURFACE)", "GREEN = VH  (VOLUME)", "BLUE = VV−VH  (RATIO)"]
