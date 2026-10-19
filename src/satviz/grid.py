"""Put a raster onto a canvas: exact slicing when the grids line up, resampling otherwise."""
from __future__ import annotations

import numpy as np
from pyproj import Transformer
from scipy.ndimage import map_coordinates

from satviz.area import Canvas

TOL = 1e-6


def _spacing(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    return abs(float(x[1] - x[0])), abs(float(y[1] - y[0]))


def is_aligned(src_x, src_y, src_epsg: int, canvas: Canvas) -> bool:
    """Same CRS, same pixel size, and pixel centres on the same lattice: copying is exact, no interpolation."""
    if src_epsg != canvas.epsg:
        return False
    dx, dy = _spacing(src_x, src_y)
    if abs(dx - canvas.res) > TOL or abs(dy - canvas.res) > TOL:
        return False
    for off in ((canvas.x[0] - src_x[0]) / dx, (src_y[0] - canvas.y[0]) / dy):
        if abs(off - round(off)) > 1e-4:
            return False
    return True


def _slice_aligned(arr, src_x, src_y, canvas: Canvas, fill):
    dx, dy = _spacing(src_x, src_y)
    ci = int(round((canvas.x[0] - src_x[0]) / dx))  # source column of canvas column 0
    rj = int(round((src_y[0] - canvas.y[0]) / dy))
    out = np.full((canvas.height, canvas.width), fill, dtype=arr.dtype)
    r0, c0 = max(0, -rj), max(0, -ci)
    r1, c1 = min(canvas.height, arr.shape[0] - rj), min(canvas.width, arr.shape[1] - ci)
    if r1 > r0 and c1 > c0:
        out[r0:r1, c0:c1] = arr[r0 + rj:r1 + rj, c0 + ci:c1 + ci]
    return out


def _block_mean(arr: np.ndarray, k: int) -> np.ndarray:
    """k x k mean over finite values (linear power averages correctly; NaN only where a whole block is empty)."""
    H, W = (arr.shape[0] // k) * k, (arr.shape[1] // k) * k
    a = arr[:H, :W].astype(np.float64).reshape(H // k, k, W // k, k)
    ok = np.isfinite(a)
    n = ok.sum(axis=(1, 3))
    s = np.where(ok, a, 0.0).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, s / n, np.nan).astype(np.float32)


def to_canvas(arr: np.ndarray, src_x: np.ndarray, src_y: np.ndarray, src_epsg: int, canvas: Canvas,
              method: str = "bilinear", fill=np.nan):
    """`arr` (pixel-centre coordinates `src_x` ascending, `src_y` descending) onto `canvas`.

    method: "bilinear" for continuous layers, "nearest" for masks and classes, which keep their dtype. When the canvas
    pixel is at least twice the source pixel, continuous layers are first block-averaged by that factor.
    Outside the source, pixels are `fill`."""
    if method not in ("bilinear", "nearest"):
        raise ValueError(f"unknown resampling method {method!r}")
    if is_aligned(src_x, src_y, src_epsg, canvas):
        return _slice_aligned(arr, src_x, src_y, canvas, fill)
    dx, dy = _spacing(src_x, src_y)
    if method == "bilinear" and src_epsg == canvas.epsg:
        k = int(round(canvas.res / dx))
        if k >= 2:
            arr = _block_mean(arr, k)
            src_x = src_x[: arr.shape[1] * k].reshape(-1, k).mean(1)
            src_y = src_y[: arr.shape[0] * k].reshape(-1, k).mean(1)
            dx, dy = dx * k, dy * k
    X, Y = np.meshgrid(canvas.x, canvas.y)
    if src_epsg != canvas.epsg:
        X, Y = Transformer.from_crs(f"EPSG:{canvas.epsg}", f"EPSG:{src_epsg}", always_xy=True).transform(X, Y)
    cols = (X - src_x[0]) / dx
    rows = (src_y[0] - Y) / dy
    order = 1 if method == "bilinear" else 0
    work = arr.astype(np.float32) if method == "bilinear" else arr
    out = map_coordinates(work, [rows, cols], order=order, mode="constant", cval=fill if method == "bilinear" else 0,
                          prefilter=False)
    if method == "nearest":
        inside = (rows >= -0.5) & (rows <= arr.shape[0] - 0.5) & (cols >= -0.5) & (cols <= arr.shape[1] - 0.5)
        out = np.where(inside, out, fill).astype(arr.dtype)
    else:
        inside = (rows >= -0.5) & (rows <= arr.shape[0] - 0.5) & (cols >= -0.5) & (cols <= arr.shape[1] - 0.5)
        out = np.where(inside, out, fill).astype(np.float32)
    return out
