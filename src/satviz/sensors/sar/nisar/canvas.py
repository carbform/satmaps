"""Read a NISAR GCOV product onto a canvas: pick the window around the area, then align or resample every layer."""
from __future__ import annotations

import h5py
import numpy as np
from pyproj import Transformer

from satviz.area import AreaError, Canvas
from satviz.config import BandSpec
from satviz.core import SourceInfo, footprint_or_none
from satviz.grid import to_canvas

CONTINUOUS = ("hh", "hv", "eta", "n_hh_raw", "n_hv_raw", "s2", "s3")  # (s2, s3: compact-pol products only)
CLASSES = ("mask", "exc")
MARGIN = 2  # source pixels read beyond the canvas, for interpolation at the edges


def find_group(path) -> str:
    """HDF5 group of the GCOV product: science/LSAR/GCOV or science/SSAR/GCOV."""
    with h5py.File(path, "r") as f:
        for sar in f.get("science", {}):
            if f"science/{sar}/GCOV" in f:
                return f"science/{sar}/GCOV"
    raise ValueError(f"{path}: not a NISAR GCOV product (no science/*/GCOV group)")


def _bounding_ring(f, group: str) -> list[tuple[float, float]]:
    """(lon, lat) ring from the product's `identification/boundingPolygon` (WKT with a height after each point)."""
    wkt = f[f"{group.rsplit('/', 1)[0]}/identification/boundingPolygon"][()].decode()
    return [tuple(float(v) for v in p.split()[:2]) for p in wkt.split("((")[1].split("))")[0].split(",")]


def describe(path) -> SourceInfo:
    group = find_group(path)
    with h5py.File(path, "r") as f:
        g = f[f"{group}/grids/frequencyA"]
        x0, y0 = float(g["xCoordinates"][0]), float(g["yCoordinates"][0])
        res = abs(float(g["xCoordinateSpacing"][()]))
        ring = footprint_or_none(_bounding_ring, f, group)
        return SourceInfo(epsg=int(g["projection"][()]), resolution_m=res, phase=(x0, y0), files=[str(path)], footprint=ring)


def window(path, group: str, canvas: Canvas) -> BandSpec:
    """Rows and columns of the file that cover the canvas (plus a margin); error if the file does not cover it."""
    with h5py.File(path, "r") as f:
        g = f[f"{group}/grids/frequencyA"]
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        epsg = int(g["projection"][()])
    e = canvas.extent
    xs, ys = np.meshgrid(np.linspace(e[0], e[1], 9), np.linspace(e[2], e[3], 9))
    if epsg != canvas.epsg:
        xs, ys = Transformer.from_crs(f"EPSG:{canvas.epsg}", f"EPSG:{epsg}", always_xy=True).transform(xs, ys)
    dx, dy = abs(float(x[1] - x[0])), abs(float(y[1] - y[0]))
    c0 = int(np.searchsorted(x, xs.min() - MARGIN * dx))
    c1 = int(np.searchsorted(x, xs.max() + MARGIN * dx))
    r0 = int(np.searchsorted(-y, -(ys.max() + MARGIN * dy)))  # y is descending
    r1 = int(np.searchsorted(-y, -(ys.min() - MARGIN * dy)))
    if c1 - c0 < 2 or r1 - r0 < 2:
        lon, lat = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True).transform([x[0], x[-1]], [y[-1], y[0]])
        raise AreaError(f"the area is outside {path.name}, which covers about lon {lon[0]:.2f}..{lon[1]:.2f}, "
                        f"lat {lat[0]:.2f}..{lat[1]:.2f}")
    return BandSpec(key="win", file=path.name, group=group, rows=(r0, r1), cols=(c0, c1))


def decimation(path, group: str, canvas: Canvas) -> int:
    """How many native pixels make one canvas pixel along a side (1 when the canvas is not at least twice as coarse, or the file
    is in another CRS): the factor `read_roi` reduces by while reading."""
    with h5py.File(path, "r") as f:
        g = f[f"{group}/grids/frequencyA"]
        if int(g["projection"][()]) != canvas.epsg:
            return 1
        dx = abs(float(g["xCoordinateSpacing"][()]))
    k = int(round(canvas.res / dx))
    return k if k >= 2 else 1


def raw_on_canvas(raw: dict, canvas: Canvas) -> dict:
    """Raw ROI arrays (as from `read_roi`) resampled onto the canvas. Aligned grids are copied exactly."""
    sx, sy, epsg = raw["x"], raw["y"], raw["epsg"]
    out = dict(raw)
    for k in (k for k in CONTINUOUS if k in raw):
        out[k] = to_canvas(raw[k], sx, sy, epsg, canvas, "bilinear")
    for k in CLASSES:
        out[k] = to_canvas(raw[k], sx, sy, epsg, canvas, "nearest", fill=0)  # mask 0 = not valid
    out["x"], out["y"], out["epsg"] = canvas.x, canvas.y, canvas.epsg
    return out
