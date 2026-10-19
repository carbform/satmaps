"""The area of interest and the canvas grid every input is read onto.

An `Area` is a rectangle in a projected CRS (UTM by default) plus an optional pixel size. A `Canvas` is the pixel grid
for it. Every sensor reader returns its data already on the canvas, so any two inputs share a grid by construction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer

EDGE_TOL = 1e-3  # a thousandth of a pixel: lat/lon round trips must not add a row or column
MAX_PIXELS = 60_000_000  # refuse canvases beyond this (memory); ask for a coarser resolution instead


class AreaError(ValueError):
    """The [area] section is missing, ambiguous or does not make sense."""


def utm_epsg(lat: float, lon: float) -> int:
    zone = int((lon + 180) // 6) % 60 + 1
    return (32600 if lat >= 0 else 32700) + zone


def _tf(src: int, dst: int) -> Transformer:
    return Transformer.from_crs(f"EPSG:{src}", f"EPSG:{dst}", always_xy=True)


@dataclass(frozen=True)
class Canvas:
    """Pixel grid: `x0`/`y0` are the west and north edges, pixels are `res` metres square, rows run north to south."""

    epsg: int
    x0: float
    y0: float
    res: float
    width: int
    height: int

    @property
    def x(self) -> np.ndarray:  # pixel centres
        return self.x0 + self.res * (np.arange(self.width) + 0.5)

    @property
    def y(self) -> np.ndarray:
        return self.y0 - self.res * (np.arange(self.height) + 0.5)

    @property
    def extent(self) -> list[float]:
        """imshow extent [left, right, bottom, top] in metres."""
        return [self.x0, self.x0 + self.width * self.res, self.y0 - self.height * self.res, self.y0]

    def lonlat_bbox(self) -> tuple[float, float, float, float]:
        """West, south, east, north in WGS84 (outer bounds of the canvas edges)."""
        e = self.extent
        xs = np.linspace(e[0], e[1], 9)
        ys = np.linspace(e[2], e[3], 9)
        X, Y = np.meshgrid(xs, ys)
        lon, lat = _tf(self.epsg, 4326).transform(X.ravel(), Y.ravel())
        return float(np.min(lon)), float(np.min(lat)), float(np.max(lon)), float(np.max(lat))

    def pixel_window(self, bbox_ll: tuple[float, float, float, float]) -> tuple[slice, slice] | None:
        """Rows and columns covered by a WGS84 box, or None when it does not touch the canvas."""
        w, s, e, n = bbox_ll
        lon = np.array([w, e, w, e])
        lat = np.array([s, s, n, n])
        X, Y = _tf(4326, self.epsg).transform(lon, lat)
        c0, c1 = (min(X) - self.x0) / self.res, (max(X) - self.x0) / self.res
        r0, r1 = (self.y0 - max(Y)) / self.res, (self.y0 - min(Y)) / self.res
        c0, c1 = max(0, math.floor(c0)), min(self.width, math.ceil(c1))
        r0, r1 = max(0, math.floor(r0)), min(self.height, math.ceil(r1))
        if c1 <= c0 or r1 <= r0:
            return None
        return slice(r0, r1), slice(c0, c1)


    def window_around(self, lat: float, lon: float, size_km: tuple[float, float]) -> tuple[tuple[int, int], tuple[int, int]]:
        """((row0, row1), (col0, col1)) of a w x h km box centred on a point; raises if it is not inside the canvas."""
        cx, cy = _tf(4326, self.epsg).transform(lon, lat)
        hw, hh = size_km[0] * 500 / self.res, size_km[1] * 500 / self.res
        col, row = (cx - self.x0) / self.res, (self.y0 - cy) / self.res
        c0, c1, r0, r1 = round(col - hw), round(col + hw), round(row - hh), round(row + hh)
        if c0 < 0 or r0 < 0 or c1 > self.width or r1 > self.height or c1 <= c0 or r1 <= r0:
            raise AreaError(f"a {size_km[0]:g} x {size_km[1]:g} km box around lat {lat}, lon {lon} is not inside the area")
        return (r0, r1), (c0, c1)


@dataclass(frozen=True)
class Area:
    """Rectangle in `epsg` metres. Build one with `Area.from_config`."""

    epsg: int
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    resolution_m: float | None = None

    @classmethod
    def from_config(cls, cfg: dict) -> Area:
        """``center = [lat, lon]`` with ``radius_km`` (square of side 2 x radius) or ``size_km = [w, h]``,
        or ``bbox = [west, south, east, north]`` (WGS84). Optional ``resolution_m`` and ``crs = "EPSG:32646"``."""
        known = {"center", "radius_km", "size_km", "bbox", "resolution_m", "crs"}
        if unknown := set(cfg) - known:
            raise AreaError(f"[area]: unknown key(s) {sorted(unknown)}; allowed: {sorted(known)}")
        has_c, has_b = "center" in cfg, "bbox" in cfg
        if has_c == has_b:
            raise AreaError("[area]: give exactly one of `center` (with radius_km or size_km) or `bbox`")
        res = cfg.get("resolution_m")
        if res is not None and not res > 0:
            raise AreaError("[area]: resolution_m must be positive")
        if has_c:
            lat, lon = (float(v) for v in cfg["center"])
            if ("radius_km" in cfg) == ("size_km" in cfg):
                raise AreaError("[area]: with `center` give exactly one of radius_km or size_km")
            w_km, h_km = (2 * float(cfg["radius_km"]),) * 2 if "radius_km" in cfg else (float(v) for v in cfg["size_km"])
            epsg = _epsg(cfg, lat, lon)
            cx, cy = _tf(4326, epsg).transform(lon, lat)
            return cls(epsg, cx - w_km * 500, cy - h_km * 500, cx + w_km * 500, cy + h_km * 500, res)
        w, s, e, n = (float(v) for v in cfg["bbox"])
        if not (w < e and s < n and -180 <= w and e <= 180 and -90 <= s and n <= 90):
            raise AreaError("[area]: bbox must be [west, south, east, north] in degrees with west < east and "
                            f"south < north, got {cfg['bbox']}")
        epsg = _epsg(cfg, (s + n) / 2, (w + e) / 2)
        xs = np.linspace(w, e, 9)
        ys = np.linspace(s, n, 9)
        X, Y = np.meshgrid(xs, ys)
        px, py = _tf(4326, epsg).transform(X.ravel(), Y.ravel())
        return cls(epsg, float(min(px)), float(min(py)), float(max(px)), float(max(py)), res)

    def canvas(self, resolution_m: float | None = None, phase: tuple[float, float] | None = None) -> Canvas:
        """Pixel grid covering the area. `phase` is (x, y) of any pixel centre of a reference grid; the canvas is aligned
        to it so the reference input needs no resampling."""
        res = resolution_m or self.resolution_m
        if not res:
            raise AreaError("no pixel size: set [area] resolution_m, or read an input that has a native resolution")
        if phase:
            px, py = phase[0] - res / 2, phase[1] + res / 2
            x0 = px + math.floor((self.xmin - px) / res + EDGE_TOL) * res
            y0 = py + math.ceil((self.ymax - py) / res - EDGE_TOL) * res
        else:
            x0, y0 = self.xmin, self.ymax
        width = math.ceil((self.xmax - x0) / res - EDGE_TOL)
        height = math.ceil((y0 - self.ymin) / res - EDGE_TOL)
        if width * height > MAX_PIXELS:
            raise AreaError(f"canvas would be {width} x {height} = {width * height / 1e6:.0f} M pixels at {res:g} m; "
                            f"set a coarser [area] resolution_m or a smaller area")
        return Canvas(self.epsg, x0, y0, res, width, height)


def _epsg(cfg: dict, lat: float, lon: float) -> int:
    if "crs" in cfg:
        text = str(cfg["crs"]).upper().removeprefix("EPSG:")
        if not text.isdigit():
            raise AreaError(f"[area] crs must look like 'EPSG:32646', got {cfg['crs']!r}")
        return int(text)
    return utm_epsg(lat, lon)
