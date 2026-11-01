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

from satmaps.area import Area, AreaError, _tf, utm_epsg

GRID = 400  # cells along the longer side of the overlap's bounding box
ERODE = 2  # cells shaved off the overlap so the canvas edge stays inside the data
MIN_SIDE_KM = 1.0
NO_OVERLAP_FIX = "A figure shows products that cover the same ground: choose products that overlap."
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


def common_area(footprints: dict[str, list[tuple[float, float]]], labels: dict[str, str] | None = None) -> Area:
    """The largest rectangle inside every footprint (a dict input id -> (lon, lat) ring); `labels` name the inputs in errors."""
    rings = {k: np.asarray(v, float) for k, v in footprints.items()}
    w = max(r[:, 0].min() for r in rings.values())
    e = min(r[:, 0].max() for r in rings.values())
    s = max(r[:, 1].min() for r in rings.values())
    n = min(r[:, 1].max() for r in rings.values())
    names = " and ".join((labels or {}).get(k, k) for k in rings)
    if not (w < e and s < n):
        raise AreaError(f"{names} do not overlap: their footprints share no area. {NO_OVERLAP_FIX}")
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
        raise AreaError(f"{names} do not overlap: their footprints share no area. {NO_OVERLAP_FIX}")
    r0, r1, c0, c1 = box
    if min(r1 - r0, c1 - c0) * step < MIN_SIDE_KM * 1000:
        raise AreaError(f"{names} overlap in a sliver under {MIN_SIDE_KM:g} km: nothing to draw. "
                        + NO_OVERLAP_FIX)
    return Area(epsg, x0 + c0 * step, y1 - r1 * step, x0 + c1 * step, y1 - r0 * step)


def group_by_ground(rings: list) -> list[list[int]]:
    """Indices of footprint rings (None: unknown) grouped by shared ground: each group has a common area, no two groups share
    one. A product with no footprint joins the first group, since nothing can be said against it."""
    groups: list[list[int]] = []
    for i in range(len(rings)):
        for g in groups:
            known = {str(j): rings[j] for j in (*g, i) if rings[j]}
            try:
                if len(known) >= 2:
                    common_area(known)
            except AreaError:
                continue
            g.append(i)
            break
        else:
            groups.append([i])
    return groups


def coverage(ring: list[tuple[float, float]], box: tuple[float, float, float, float], n: int = 40) -> float:
    """The share (0..1) of a (west, south, east, north) box that lies inside a footprint ring, sampled on an n x n grid."""
    w, s, e, nn = box
    if not (w < e and s < nn):
        return 0.0
    lon, lat = np.meshgrid(np.linspace(w, e, n), np.linspace(s, nn, n))
    inside = Ring(np.asarray(ring, float)).contains_points(np.column_stack([lon.ravel(), lat.ravel()]))
    return float(inside.mean())


def touches(ring: list[tuple[float, float]], box: tuple[float, float, float, float]) -> bool:
    """Whether a (west, south, east, north) box and a footprint ring share any ground at all."""
    from matplotlib.transforms import Bbox

    w, s, e, n = box
    return bool(w < e and s < n and Ring(np.asarray(ring, float)).intersects_bbox(Bbox.from_extents(w, s, e, n), filled=True))


def overlap_share(ring1: list[tuple[float, float]] | None, ring2: list[tuple[float, float]] | None, n: int = 20) -> float:
    """Estimated overlap share (0.0 to 1.0) of two footprint rings (lon, lat), relative to the smaller product."""
    if not ring1 or not ring2:
        return 0.0
    r1 = np.asarray(ring1, float)
    r2 = np.asarray(ring2, float)
    w1, e1 = r1[:, 0].min(), r1[:, 0].max()
    s1, n1 = r1[:, 1].min(), r1[:, 1].max()
    w2, e2 = r2[:, 0].min(), r2[:, 0].max()
    s2, n2 = r2[:, 1].min(), r2[:, 1].max()

    w, e = max(w1, w2), min(e1, e2)
    s, nn = max(s1, s2), min(n1, n2)
    if not (w < e and s < nn):
        return 0.0

    lon, lat = np.meshgrid(np.linspace(w, e, n), np.linspace(s, nn, n))
    pts = np.column_stack([lon.ravel(), lat.ravel()])
    both = Ring(r1).contains_points(pts) & Ring(r2).contains_points(pts)
    inter_area = (e - w) * (nn - s) * both.mean()
    if inter_area <= 0:
        return 0.0

    lon1, lat1 = np.meshgrid(np.linspace(w1, e1, n), np.linspace(s1, n1, n))
    area1 = (e1 - w1) * (n1 - s1) * Ring(r1).contains_points(np.column_stack([lon1.ravel(), lat1.ravel()])).mean()
    lon2, lat2 = np.meshgrid(np.linspace(w2, e2, n), np.linspace(s2, n2, n))
    area2 = (e2 - w2) * (n2 - s2) * Ring(r2).contains_points(np.column_stack([lon2.ravel(), lat2.ravel()])).mean()

    denom = min(area1, area2)
    return float(np.clip(inter_area / max(denom, 1e-9), 0.0, 1.0))


def pick_resolution(area: Area, finest_native_m: float, target_px: int) -> float:
    """Pixel size for an auto area: fine enough for `target_px` along the longer side, never finer than the data, rounded up
    to a round number of metres."""
    want = max(finest_native_m, max(area.xmax - area.xmin, area.ymax - area.ymin) / target_px)
    return float(next((m for m in NICE_M if m >= want * 0.999), np.ceil(want / 1000) * 1000))
