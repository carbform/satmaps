from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from nisar_viz.config import BandSpec, Scene, Zoom
from nisar_viz.io import assemble

H, W = 120, 110
NEBS_DB = -22.0  # sigma0-referenced noise-equivalent backscatter
ETA = 0.7


def make_raw(seed: int = 0, shift_db: float = 0.0) -> dict:
    """Synthetic ROI: land with HV well above the noise floor, plus a 'water' block with HV below it."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    base = -8 + 4 * np.sin(xx / 15.0) + 3 * np.cos(yy / 20.0) + shift_db
    hh = 10 ** ((base + rng.normal(0, 1.5, (H, W))) / 10)
    hv = 10 ** ((base - 7 + rng.normal(0, 1.5, (H, W))) / 10)
    water = (yy > 70) & (xx < 60)
    hv[water] = 10 ** ((-26 + rng.normal(0, 1.0, water.sum())) / 10)
    hh[water] = 10 ** ((-20 + rng.normal(0, 1.0, water.sum())) / 10)
    return dict(
        x=500000.0 + 10 * np.arange(W), y=3000000.0 - 10 * np.arange(H), epsg=32646,
        hh=hh.astype(np.float32), hv=hv.astype(np.float32),
        mask=np.ones((H, W), np.uint8), exc=np.zeros((H, W), np.uint8),
        eta=np.full((H, W), ETA, np.float32),
        n_hh_raw=np.full((H, W), 10 ** (NEBS_DB / 10), np.float32),
        n_hv_raw=np.full((H, W), 10 ** (NEBS_DB / 10), np.float32),
    )


@pytest.fixture
def raw():
    return make_raw()


@pytest.fixture
def ds(raw):
    return assemble(raw, "S")


def write_granule(path: Path, group: str, raw: dict) -> None:
    """Minimal HDF5 file with the GCOV layout that `nisar_viz.io.read_roi` reads."""
    with h5py.File(path, "w") as f:
        g = f.create_group(f"{group}/grids/frequencyA")
        g["xCoordinates"], g["yCoordinates"] = raw["x"], raw["y"]
        g["projection"] = np.uint32(raw["epsg"])
        g["HHHH"], g["HVHV"] = raw["hh"], raw["hv"]
        g["mask"], g["inputDataExceptionMask"] = raw["mask"], raw["exc"]
        g["rtcGammaToSigmaFactor"] = raw["eta"]
        nb = f.create_group(f"{group}/metadata/calibrationInformation/frequencyA/noiseEquivalentBackscatter")
        # coarse noise grid with descending y, as in the real products
        nx = np.linspace(raw["x"][0] - 100, raw["x"][-1] + 100, 5)
        ny = np.linspace(raw["y"][0] + 100, raw["y"][-1] - 100, 4)
        nb["xCoordinates"], nb["yCoordinates"] = nx, ny
        nb["HH"] = np.full((4, 5), 10 ** (NEBS_DB / 10))
        nb["HV"] = np.full((4, 5), 10 ** (NEBS_DB / 10))


@pytest.fixture
def scene(tmp_path) -> Scene:
    """Scene over two synthetic granules (L slightly brighter than S) with zoom windows that fit the tiny ROI."""
    for key, group, shift in (("S", "science/SSAR/GCOV", 0.0), ("L", "science/LSAR/GCOV", 1.5)):
        write_granule(tmp_path / f"{key}.h5", group, make_raw(seed=1 if key == "S" else 2, shift_db=shift))
    bands = {
        "S": BandSpec("S", "S.h5", "science/SSAR/GCOV", (0, H), (0, W), 3.2, 9, "P00500"),
        "L": BandSpec("L", "L.h5", "science/LSAR/GCOV", (0, H), (0, W), 1.239, 24, "P05023"),
    }
    zooms = (Zoom("A", "ONE", (5, 35), (5, 60)), Zoom("B", "TWO", (40, 70), (10, 70)), Zoom("C", "THREE", (80, 110), (30, 90)))
    return Scene(
        name="Testland", reach="Test reach", locality="Nowhere", region="Nowhere, Testland", callout_caption="with callouts (crosses)",
        date="1 Jan 2026", time_utc="00:00", track=1, frame=2, posting_m=10, crs_label="UTM 46N", s_mode="test mode",
        author="Tester", website="example.org", bands=bands, zooms=zooms,
        callouts={"p": (27.0, 94.0)}, data_dir=tmp_path,
    )
