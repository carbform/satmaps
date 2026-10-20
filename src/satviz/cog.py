"""Windowed reads of cloud-optimised GeoTIFFs onto what a canvas needs. Needs rasterio: pip install "satviz[optical]"."""
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
        raise ImportError('reading GeoTIFFs and STAC data needs rasterio: pip install "satviz[optical]"') from None
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


def read_window(href: str, canvas: Canvas, cache_dir: Path | None = None, band: int = 1):
    """(array, x, y, epsg, nodata) for the part of the raster under the canvas, or None if it does not overlap.

    `x`/`y` are pixel-centre coordinates in the raster's own CRS. Raw values are returned (scaling is the caller's job)."""
    rio = _rasterio()
    from rasterio.windows import Window

    cache = None
    if cache_dir is not None:
        key = hashlib.sha1(f"{href.split('?')[0]}|{band}|{canvas.epsg}|{canvas.extent}".encode()).hexdigest()[:20]
        cache = Path(cache_dir) / f"cog_{key}.npz"
        if cache.exists():
            with np.load(cache) as z:
                return None if int(z["empty"]) else (z["arr"], z["x"], z["y"], int(z["epsg"]), z["nodata"].item())
    with rio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF,.tiff",
                 GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="1"):
        with rio.open(href) as src:
            epsg = raster_epsg(src)
            e = canvas.extent
            xs, ys = np.meshgrid(np.linspace(e[0], e[1], 9), np.linspace(e[2], e[3], 9))
            if epsg != canvas.epsg:
                xs, ys = Transformer.from_crs(f"EPSG:{canvas.epsg}", f"EPSG:{epsg}", always_xy=True).transform(xs, ys)
            t = src.transform
            c0, c1 = sorted(((xs.min() - t.c) / t.a, (xs.max() - t.c) / t.a))
            r0, r1 = sorted(((ys.max() - t.f) / t.e, (ys.min() - t.f) / t.e))
            c0, c1 = max(0, int(np.floor(c0)) - MARGIN), min(src.width, int(np.ceil(c1)) + MARGIN)
            r0, r1 = max(0, int(np.floor(r0)) - MARGIN), min(src.height, int(np.ceil(r1)) + MARGIN)
            if c1 - c0 < 1 or r1 - r0 < 1:
                result = None
            else:
                arr = src.read(band, window=Window(c0, r0, c1 - c0, r1 - r0))
                x = t.c + t.a * (np.arange(c0, c1) + 0.5)
                y = t.f + t.e * (np.arange(r0, r1) + 0.5)
                result = (arr, x, y, epsg, src.nodata)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        if result is None:
            np.savez(cache, empty=1)
        else:
            arr, x, y, ep, nd = result
            np.savez(cache, empty=0, arr=arr, x=x, y=y, epsg=ep, nodata=np.array(np.nan if nd is None else nd))
    return result
