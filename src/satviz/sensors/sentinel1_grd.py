"""Sentinel-1 IW GRD (ground-range detected) from a local, unzipped SAFE folder: sigma-nought VV/VH or HH/HV.

```toml
[[inputs]]
id = "S1"
sensor = "sentinel1_grd"
source = { path = "S1D_IW_GRDH_1SDV_..._F331.SAFE" }   # the unzipped product folder
```
Unlike the `sentinel1_rtc` catalogue sensor, a GRD file is not map-projected: the measurement GeoTIFF carries ground control
points and an identity transform. This reader therefore works in image space: it finds the canvas in (line, pixel) with a
thin-plate-spline fit to the GCPs, reads that window, calibrates it, and samples it onto the canvas.

Calibration, as in ESA's Sentinel-1 product specification: sigma0 = (DN^2 - N) / A^2, with A from the `sigmaNought` look-up table
of the calibration annotation, and N = noiseRange(line, pixel) x noiseAzimuth(line) from the noise annotation. The LUTs already
carry the absolute calibration constant. Values at or below zero after noise subtraction are dropped. GRD is geolocated on the
ellipsoid with the GCP heights, not terrain-flattened, so slopes facing the radar are bright and the far sides dark.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from pyproj import Transformer
from scipy.ndimage import map_coordinates, uniform_filter

from satviz.area import Area, AreaError, Canvas
from satviz.cog import _rasterio
from satviz.core import Product, SourceInfo, sensor
from satviz.geo import crs_label
from satviz.sensors import nrsc
from satviz.sources import SourceError, resolve_one_file

CREDIT = "Contains modified Copernicus Sentinel data {year}"
KEYS = {"label", "credit", "attribution", "note"}
MARGIN = 8  # pixels kept around the window, for resampling
LATTICE = 16  # the GCP fit is evaluated on every LATTICE-th canvas pixel and interpolated between


def _check(spec) -> None:
    if unknown := set(spec.options) - KEYS - {"source"}:
        raise SourceError(f"input {spec.key!r}: unknown key(s) {sorted(unknown)}; allowed: {sorted(KEYS | {'source'})}")


def _floats(node, tag: str) -> np.ndarray:
    return np.array(node.findtext(tag).split(), dtype=np.float64)


def read_luts(path: Path, vector_tag: str, value_tag: str):
    """[(line, pixels, values)] from a calibration or range-noise annotation: one entry per vector in the file."""
    out = []
    for v in ET.parse(path).getroot().iter(vector_tag):
        out.append((float(v.findtext("line")), _floats(v, "pixel"), _floats(v, value_tag)))
    if not out:
        raise SourceError(f"{path.name}: no <{vector_tag}> found")
    return sorted(out, key=lambda t: t[0])


def read_azimuth_noise(path: Path) -> list[dict]:
    out = []
    for v in ET.parse(path).getroot().iter("noiseAzimuthVector"):
        out.append(dict(first_line=int(v.findtext("firstAzimuthLine")), last_line=int(v.findtext("lastAzimuthLine")),
                        first_sample=int(v.findtext("firstRangeSample")), last_sample=int(v.findtext("lastRangeSample")),
                        lines=_floats(v, "line"), lut=_floats(v, "noiseAzimuthLut")))
    return out


def lut_on_grid(vectors, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """A set of range-sampled vectors, each at one line, interpolated linearly to every (row, col) of the window."""
    at_cols = np.stack([np.interp(cols, px, val) for _, px, val in vectors])
    lines = np.array([v[0] for v in vectors])
    if len(lines) == 1:
        return np.repeat(at_cols, len(rows), axis=0)
    i = np.clip(np.searchsorted(lines, rows, side="right") - 1, 0, len(lines) - 2)
    t = np.clip((rows - lines[i]) / (lines[i + 1] - lines[i]), 0.0, 1.0)[:, None]
    return at_cols[i] * (1 - t) + at_cols[i + 1] * t


def azimuth_noise_on_grid(blocks: list[dict], rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Per-swath noise factor along azimuth, as a (row, col) array; 1 where no block covers a pixel."""
    out = np.ones((len(rows), len(cols)), np.float64)
    for b in blocks:
        r_in = (rows >= b["first_line"]) & (rows <= b["last_line"])
        c_in = (cols >= b["first_sample"]) & (cols <= b["last_sample"])
        if r_in.any() and c_in.any():
            out[np.ix_(r_in, c_in)] = np.interp(rows[r_in], b["lines"], b["lut"])[:, None]
    return out


