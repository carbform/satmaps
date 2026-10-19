"""Plot-space helpers: figures are drawn in the product's projected grid (no resampling to lat/lon)."""
from __future__ import annotations


def utm_extent(d: dict) -> list[float]:
    """imshow extent [left, right, bottom, top] in metres, from pixel-centre coordinates."""
    dx = abs(d["x"][1] - d["x"][0]) / 2
    dy = abs(d["y"][1] - d["y"][0]) / 2
    return [d["x"][0] - dx, d["x"][-1] + dx, d["y"][-1] - dy, d["y"][0] + dy]


def to_xy(d: dict, lat: float, lon: float) -> tuple[float, float]:
    """Project a WGS84 point into the dataset's grid."""
    return d["to_utm"].transform(lon, lat)


def project(epsg: int, lat: float, lon: float) -> tuple[float, float]:
    """WGS84 point to the given projected CRS (works for any product, not just NISAR's working dataset)."""
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(lon, lat)
