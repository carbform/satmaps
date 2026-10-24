"""Windowed reads of cloud-optimised GeoTIFFs onto what a canvas needs. Needs rasterio: pip install "satviz[rasters]"."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from pyproj import Transformer

from satviz.area import Canvas

MARGIN = 2


def _rasterio():
    try:
        import rasterio
    except ImportError:
        raise ImportError('reading GeoTIFF products needs rasterio: pip install "satviz[rasters]"') from None
    return rasterio


def raster_epsg(src) -> int:
    """EPSG code of an open raster. Some producers (e.g. NRSC) write the UTM zone without an EPSG tag, so fall back to a
    looser match against the registry before giving up."""
    if (epsg := src.crs.to_epsg()) is not None:
        return epsg
    from pyproj import CRS

    if (epsg := CRS.from_wkt(src.crs.to_wkt()).to_epsg(min_confidence=20)) is None:
        raise ValueError(f"{src.name}: cannot tell which EPSG code its coordinate system is")
    return epsg


STRIP_PX = 4_000_000  # input pixels per strip of a decimated read


def _window(src, canvas: Canvas, epsg: int):
    """(c0, c1, r0, r1) of the raster under the canvas (plus a margin), or None when it does not overlap."""
    e = canvas.extent
    xs, ys = np.meshgrid(np.linspace(e[0], e[1], 9), np.linspace(e[2], e[3], 9))
    if epsg != canvas.epsg:
        xs, ys = Transformer.from_crs(f"EPSG:{canvas.epsg}", f"EPSG:{epsg}", always_xy=True).transform(xs, ys)
    t = src.transform
    c0, c1 = sorted(((xs.min() - t.c) / t.a, (xs.max() - t.c) / t.a))
    r0, r1 = sorted(((ys.max() - t.f) / t.e, (ys.min() - t.f) / t.e))
    c0, c1 = max(0, int(np.floor(c0)) - MARGIN), min(src.width, int(np.ceil(c1)) + MARGIN)
    r0, r1 = max(0, int(np.floor(r0)) - MARGIN), min(src.height, int(np.ceil(r1)) + MARGIN)
    return None if c1 - c0 < 1 or r1 - r0 < 1 else (c0, c1, r0, r1)


def _factor(src, canvas: Canvas, epsg: int) -> int:
    """How many raster pixels make one canvas pixel along a side, when the canvas is at least twice as coarse (else 1)."""
    k = int(round(canvas.res / abs(src.transform.a)))
    return k if epsg == canvas.epsg and k >= 2 else 1


def _cached(cache_dir, key: str):
    if cache_dir is None:
        return None, None
    path = Path(cache_dir) / f"cog_{hashlib.sha1(key.encode()).hexdigest()[:20]}.npz"
    if path.exists():
        with np.load(path) as z:
            return path, (None if int(z["empty"]) else (z["arr"], z["x"], z["y"], int(z["epsg"]), z["nodata"].item()))
    return path, False


def _store(path, result) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if result is None:
        np.savez(path, empty=1)
    else:
        arr, x, y, ep, nd = result
        np.savez(path, empty=0, arr=arr, x=x, y=y, epsg=ep, nodata=np.array(np.nan if nd is None else nd))


def read_window(href: str, canvas: Canvas, cache_dir: Path | None = None, band: int = 1, nearest: bool = False):
    """(array, x, y, epsg, nodata) for the part of the raster under the canvas, or None if it does not overlap.

    `x`/`y` are pixel-centre coordinates in the raster's own CRS. Raw values are returned (scaling is the caller's job).
    With `nearest` (masks and classes) a canvas at least twice as coarse as the raster gets every k-th pixel instead of
    the whole window, so a coarse figure never reads what it would throw away."""
    rio = _rasterio()
    from rasterio.enums import Resampling
    from rasterio.windows import Window

    path, hit = _cached(cache_dir, f"{href.split('?')[0]}|{band}|{canvas.epsg}|{canvas.extent}|{canvas.res if nearest else ''}")
    if hit is not False and path is not None:
        return hit
    with rio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF,.tiff",
                 GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="1"):
        with rio.open(href) as src:
            epsg = raster_epsg(src)
            box = _window(src, canvas, epsg)
            if box is None:
                result = None
            else:
                c0, c1, r0, r1 = box
                t = src.transform
                k = _factor(src, canvas, epsg) if nearest else 1
                if k > 1:
                    r1, c1 = r1 - (r1 - r0) % k, c1 - (c1 - c0) % k
                    shape = ((r1 - r0) // k, (c1 - c0) // k)
                    arr = src.read(band, window=Window(c0, r0, c1 - c0, r1 - r0), out_shape=shape, resampling=Resampling.nearest)
                    x = t.c + t.a * (c0 + k * (np.arange(shape[1]) + 0.5))
                    y = t.f + t.e * (r0 + k * (np.arange(shape[0]) + 0.5))
                else:
                    arr = src.read(band, window=Window(c0, r0, c1 - c0, r1 - r0))
                    x = t.c + t.a * (np.arange(c0, c1) + 0.5)
                    y = t.f + t.e * (np.arange(r0, r1) + 0.5)
                result = (arr, x, y, epsg, src.nodata)
    _store(path, result)
    return result


def read_converted(href: str, canvas: Canvas, convert, tag: str, cache_dir: Path | None = None, band: int = 1):
    """(array, x, y, epsg, native pixel size) of `convert(raw window)` (float32, NaN where there is no data) for the part of
    the raster under the canvas, or None if it does not overlap. `tag` names the conversion and its constants, for the cache.

    For a canvas at least twice as coarse as the raster the window is converted and block-averaged a strip of rows at a time (the
    mean of the converted values, which is what resampling to the canvas would do), so memory stays bounded and the averaged array
    is already near the canvas's pixel size."""
    from satviz.grid import _block_mean

    rio = _rasterio()
    from rasterio.windows import Window

    path, hit = _cached(cache_dir, f"{href.split('?')[0]}|{band}|{canvas.epsg}|{canvas.extent}|{canvas.res}|{tag}")
    if hit is not False and path is not None:
        return None if hit is None else (*hit[:4], hit[4])
    with rio.open(href) as src:
        epsg = raster_epsg(src)
        box = _window(src, canvas, epsg)
        if box is None:
            _store(path, None)
            return None
        c0, c1, r0, r1 = box
        t = src.transform
        k, native = _factor(src, canvas, epsg), abs(float(t.a))
        if k == 1:
            arr = np.asarray(convert(src.read(band, window=Window(c0, r0, c1 - c0, r1 - r0))), np.float32)
            x, y = t.c + t.a * (np.arange(c0, c1) + 0.5), t.f + t.e * (np.arange(r0, r1) + 0.5)
        else:
            r1, c1 = r1 - (r1 - r0) % k, c1 - (c1 - c0) % k
            rows_per = max(k, STRIP_PX // max(c1 - c0, 1) // k * k)
            strips = [_block_mean(np.asarray(convert(src.read(band, window=Window(c0, a, c1 - c0, min(a + rows_per, r1) - a))),
                                             np.float32), k) for a in range(r0, r1, rows_per)]
            arr = np.concatenate(strips)
            x = t.c + t.a * (c0 + k * (np.arange(arr.shape[1]) + 0.5))
            y = t.f + t.e * (r0 + k * (np.arange(arr.shape[0]) + 0.5))
    _store(path, (arr, x, y, epsg, native))
    return arr, x, y, epsg, native


def edge_ring(valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(rows, cols) of a ring around the valid pixels of a coarse mask, in pixel-edge units: down the first valid pixel of each
    row that has one, then back up the last. Valid data is taken as one run per row (holes inside a run are inside the ring)."""
    rows = np.flatnonzero(valid.any(axis=1))
    if not len(rows):
        raise ValueError("no valid pixels")
    first = np.array([np.flatnonzero(valid[r])[0] for r in rows], float)
    last = np.array([np.flatnonzero(valid[r])[-1] + 1.0 for r in rows])
    return np.concatenate([rows, rows[::-1]]) + 0.5, np.concatenate([first, last[::-1]])


def valid_ring(href: str, is_valid, across: int = 600, band: int = 1) -> list[tuple[float, float]]:
    """(lon, lat) ring of where a map-projected raster has data: a coarse nearest read about `across` pixels wide, `is_valid`
    (array -> bool array) applied to it, and the ring of the valid pixels (see `edge_ring`) in lon/lat."""
    from rasterio.enums import Resampling

    with _rasterio().open(href) as src:
        step = max(1, src.width // across)
        shape = (max(2, src.height // step), max(2, src.width // step))
        coarse = src.read(band, out_shape=shape, resampling=Resampling.nearest)
        t, epsg = src.transform, raster_epsg(src)
        sy, sx = src.height / shape[0], src.width / shape[1]
    r, c = edge_ring(is_valid(coarse))
    lon, lat = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True).transform(t.c + t.a * c * sx, t.f + t.e * r * sy)
    return list(zip(map(float, lon), map(float, lat), strict=True))
