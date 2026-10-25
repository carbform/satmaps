"""Read an ROI from a NISAR GCOV HDF5 file and assemble the layers used by the figures."""
from __future__ import annotations

import logging
from pathlib import Path

import h5py
import numpy as np
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator

from satviz.config import BandSpec, Scene
from satviz.grid import _block_mean
from satviz.sensors.sar.nisar.metadata import read_band_metadata
from satviz.sensors.sar.nisar.processing import derive

log = logging.getLogger(__name__)


CACHE_VERSION = "v2"  # raw arrays changed shape with polarisation sets: older cache files are not read


class PolarisationError(ValueError):
    """The product's polarisations are not ones satviz draws."""


def pol_set(g) -> dict:
    """The terms of a GCOV grid group that satviz draws, from the file's own lists: `co` and `cross` are the first two power
    terms (HHHH/HVHV, else VVVV/VHVH, else the compact RHRH/RVRV, which also has the complex RHRV), `noise` their names in the
    noise layer, `pols` the two polarisations, `compact` whether the product is compact-pol (circular transmit)."""
    listed = g["listOfCovarianceTerms"][()] if "listOfCovarianceTerms" in g else list(g)  # (no list: the datasets present)
    terms = {t.decode() if isinstance(t, bytes) else str(t) for t in listed}
    for co, cross, noise, compact in (("HHHH", "HVHV", ("HH", "HV"), False), ("VVVV", "VHVH", ("VV", "VH"), False),
                                      ("RHRH", "RVRV", ("RH", "RV"), True)):
        if {co, cross} <= terms and (not compact or "RHRV" in terms):
            return dict(co=co, cross=cross, noise=noise, pols=noise, compact=compact)
    raise PolarisationError(f"covariance terms {', '.join(sorted(terms))}: satviz draws products with HH+HV, VV+VH or compact "
                            "RH+RV (RHRH, RVRV, RHRV); single-polarisation and co-polarised pairs are not drawn")


STRIP = 64  # output rows per strip when a read is decimated: bounds the memory of a whole-frame read


