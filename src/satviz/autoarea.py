"""The area of a job that names none: the largest rectangle inside where every input has data.

Each sensor reports a footprint ring (lon, lat) from its own metadata. Grid extents would not do: a Sentinel-1 swath, an EOS-04
scene and a NISAR frame all carry nodata wedges inside their bounding boxes, so a box that passes the overlap test can still hold
no common data. The rings are intersected on a coarse grid in the UTM zone of the overlap, the mask is eroded a little, and the
largest axis-aligned rectangle left in it becomes the `Area`. An empty overlap is an error that names the inputs.
"""
from __future__ import annotations

import numpy as np
from matplotlib.path import Path as Ring
from scipy.ndimage import binary_erosion

from satviz.area import Area, AreaError, _tf, utm_epsg

GRID = 400  # cells along the longer side of the overlap's bounding box
ERODE = 2  # cells shaved off the overlap so the canvas edge stays inside the data
MIN_SIDE_KM = 1.0
NO_OVERLAP_FIX = "Give an [area] to draw one place anyway."
NICE_M = (10, 20, 30, 50, 60, 100, 150, 200, 250, 300, 500, 1000, 2000)


def largest_rectangle(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """(row0, row1, col0, col1) of the largest all-True rectangle (histogram method), or None for an empty mask."""
    heights = np.zeros(mask.shape[1], int)
    best, box = 0, None
    for r, row in enumerate(mask):
        heights = np.where(row, heights + 1, 0)
        stack: list[tuple[int, int]] = []  # (start column, height), heights increasing
        for c, h in enumerate([*heights, 0]):
            start = c
            while stack and stack[-1][1] >= h:
                start, top = stack.pop()
                if top * (c - start) > best:
                    best, box = top * (c - start), (r - top + 1, r + 1, start, c)
            stack.append((start, h))
    return box


def common_area(footprints: dict[str, list[tuple[float, float]]]) -> Area:
    """The largest rectangle inside every footprint (a dict input id -> (lon, lat) ring)."""
    rings = {k: np.asarray(v, float) for k, v in footprints.items()}
    w = max(r[:, 0].min() for r in rings.values())
    e = min(r[:, 0].max() for r in rings.values())
    s = max(r[:, 1].min() for r in rings.values())
    n = min(r[:, 1].max() for r in rings.values())
    names = ", ".join(rings)
    if not (w < e and s < n):
        raise AreaError(f"the inputs ({names}) do not overlap: their footprints share no area. {NO_OVERLAP_FIX}")
    lat0, lon0 = (s + n) / 2, (w + e) / 2
    epsg = utm_epsg(lat0, lon0)
    to_utm, to_ll = _tf(4326, epsg), _tf(epsg, 4326)
    xs, ys = to_utm.transform([w, e, w, e], [s, s, n, n])
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    step = max(x1 - x0, y1 - y0) / GRID
    cols, rows = int(np.ceil((x1 - x0) / step)), int(np.ceil((y1 - y0) / step))
    X, Y = np.meshgrid(x0 + step * (np.arange(cols) + 0.5), y1 - step * (np.arange(rows) + 0.5))  # row 0 is north
    lon, lat = to_ll.transform(X.ravel(), Y.ravel())
    pts = np.column_stack([lon, lat])
    mask = np.ones(len(pts), bool)
    for r in rings.values():
        mask &= Ring(r).contains_points(pts)
    mask = binary_erosion(mask.reshape(rows, cols), iterations=ERODE)
    box = largest_rectangle(mask)
    if box is None:
        raise AreaError(f"the inputs ({names}) do not overlap: their footprints share no area. {NO_OVERLAP_FIX}")
    r0, r1, c0, c1 = box
    if min(r1 - r0, c1 - c0) * step < MIN_SIDE_KM * 1000:
        raise AreaError(f"the inputs ({names}) overlap in a sliver under {MIN_SIDE_KM:g} km: nothing to draw. "
                        + NO_OVERLAP_FIX)
    return Area(epsg, x0 + c0 * step, y1 - r1 * step, x0 + c1 * step, y1 - r0 * step)


def pick_resolution(area: Area, finest_native_m: float, target_px: int) -> float:
    """Pixel size for an auto area: fine enough for `target_px` along the longer side, never finer than the data, rounded up
    to a round number of metres."""
    want = max(finest_native_m, max(area.xmax - area.xmin, area.ymax - area.ymin) / target_px)
    return float(next((m for m in NICE_M if m >= want * 0.999), np.ceil(want / 1000) * 1000))
