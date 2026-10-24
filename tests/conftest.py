from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest
from pyproj import Transformer

from satviz.config import BandSpec, Scene, Zoom
from satviz.sensors.sar.nisar.io import assemble

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


def write_granule(path: Path, group: str, raw: dict, *, instrument: str = "SSAR", freq_hz: float = 3.2e9, calibrated: bool = False,
                  rfi: str = "FDNF", start: str = "2026-09-25T22:57:40.10308051", crid: str = "P00500", track: int = 112) -> None:
    """Minimal HDF5 file with the GCOV layout and the metadata that `satviz.sensors.sar.nisar.io` / `satviz.sensors.sar.nisar.metadata` read."""
    root = group.rsplit("/", 1)[0]
    with h5py.File(path, "w") as f:
        g = f.create_group(f"{group}/grids/frequencyA")
        g["xCoordinates"], g["yCoordinates"] = raw["x"], raw["y"]
        g["xCoordinateSpacing"] = 10.0
        g["projection"] = np.uint32(raw["epsg"])
        g["listOfPolarizations"] = np.array([b"HH", b"HV"])
        g["HHHH"], g["HVHV"] = raw["hh"], raw["hv"]
        g["mask"], g["inputDataExceptionMask"] = raw["mask"], raw["exc"]
        g["rtcGammaToSigmaFactor"] = raw["eta"]
        g["numberOfLooks"] = np.full(raw["hh"].shape, 16.0 if instrument == "SSAR" else np.nan, np.float32)
        m = f.create_group(f"{group}/metadata")
        sw = m.create_group("sourceData/swaths/frequencyA")
        sw["centerFrequency"] = freq_hz
        sw["rangeBandwidth"] = 37.5e6
        par = m.create_group("processingInformation/parameters")
        par["rfiMitigationApplied"] = rfi.encode()
        for k, v in (("noiseCorrectionApplied", "False"), ("polarimetricSymmetrizationApplied", "False"),
                     ("rangeIonosphericGeolocationCorrectionApplied", "False"), ("azimuthIonosphericGeolocationCorrectionApplied", "False")):
            par[k] = v.encode()
        for pol in ("HH", "HV"):
            m[f"calibrationInformation/frequencyA/{pol}/scaleFactor"] = 27000.0 if calibrated else 0.0
        nb = m.create_group("calibrationInformation/frequencyA/noiseEquivalentBackscatter")
        # coarse noise grid with descending y, as in the real products
        nx = np.linspace(raw["x"][0] - 100, raw["x"][-1] + 100, 5)
        ny = np.linspace(raw["y"][0] + 100, raw["y"][-1] - 100, 4)
        nb["xCoordinates"], nb["yCoordinates"] = nx, ny
        nb["HH"] = np.full((4, 5), 10 ** (NEBS_DB / 10))
        nb["HV"] = np.full((4, 5), 10 ** (NEBS_DB / 10))
        ident = f.create_group(f"{root}/identification")
        for k, v in (("instrumentName", instrument), ("radarBand", instrument[0]), ("granuleId", path.stem), ("compositeReleaseId", crid),
                     ("productVersion", "1.0"), ("productSpecificationVersion", "1.2.1"), ("processingCenter", "TEST"),
                     ("orbitPassDirection", "Ascending"), ("lookDirection", "Left"), ("zeroDopplerStartTime", start),
                     ("zeroDopplerEndTime", start[:17] + "59.0")):
            ident[k] = v.encode()
        ident["trackNumber"], ident["frameNumber"], ident["hasInputDataException"] = track, 16, 0
        x0, x1, y0, y1 = raw["x"][0], raw["x"][-1], raw["y"][-1], raw["y"][0]
        corners = Transformer.from_crs(raw["epsg"], 4326, always_xy=True).transform([x0, x1, x1, x0, x0], [y1, y1, y0, y0, y1])
        ident["boundingPolygon"] = ("POLYGON ((" + ",".join(f"{lo} {la} 0" for lo, la in zip(*corners, strict=True)) + "))").encode()


@pytest.fixture
def scene(tmp_path) -> Scene:
    """Scene over two synthetic granules (L slightly brighter than S) with zoom windows that fit the tiny ROI."""
    write_granule(tmp_path / "S.h5", "science/SSAR/GCOV", make_raw(seed=1))
    write_granule(tmp_path / "L.h5", "science/LSAR/GCOV", make_raw(seed=2, shift_db=1.5), instrument="LSAR", freq_hz=1.239e9,
                  calibrated=True, rfi="False", start="2026-09-25T22:57:40.0", crid="P05023")
    bands = {
        "S": BandSpec("S", "S.h5", "science/SSAR/GCOV", (0, H), (0, W)),
        "L": BandSpec("L", "L.h5", "science/LSAR/GCOV", (0, H), (0, W)),
    }
    zooms = (Zoom("A", "ONE", (5, 35), (5, 60)), Zoom("B", "TWO", (40, 70), (10, 70)), Zoom("C", "THREE", (80, 110), (30, 90)))
    return Scene(
        name="Testland", reach="Test reach", locality="Nowhere", region="Nowhere, Testland", callout_caption="with callouts (crosses)",
        author="Tester", website="example.org", bands=bands, zooms=zooms, callouts={"p": (27.0, 94.0)}, data_dir=tmp_path,
    )


@pytest.fixture
def layouts_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "jobs" / "layouts"