def sigma0(dn: np.ndarray, row0: int, col0: int, cal, noise_range, noise_az) -> tuple[np.ndarray, float]:
    """Linear sigma-nought of the DN window whose corner is (row0, col0), and the share of pixels dropped.

    Pixels with DN 0 (outside the swath) and those at or below the noise after subtraction become NaN."""
    rows = np.arange(row0, row0 + dn.shape[0], dtype=np.float64)
    cols = np.arange(col0, col0 + dn.shape[1], dtype=np.float64)
    a = lut_on_grid(cal, rows, cols)
    n = lut_on_grid(noise_range, rows, cols) * azimuth_noise_on_grid(noise_az, rows, cols)
    power = dn.astype(np.float64) ** 2 - n
    s0 = power / a**2
    inside = dn > 0
    below = inside & (power <= 0)
    s0[~inside | below] = np.nan
    return s0.astype(np.float32), float(below.sum() / max(inside.sum(), 1))


def canvas_to_image(gcps, canvas: Canvas) -> tuple[np.ndarray, np.ndarray]:
    """(row, col) in the measurement image of every canvas pixel centre, from a thin-plate-spline fit to the GCPs."""
    from rasterio.transform import GCPTransformer

    gx, gy = np.meshgrid(canvas.x, canvas.y)
    ri = np.unique(np.append(np.arange(0, gx.shape[0], LATTICE), gx.shape[0] - 1))
    ci = np.unique(np.append(np.arange(0, gx.shape[1], LATTICE), gx.shape[1] - 1))
    sx, sy = gx[np.ix_(ri, ci)], gy[np.ix_(ri, ci)]
    lon, lat = Transformer.from_crs(f"EPSG:{canvas.epsg}", "EPSG:4326", always_xy=True).transform(sx, sy)
    rr, cc = GCPTransformer(gcps, tps=True).rowcol(lon.ravel(), lat.ravel(), op=lambda v: v)
    rr, cc = np.reshape(rr, sx.shape), np.reshape(cc, sx.shape)

    def full(a):  # bilinear from the lattice to every canvas pixel
        fr = np.interp(np.arange(gx.shape[0]), ri, np.arange(len(ri)))
        fc = np.interp(np.arange(gx.shape[1]), ci, np.arange(len(ci)))
        return map_coordinates(a, np.meshgrid(fr, fc, indexing="ij"), order=1)

    return full(rr), full(cc)


def _files(folder: Path) -> dict[str, dict[str, Path]]:
    """{polarisation: {measurement, calibration, noise}} for the polarisations in the SAFE folder."""
    out = {}
    for tif in sorted((folder / "measurement").glob("*.tiff")):
        pol = tif.name.split("-")[3].upper()
        stem = tif.stem
        cal = sorted((folder / "annotation" / "calibration").glob(f"calibration-{stem}.xml"))
        noise = sorted((folder / "annotation" / "calibration").glob(f"noise-{stem}.xml"))
        if not cal or not noise:
            raise SourceError(f"{folder.name}: calibration or noise annotation for {pol} is missing")
        out[pol] = dict(measurement=tif, calibration=cal[0], noise=noise[0],
                        annotation=folder / "annotation" / f"{stem}.xml")
    if not out:
        raise SourceError(f"{folder}: no measurement/*.tiff; point `source.path` at the unzipped .SAFE folder")
    return out


def _pols(files: dict) -> tuple[str, str]:
    for co, cross in (("VV", "VH"), ("HH", "HV")):
        if co in files and cross in files:
            return co, cross
    raise SourceError(f"need VV+VH or HH+HV, found {sorted(files)}")


def _annotation(path: Path) -> dict:
    root = ET.parse(path).getroot()
    return dict(start=datetime.fromisoformat(root.findtext(".//productFirstLineUtcTime")),
                stop=datetime.fromisoformat(root.findtext(".//productLastLineUtcTime")),
                orbit=root.findtext(".//pass", "").lower(), mission=root.findtext(".//missionId", "S1"),
                res=float(root.findtext(".//rangePixelSpacing")), rel_orbit=root.findtext(".//relativeOrbitNumber", ""))


def _folder(spec, data_dir) -> Path:
    return nrsc.product_folder(resolve_one_file(spec, data_dir))


def describe(spec, data_dir, area: Area | None = None) -> SourceInfo:
    _check(spec)
    files = _files(_folder(spec, data_dir))
    co = files[_pols(files)[0]]
    return SourceInfo(epsg=4326, resolution_m=_annotation(co["annotation"])["res"], phase=None, files=[str(co["measurement"])])