def _strips(ds, r0: int, r1: int, c0: int, c1: int, k: int, mean: bool) -> np.ndarray:
    """The window of `ds` reduced k x k, a strip of rows at a time: block mean over finite values (continuous layers) or
    the centre pixel of each block (masks and classes). Row and column counts are multiples of k."""
    out = []
    for a in range(r0, r1, STRIP * k):
        b = min(a + STRIP * k, r1)
        block = ds[a:b, c0:c1]
        out.append(_block_mean(block, k) if mean else block[k // 2::k, k // 2::k])
    return np.concatenate(out)


class _Part:
    """A complex dataset seen as its real or imaginary part, so `_strips` reads it a strip at a time."""

    def __init__(self, ds, part):
        self.ds, self.part = ds, part

    def __getitem__(self, key):
        return self.part(self.ds[key]).astype(np.float32)


def read_roi(path: Path, spec: BandSpec, k: int = 1) -> dict:
    """Raw ROI arrays straight from the file, with the noise layer interpolated onto the grid. With `k` > 1 every layer is
    reduced k x k while it is read (a coarse canvas never needs the full-resolution window in memory)."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Put the granule there, pass --data-dir, or set SATVIZ_DATA_DIR/NISAR_DATA_DIR (README, 'Data')."
        )
    (r0, r1), (c0, c1) = spec.rows, spec.cols
    if k > 1:
        r1, c1 = r1 - (r1 - r0) % k, c1 - (c1 - c0) % k
    with h5py.File(path, "r") as f:
        g = f[f"{spec.group}/grids/frequencyA"]
        ps = pol_set(g)
        x = g["xCoordinates"][c0:c1]
        y = g["yCoordinates"][r0:r1]
        if k == 1:
            sl = (slice(r0, r1), slice(c0, c1))
            out = dict(
                x=x, y=y, epsg=int(g["projection"][()]),
                hh=g[ps["co"]][sl].astype(np.float32), hv=g[ps["cross"]][sl].astype(np.float32),
                mask=g["mask"][sl], exc=g["inputDataExceptionMask"][sl],
                eta=g["rtcGammaToSigmaFactor"][sl].astype(np.float32),
            )
        else:
            x, y = x.reshape(-1, k).mean(1), y.reshape(-1, k).mean(1)
            out = dict(
                x=x, y=y, epsg=int(g["projection"][()]),
                hh=_strips(g[ps["co"]], r0, r1, c0, c1, k, True), hv=_strips(g[ps["cross"]], r0, r1, c0, c1, k, True),
                mask=_strips(g["mask"], r0, r1, c0, c1, k, False),
                exc=_strips(g["inputDataExceptionMask"], r0, r1, c0, c1, k, False),
                eta=_strips(g["rtcGammaToSigmaFactor"], r0, r1, c0, c1, k, True),
            )
        if ps["compact"]:  # RHRV is complex: its Stokes parts S2 = 2 Re, S3 = -2 Im, as real layers (the averaging is linear)
            cross = g["RHRV"]
            if k == 1:
                z = cross[r0:r1, c0:c1]
                out["s2"], out["s3"] = (2 * z.real).astype(np.float32), (-2 * z.imag).astype(np.float32)
            else:
                out["s2"] = 2 * _strips(_Part(cross, np.real), r0, r1, c0, c1, k, True)
                out["s3"] = -2 * _strips(_Part(cross, np.imag), r0, r1, c0, c1, k, True)
        out["pols"] = np.array(ps["pols"])
        nb = f[f"{spec.group}/metadata/calibrationInformation/frequencyA/noiseEquivalentBackscatter"]
        nx, ny = nb["xCoordinates"][:], nb["yCoordinates"][:]
        nhh, nhv = nb[ps["noise"][0]][:].astype(np.float64), nb[ps["noise"][1]][:].astype(np.float64)

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
    extra = {k: raw[k] for k in ("s2", "s3") if k in raw}  # compact-pol Stokes parts
    d = dict(
        **extra, pols=tuple(str(p) for p in raw.get("pols", ("HH", "HV"))),
        band=band, x=raw["x"], y=raw["y"], epsg=epsg, hh=hh, hv=hv, mask=mask, exc=raw["exc"], eta=eta,
        n_hh=n_hh, n_hv=n_hv, n_hh_raw=raw["n_hh_raw"], n_hv_raw=raw["n_hv_raw"], valid=valid,
        to_ll=Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True),
        to_utm=Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True),
    )
    return derive(d)


def _cache_file(cache_dir: Path, tag: str, spec: BandSpec, k: int = 1) -> Path:
    (r0, r1), (c0, c1) = spec.rows, spec.cols
    return cache_dir / f"{tag.lower()}_{spec.key}_{r0}-{r1}_{c0}-{c1}{f'_x{k}' if k > 1 else ''}_{CACHE_VERSION}.npz"


def load_raw(path: Path, spec: BandSpec, cache_dir: str | Path | None = None, tag: str = "scene", k: int = 1) -> dict:
    """Raw ROI arrays, optionally through an .npz cache (reading the multi-GB HDF5 is slow)."""
    raw = None
    cf = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cf = _cache_file(cache_dir, tag, spec, k)
        if cf.exists() and path.exists():
            st = path.stat()
            with np.load(cf) as z:
                if int(z["_size"]) == st.st_size and int(z["_mtime_ns"]) == st.st_mtime_ns:
                    raw = {k: z[k] for k in z.files if not k.startswith("_")}
                    raw["epsg"] = int(raw["epsg"])
                    log.info("cache hit: %s", cf.name)
    if raw is None:
        log.info("reading %s", path.name)
        raw = read_roi(path, spec, k)
        if cf is not None:
            st = path.stat()
            np.savez(cf, _size=st.st_size, _mtime_ns=st.st_mtime_ns, **raw)
    return raw


def load_roi(scene: Scene, band: str, cache_dir: str | Path | None = None) -> dict:
    """Load one band's ROI (rows/cols from the scene config), optionally through an .npz cache."""
    spec = scene.bands[band]
    path = scene.band_path(band)
    d = assemble(load_raw(path, spec, cache_dir, scene.name), band)
    d["meta"] = read_band_metadata(path, spec)  # acquisition facts come from the file, not from configuration
    return d
