"""Any satellite from GeoTIFFs and a band map in the job file: ResourceSat LISS, ALOS PALSAR RTC, PlanetScope, ...

```toml
[[inputs]]
id = "liss"
sensor = "geotiff"
kind = "optical"                           # or "sar"
source = { path = "LISS4_scene.tif" }      # one multi-band file ...
bands = { red = 3, green = 2, blue = 1 }   # ... 1-based band numbers; or a file per band: { red = "B3.tif", ... }
scale = 0.0001                             # optical: reflectance = DN * scale + offset
offset = 0.0
nodata = 0
date = "2026-09-25"                        # required: GeoTIFFs rarely carry a reliable date
time = "05:12"                             # optional, UTC; omitted from the figure when not given
platform = "ResourceSat-2"
label = "LISS-IV"
credit = "ResourceSat-2 LISS-IV data, NRSC/ISRO"   # required: the figure always credits its data
```
SAR (`kind = "sar"`): bands `co` and `cross`, `values = "power" | "amplitude" | "db"` (converted to linear power).
Optical layers are named blue green red nir swir16 swir22, as the optical recipes expect.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from satviz.area import Area, AreaError, Canvas
from satviz.cog import _rasterio, raster_epsg, read_window
from satviz.core import Product, SourceInfo, sensor
from satviz.geo import crs_label
from satviz.grid import to_canvas
from satviz.sources import SourceError, resolve_one_file

KEYS = {"kind", "bands", "scale", "offset", "nodata", "date", "time", "platform", "label", "credit", "attribution", "values",
        "note"}
OPTICAL_BANDS = ("blue", "green", "red", "nir", "swir16", "swir22")
SAR_BANDS = ("co", "cross")


def _options(spec) -> dict:
    o = spec.options
    if unknown := set(o) - KEYS - {"source"}:
        raise SourceError(f"input {spec.key!r}: unknown key(s) {sorted(unknown)}; allowed: {sorted(KEYS | {'source'})}")
    kind = o.get("kind")
    if kind not in ("optical", "sar"):
        raise SourceError(f"input {spec.key!r}: `kind` must be \"optical\" or \"sar\" for sensor geotiff")
    bands = o.get("bands")
    allowed = OPTICAL_BANDS if kind == "optical" else SAR_BANDS
    if not isinstance(bands, dict) or not bands:
        raise SourceError(f"input {spec.key!r}: give a band map, e.g. bands = {{ {allowed[2]} = 3 }}")
    if bad := set(bands) - set(allowed):
        raise SourceError(f"input {spec.key!r}: unknown band name(s) {sorted(bad)} for kind {kind!r}; use {list(allowed)}")
    if kind == "sar" and set(bands) != set(SAR_BANDS):
        raise SourceError(f"input {spec.key!r}: a SAR input needs both `co` and `cross` in bands")
    for req in ("date", "credit"):
        if not o.get(req):
            raise SourceError(f"input {spec.key!r}: `{req}` is required for sensor geotiff")
    return o


def _path_of(spec, band_ref, data_dir) -> tuple[Path, int]:
    """(file, band number) for one entry of the band map: a number in the source file, or a file name."""
    if isinstance(band_ref, int):
        return resolve_one_file(spec, data_dir), band_ref
    sub = type(spec)(spec.key, spec.sensor, "", {"source": {"path": str(band_ref)}})
    return resolve_one_file(sub, data_dir), 1


def describe(spec, data_dir, area: Area | None = None) -> SourceInfo:
    o = _options(spec)
    path, _ = _path_of(spec, next(iter(o["bands"].values())), data_dir)
    rio = _rasterio()
    with rio.open(path) as src:
        t = src.transform
        res = abs(t.a)
        return SourceInfo(epsg=raster_epsg(src), resolution_m=res, phase=(t.c + res / 2, t.f - res / 2), files=[str(path)])


def open_on_canvas(spec, canvas: Canvas, area: Area, data_dir, cache_dir=None, tag="job") -> Product:
    o = _options(spec)
    kind = o["kind"]
    scale, offset, nodata = float(o.get("scale", 1.0)), float(o.get("offset", 0.0)), o.get("nodata")
    values = o.get("values", "power")
    if values not in ("power", "amplitude", "db"):
        raise SourceError(f"input {spec.key!r}: values must be power, amplitude or db")
    layers, files, native = {}, [], None
    for name, ref in o["bands"].items():
        path, idx = _path_of(spec, ref, data_dir)
        files.append(str(path))
        r = read_window(str(path), canvas, cache_dir, band=idx)
        if r is None:
            raise AreaError(f"input {spec.key!r}: {path.name} does not cover the area")
        arr, x, y, epsg, file_nodata = r
        a = arr.astype(np.float32)
        nd = nodata if nodata is not None else file_nodata
        if nd is not None and not (isinstance(nd, float) and np.isnan(nd)):
            a[arr == nd] = np.nan
        a = a * scale + offset if kind == "optical" else _to_power(a, values)
        native = abs(float(x[1] - x[0])) if len(x) > 1 else canvas.res
        layers[name] = to_canvas(a, x, y, epsg, canvas, "bilinear")
    ref_layer = layers.get("red", layers.get("co", next(iter(layers.values()))))
    valid = np.isfinite(ref_layer) if kind == "optical" else np.isfinite(ref_layer) & (ref_layer > 0)
    when = _when(spec, o)
    platform, label = str(o.get("platform", "")), str(o.get("label", ""))
    caveats = [str(o["note"])] if o.get("note") else []
    caveats.append(f"Reflectance = value x {scale:g} + {offset:g}, as set in the job file; no cloud screening."
                   if kind == "optical" else f"Values read as {values}; no noise screening, no speckle filter.")
    if native > canvas.res * 1.5:
        caveats.append(f"{platform or 'Input'}: {native:g} m pixels are resampled to this figure's {canvas.res:g} m grid.")
    credit = str(o["credit"])
    return Product(
        key=spec.key, layers=layers, x=canvas.x, y=canvas.y, epsg=canvas.epsg, valid=valid, kind=kind,
        meta=dict(platform=platform, sensor=label, label=label, start=when, end=when, resolution_m=canvas.res,
                  crs=crs_label(canvas.epsg), attribution=str(o.get("attribution", credit)), credit=credit, items=files,
                  time_known=bool(o.get("time"))),
        facts=SimpleNamespace(date=f"{when.day} {when:%b %Y}", files=", ".join(Path(f).name for f in files)),
        caveats=caveats,
    )


def _to_power(a: np.ndarray, values: str) -> np.ndarray:
    if values == "amplitude":
        return a * a
    if values == "db":
        return np.power(10.0, a / 10.0)
    return a


def _when(spec, o: dict) -> datetime:
    try:
        return datetime.fromisoformat(f"{o['date']}T{o.get('time', '00:00')}")
    except ValueError:
        raise SourceError(f"input {spec.key!r}: date must look like 2026-09-25 and time like 05:12") from None


sensor("geotiff")(SimpleNamespace(describe=describe, open=open_on_canvas, kind="any"))