def open_on_canvas(spec, canvas: Canvas, area: Area, data_dir, cache_dir=None, tag="job") -> Product:
    _check(spec)
    folder = _folder(spec, data_dir)
    files = _files(folder)
    pols = _pols(files)
    info = _annotation(files[pols[0]]["annotation"])
    rio = _rasterio()
    layers, dropped, used = {}, [], []
    img_rows = img_cols = None
    for name, pol in zip(("co", "cross"), pols, strict=True):
        f = files[pol]
        used.append(str(f["measurement"]))
        with rio.open(f["measurement"]) as src:
            if img_rows is None:
                img_rows, img_cols = canvas_to_image(src.gcps[0], canvas)
            r0, r1 = int(np.floor(img_rows.min())) - MARGIN, int(np.ceil(img_rows.max())) + MARGIN
            c0, c1 = int(np.floor(img_cols.min())) - MARGIN, int(np.ceil(img_cols.max())) + MARGIN
            r0, r1, c0, c1 = max(r0, 0), min(r1, src.height - 1), max(c0, 0), min(c1, src.width - 1)
            if r1 <= r0 or c1 <= c0:
                raise AreaError(f"input {spec.key!r}: {folder.name} does not cover the area")
            from rasterio.windows import Window

            dn = src.read(1, window=Window(c0, r0, c1 - c0 + 1, r1 - r0 + 1))
        s0, share = sigma0(dn, r0, c0, read_luts(f["calibration"], "calibrationVector", "sigmaNought"),
                           read_luts(f["noise"], "noiseRangeVector", "noiseRangeLut"), read_azimuth_noise(f["noise"]))
        coarse = max(1, int(round(canvas.res / info["res"])))
        if coarse >= 2:  # box-average first, so a coarser canvas does not alias speckle
            ok = np.isfinite(s0)
            num = uniform_filter(np.where(ok, s0, 0.0), coarse)
            den = uniform_filter(ok.astype(np.float32), coarse)
            s0 = np.where(den > 0.5, num / np.maximum(den, 1e-6), np.nan).astype(np.float32)
        sample = np.where(np.isfinite(s0), s0, np.nan)
        # NaN-aware bilinear: weight the values by validity so one bad neighbour does not blank a pixel
        coords = [img_rows - r0, img_cols - c0]
        val = map_coordinates(np.nan_to_num(sample), coords, order=1, mode="constant", cval=0.0)
        wgt = map_coordinates(np.isfinite(sample).astype(np.float32), coords, order=1, mode="constant", cval=0.0)
        layer = np.where(wgt > 0.99, val / np.maximum(wgt, 1e-6), np.nan).astype(np.float32)
        layers[name] = layer
        dropped.append((pol, 100 * share))
    valid = np.isfinite(layers["co"])
    if not valid.any():
        raise AreaError(f"input {spec.key!r}: {folder.name} has no usable data in the area")
    when = info["start"] + (info["stop"] - info["start"]) / 2
    gap = ", ".join(f"{p} {pct:.0f}%" for p, pct in dropped)
    caveats = [str(spec.options["note"])] if spec.options.get("note") else []
    caveats.append("Sentinel-1 GRD: sigma0 with thermal noise subtracted; pixels at or below the noise level are dropped "
                   f"({gap}); geolocated on the ellipsoid, not terrain-flattened; no speckle filter.")
    if info["res"] > canvas.res * 1.5:
        caveats.append(f"Sentinel-1: {info['res']:g} m pixels resampled to this figure's {canvas.res:g} m grid.")
    credit = str(spec.options.get("credit", CREDIT.format(year=when.year)))
    platform = "Sentinel-1" + info["mission"][-1].upper() if info["mission"].upper().startswith("S1") else "Sentinel-1"
    return Product(
        key=spec.key, layers=layers, x=canvas.x, y=canvas.y, epsg=canvas.epsg, valid=valid, kind="sar",
        meta=dict(platform=platform, sensor="IW GRD", label=str(spec.options.get("label", "IW GRD")), start=when, end=when,
                  resolution_m=canvas.res, crs=crs_label(canvas.epsg),
                  attribution=str(spec.options.get("attribution", "Copernicus Sentinel")), credit=credit, items=used),
        facts=SimpleNamespace(date=f"{when.day} {when:%b %Y}", files=folder.name, polarisations="/".join(pols),
                              orbit=info["orbit"], relative_orbit=info["rel_orbit"]),
        caveats=caveats,
    )


sensor("sentinel1_grd")(SimpleNamespace(describe=describe, open=open_on_canvas, kind="sar"))
