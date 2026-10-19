"""Read an ROI from a NISAR GCOV HDF5 file and assemble the layers used by the figures."""
from __future__ import annotations

import logging
from pathlib import Path

import h5py
import numpy as np
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator

from satviz.config import BandSpec, Scene
from satviz.sensors.nisar_gcov.metadata import read_band_metadata
from satviz.sensors.nisar_gcov.processing import derive

log = logging.getLogger(__name__)


def read_roi(path: Path, spec: BandSpec) -> dict:
    """Raw ROI arrays straight from the file, with the noise layer interpolated onto the 10 m grid."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Put the granule there, pass --data-dir, or set SATVIZ_DATA_DIR/NISAR_DATA_DIR (README, 'Data')."
        )
    (r0, r1), (c0, c1) = spec.rows, spec.cols
    with h5py.File(path, "r") as f:
        g = f[f"{spec.group}/grids/frequencyA"]
        sl = (slice(r0, r1), slice(c0, c1))
        x = g["xCoordinates"][c0:c1]
        y = g["yCoordinates"][r0:r1]
        out = dict(
            x=x, y=y, epsg=int(g["projection"][()]),
            hh=g["HHHH"][sl].astype(np.float32), hv=g["HVHV"][sl].astype(np.float32),
            mask=g["mask"][sl], exc=g["inputDataExceptionMask"][sl],
            eta=g["rtcGammaToSigmaFactor"][sl].astype(np.float32),
        )
        nb = f[f"{spec.group}/metadata/calibrationInformation/frequencyA/noiseEquivalentBackscatter"]
        nx, ny = nb["xCoordinates"][:], nb["yCoordinates"][:]
        nhh, nhv = nb["HH"][:].astype(np.float64), nb["HV"][:].astype(np.float64)

    def interp(grid):
        # NEBS y is descending; RegularGridInterpolator needs ascending axes.
        yy, gg = (ny[::-1], grid[::-1]) if ny[0] > ny[-1] else (ny, grid)
        fn = RegularGridInterpolator((yy, nx), gg, bounds_error=False, fill_value=None)
        Y, X = np.meshgrid(y, x, indexing="ij")
        return fn(np.stack([Y.ravel(), X.ravel()], -1)).reshape(Y.shape).astype(np.float32)

    out["n_hh_raw"], out["n_hv_raw"] = interp(nhh), interp(nhv)
    return out


def assemble(raw: dict, band: str) -> dict:
    """Build the working dataset from raw ROI arrays.

    The ISRO format document (SAC-PR-NISAR-2024-051, 7.3.6.1) describes the noise layer as noise-equivalent
    sigma0. The covariance terms are gamma0 and sigma0 = eta * gamma0, so the gamma0-referenced floor is NEBS / eta.
    """
    eta = raw["eta"]
    with np.errstate(divide="ignore", invalid="ignore"):
        n_hh, n_hv = raw["n_hh_raw"] / eta, raw["n_hv_raw"] / eta
    hh, hv, mask = raw["hh"], raw["hv"], raw["mask"]
    valid = (mask >= 1) & (mask <= 5) & np.isfinite(hh) & np.isfinite(hv) & (hh > 0) & (hv > 0)
    epsg = raw["epsg"]
    d = dict(
        band=band, x=raw["x"], y=raw["y"], epsg=epsg, hh=hh, hv=hv, mask=mask, exc=raw["exc"], eta=eta,
        n_hh=n_hh, n_hv=n_hv, n_hh_raw=raw["n_hh_raw"], n_hv_raw=raw["n_hv_raw"], valid=valid,
        to_ll=Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True),
        to_utm=Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True),
    )
    return derive(d)


def _cache_file(cache_dir: Path, scene: Scene, spec: BandSpec) -> Path:
    (r0, r1), (c0, c1) = spec.rows, spec.cols
    return cache_dir / f"{scene.name.lower()}_{spec.key}_{r0}-{r1}_{c0}-{c1}.npz"


def load_roi(scene: Scene, band: str, cache_dir: str | Path | None = None) -> dict:
    """Load one band's ROI, optionally through an .npz cache (reading the multi-GB HDF5 is slow)."""
    spec = scene.bands[band]
    path = scene.band_path(band)
    raw = None
    cf = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cf = _cache_file(cache_dir, scene, spec)
        if cf.exists() and path.exists():
            st = path.stat()
            with np.load(cf) as z:
                if int(z["_size"]) == st.st_size and int(z["_mtime_ns"]) == st.st_mtime_ns:
                    raw = {k: z[k] for k in z.files if not k.startswith("_")}
                    raw["epsg"] = int(raw["epsg"])
                    log.info("cache hit: %s", cf.name)
    if raw is None:
        log.info("reading %s", path.name)
        raw = read_roi(path, spec)
        if cf is not None:
            st = path.stat()
            np.savez(cf, _size=st.st_size, _mtime_ns=st.st_mtime_ns, **raw)
    d = assemble(raw, band)
    d["meta"] = read_band_metadata(path, spec)  # acquisition facts come from the file, not from configuration
    return d
