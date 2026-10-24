"""Sentinel-2 Level-2A from a local, unzipped `.SAFE` folder: every spectral band as surface reflectance.

```toml
[[inputs]]
id = "S2"
sensor = "sentinel2"
source = { path = "S2C_MSIL2A_20260929T041551_N0513_R090_T46RFR_20260929T075413.SAFE" }
```
Each band is read from its own native resolution (10 m: B2, B3, B4, B8; 20 m: B5, B6, B7, B8A, B11, B12; 60 m: B1, B9). The 20 m
and 60 m folders also hold downsampled copies of the finer bands; those are not used.

Reflectance is (DN + BOA_ADD_OFFSET) / BOA_QUANTIFICATION_VALUE (Sentinel-2 Products Specification, processing baseline 04.00 and
later). Each band's offset is looked up by its `band_id` in `MTD_MSIL2A.xml`, because the metadata lists B10 and L2A has no image
for it, so pairing offsets with the files found on disk would shift B11 and B12. DN 0 is no data and 65535 is saturation; both
are dropped before the offset can turn them into numbers.

Layers: the band ids (`B01` ... `B8A` ... `B12`), the colour roles the recipes use (`blue green red nir swir16 swir22`, the same
arrays) and `cloud` from the scene classification, as the catalogue reader does. Centre wavelengths and widths are read from the
metadata of the satellite that took the scene.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from satviz.area import Area, AreaError, Canvas
from satviz.cog import _rasterio, raster_epsg, read_window
from satviz.core import BandInfo, Product, SourceInfo, sensor
from satviz.geo import crs_label
from satviz.grid import to_canvas
from satviz.sensors import nrsc
from satviz.sources import SourceError, resolve_one_file

KEYS = {"label", "credit", "attribution", "note"}
SATURATED = 65535
SCL_CLOUD = (3, 8, 9, 10)  # cloud shadow, medium and high probability cloud, thin cirrus (the catalogue reader uses the same)
ROLES = {"blue": "B02", "green": "B03", "red": "B04", "nir": "B08", "swir16": "B11", "swir22": "B12"}
# Common band names from the Sentinel-2 Products Specification Document (docs/references).
COMMON_NAMES = {
    "B01": "coastal aerosol", "B02": "blue", "B03": "green", "B04": "red", "B05": "red edge 1", "B06": "red edge 2",
    "B07": "red edge 3", "B08": "nir", "B8A": "nir narrow", "B09": "water vapour", "B11": "swir 1", "B12": "swir 2",
}


def band_code(physical: str) -> str:
    """'B1' -> 'B01', 'B8A' -> 'B8A', 'B11' -> 'B11': the spelling used in the image file names."""
    return f"B{int(physical[1:]):02d}" if physical[1:].isdigit() else physical


def _text(root, tag: str, default: str | None = None) -> str | None:
    for e in root.iter():
        if e.tag.split("}")[-1] == tag:
            return (e.text or "").strip()
    return default


def read_mtd(folder: Path) -> dict:
    """Band resolution and wavelengths by band, BOA offsets by band_id, the quantification value, spacecraft and start time."""
    path = folder / "MTD_MSIL2A.xml"
    if not path.is_file():
        raise SourceError(f"{folder}: no MTD_MSIL2A.xml; point `source.path` at the unzipped Level-2A .SAFE folder")
    root = ET.parse(path).getroot()
    offsets = {int(e.get("band_id")): float(e.text) for e in root.iter() if e.tag.split("}")[-1] == "BOA_ADD_OFFSET"}
    bands = {}
    for e in root.iter():
        if e.tag.split("}")[-1] != "Spectral_Information":
            continue
        bid = int(e.get("bandId"))
        bands[band_code(e.get("physicalBand"))] = dict(
            band_id=bid, resolution=int(_text(e, "RESOLUTION")), min=float(_text(e, "MIN")), max=float(_text(e, "MAX")),
            central=float(_text(e, "CENTRAL")), offset=offsets.get(bid))
    if not bands or not offsets:
        raise SourceError(f"{path.name}: no spectral information or BOA offsets "
                          "(is it a Level-2A product from processing baseline 04.00 or later?)")
    return dict(bands=bands, quantification=float(_text(root, "BOA_QUANTIFICATION_VALUE")),
                spacecraft=_text(root, "SPACECRAFT_NAME") or "Sentinel-2", baseline=_text(root, "PROCESSING_BASELINE", ""),
                start=datetime.fromisoformat(_text(root, "PRODUCT_START_TIME").rstrip("Z")))


def _granule(folder: Path) -> Path:
    grans = sorted((folder / "GRANULE").glob("L2A_*"))
    if len(grans) != 1:
        raise SourceError(f"{folder.name}: expected one granule under GRANULE/, found {len(grans)}")
    return grans[0] / "IMG_DATA"


def band_file(img_data: Path, code: str, resolution: int) -> Path | None:
    """The band's file in its own native-resolution folder, or None (L2A has no B10 image, for one)."""
    hits = sorted((img_data / f"R{resolution}m").glob(f"*_{code}_{resolution}m.jp2"))
    return hits[0] if hits else None


def to_reflectance(dn: np.ndarray, offset: float, quantification: float) -> np.ndarray:
    """(DN + offset) / quantification. No data (DN 0) and saturated (65535) pixels are NaN, never offset numbers."""
    refl = (dn.astype(np.float32) + np.float32(offset)) / np.float32(quantification)
    refl[(dn == 0) | (dn == SATURATED)] = np.nan
    return refl


def _folder(spec, data_dir) -> Path:
    return nrsc.product_folder(resolve_one_file(spec, data_dir))


def _check(spec) -> None:
    if unknown := set(spec.options) - KEYS - {"source"}:
        raise SourceError(f"input {spec.key!r}: unknown key(s) {sorted(unknown)}; allowed: {sorted(KEYS | {'source'})}")


def describe(spec, data_dir, area: Area | None = None) -> SourceInfo:
    _check(spec)
    folder = _folder(spec, data_dir)
    mtd = read_mtd(folder)
    path = band_file(_granule(folder), "B04", mtd["bands"]["B04"]["resolution"])
    if path is None:
        raise SourceError(f"{folder.name}: no B04 image")
    with _rasterio().open(path) as src:
        t = src.transform
        res = abs(t.a)
        return SourceInfo(epsg=raster_epsg(src), resolution_m=res, phase=(t.c + res / 2, t.f - res / 2), files=[str(path)])


def _cloud_layer(img: Path, canvas: Canvas, cache_dir) -> np.ndarray | None:
    path = next(iter(sorted((img / "R20m").glob("*_SCL_20m.jp2"))), None)
    r = read_window(str(path), canvas, cache_dir) if path is not None else None
    if r is None:
        return None
    scl = to_canvas(r[0], r[1], r[2], r[3], canvas, "nearest", fill=0)
    return np.isin(scl, SCL_CLOUD).astype(np.float32)


def open_on_canvas(spec, canvas: Canvas, area: Area, data_dir, cache_dir=None, tag="job") -> Product:
    _check(spec)
    folder = _folder(spec, data_dir)
    mtd = read_mtd(folder)
    img = _granule(folder)
    layers, infos, files, coarse = {}, [], [], []
    for code, b in sorted(mtd["bands"].items(), key=lambda kv: kv[1]["central"]):
        path = band_file(img, code, b["resolution"])
        if path is None:
            continue  # a band the metadata lists but the product does not carry (B10)
        if b["offset"] is None:
            raise SourceError(f"{folder.name}: no BOA_ADD_OFFSET for band {code} (band_id {b['band_id']})")
        r = read_window(str(path), canvas, cache_dir)
        if r is None:
            raise AreaError(f"input {spec.key!r}: {path.name} does not cover the area")
        dn, x, y, epsg, _ = r
        layers[code] = to_canvas(to_reflectance(dn, b["offset"], mtd["quantification"]), x, y, epsg, canvas, "bilinear")
        files.append(str(path))
        infos.append(BandInfo(id=code, layer=code, name=COMMON_NAMES.get(code, ""), wavelength_nm=b["central"],
                              range_nm=(b["min"], b["max"]), resolution_m=float(b["resolution"])))
        if b["resolution"] > canvas.res * 1.5:
            coarse.append(f"{code} ({b['resolution']} m)")
    for role, code in ROLES.items():
        if code in layers:
            layers[role] = layers[code]  # the same array under the name the recipes use
    if "B04" not in layers:
        raise SourceError(f"{folder.name}: no B04 image, cannot build a validity mask")
    valid = np.isfinite(layers["B04"])
    cloud = _cloud_layer(img, canvas, cache_dir)
    cloud_pct = float("nan")
    if cloud is not None:
        layers["cloud"] = cloud
        cloud_pct = 100 * float(cloud[valid].mean()) if valid.any() else float("nan")
    when = mtd["start"]
    caveats = [str(spec.options["note"])] if spec.options.get("note") else []
    cloud_text = (f"{cloud_pct:.0f}% cloud, shadow or cirrus in view; clouds are shown, not masked."
                  if np.isfinite(cloud_pct) else "clouds are shown, not masked.")
    caveats.append(f"{mtd['spacecraft']}, {when:%d %b %Y}: {cloud_text}")
    if coarse:
        caveats.append(f"{', '.join(coarse)} are resampled to this figure's {canvas.res:g} m grid.")
    credit = str(spec.options.get("credit", f"Contains modified Copernicus Sentinel data {when.year}"))
    return Product(
        key=spec.key, layers=layers, x=canvas.x, y=canvas.y, epsg=canvas.epsg, valid=valid, kind="optical",
        meta=dict(platform=mtd["spacecraft"], sensor="MSI", label=str(spec.options.get("label", "L2A")), reflectance="surface",
                  start=when, end=when, resolution_m=canvas.res, crs=crs_label(canvas.epsg),
                  attribution=str(spec.options.get("attribution", "Copernicus Sentinel")), credit=credit, items=files,
                  time_known=True),
        facts=SimpleNamespace(date=f"{when.day} {when:%b %Y}", files=folder.name, cloud_pct=cloud_pct,
                              coverage_pct=100 * float(valid.mean()), items=folder.name, baseline=mtd["baseline"]),
        caveats=caveats, bands=tuple(infos),
    )


sensor("sentinel2")(SimpleNamespace(describe=describe, open=open_on_canvas, kind="optical"))
