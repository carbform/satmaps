"""EOS-04 (RISAT-1A) SAR, NRSC/ISRO: Level-2B terrain-normalised gamma-nought ARD product folders (ScanSAR MRS).

```toml
[[inputs]]
id = "E"
sensor = "eos04"
source = { path = "E04_SAR_MRS_11OCT2026_...E080824" }   # the unzipped product folder
```
The GeoTIFFs hold DN, a representation of gamma-nought (EOS-04 Data Products Format Document, section 6.3):
gamma0_dB = 20 log10(DN) - Kcal_dB, and in linear units gamma0 = DN^2 / Kcal_linear, with the image noise bias N
subtracted from DN^2 first (section 3.0). Layers are `co` and `cross` (linear power) for the two polarisations in the
product (HH/HV here). Only pixels flagged 128 in the mask file (valid, not layover, not shadow, inside the image) are used.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from satviz.area import Area, AreaError, Canvas
from satviz.cog import _rasterio, raster_epsg, read_window
from satviz.core import Product, SourceInfo, sensor
from satviz.geo import crs_label
from satviz.grid import to_canvas
from satviz.radar import radar_facts
from satviz.sensors import nrsc
from satviz.sources import SourceError, resolve_one_file

CREDIT = "EOS-04 SAR data, NRSC/ISRO"
VALID = 128  # mask value for undistorted valid image data (16 layover, 64 shadow, 0 outside)
KEYS = {"label", "credit", "attribution", "note"}


def _folder(spec, data_dir) -> Path:
    return nrsc.product_folder(resolve_one_file(spec, data_dir))


def _check(spec) -> None:
    if unknown := set(spec.options) - KEYS - {"source"}:
        raise SourceError(f"input {spec.key!r}: unknown key(s) {sorted(unknown)}; allowed: {sorted(KEYS | {'source'})}")


def _pols(meta: dict) -> list[str]:
    pols = [meta[k] for k in ("TxRxPol1", "TxRxPol2") if meta.get(k)]
    if len(pols) != 2:
        raise SourceError(f"EOS-04 product has polarisations {pols}; this reader needs a dual-polarisation product (co + cross)")
    return pols


def _imagery(folder: Path, pol: str) -> Path:
    path = folder / f"scene_{pol}" / f"imagery_{pol}.tif"
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found; is {folder.name} a Level-2B product folder?")
    return path


def _mask(folder: Path) -> Path:
    hits = sorted(folder.glob("*_mask.tif"))
    if not hits:
        raise FileNotFoundError(f"{folder}: no *_mask.tif; the layover/shadow mask is required to use the data")
    return hits[0]


def _radar(folder: Path) -> dict:
    """Band and centre frequency from product.xml (`RadarBand`, `RadarCenterFrequency` in Hz)."""
    import xml.etree.ElementTree as ET

    root = ET.parse(folder / "product.xml").getroot()
    hz = root.findtext(".//RadarCenterFrequency")
    if hz is None:
        raise SourceError(f"{folder.name}: product.xml has no RadarCenterFrequency")
    return radar_facts(float(hz) / 1e9, root.findtext(".//RadarBand") or None)


def gamma0_linear(dn: np.ndarray, k_beta0_db: float, noise_bias: float) -> np.ndarray:
    """(DN^2 - N) / Kcal_linear in float32; DN 0 (outside the image) and pixels below the noise bias become NaN."""
    p = dn.astype(np.float64) ** 2 - noise_bias
    g = p / 10.0 ** (k_beta0_db / 10.0)
    g[(dn == 0) | (p <= 0)] = np.nan
    return g.astype(np.float32)


def describe(spec, data_dir, area: Area | None = None) -> SourceInfo:
    _check(spec)
    folder = _folder(spec, data_dir)
    path = _imagery(folder, _pols(nrsc.read_meta(folder, "BAND_META.txt"))[0])
    with _rasterio().open(path) as src:
        t = src.transform
        res = abs(t.a)
        return SourceInfo(epsg=raster_epsg(src), resolution_m=res, phase=(t.c + res / 2, t.f - res / 2), files=[str(path)])


def open_on_canvas(spec, canvas: Canvas, area: Area, data_dir, cache_dir=None, tag="job") -> Product:
    _check(spec)
    folder = _folder(spec, data_dir)
    meta = nrsc.read_meta(folder, "BAND_META.txt")
    pols = _pols(meta)
    when = nrsc.parse_time(meta["SceneCenterTime"])
    m = read_window(str(_mask(folder)), canvas, cache_dir)
    if m is None:
        raise AreaError(f"input {spec.key!r}: {folder.name} does not cover the area")
    mask, mx, my, mepsg, _ = m
    valid = to_canvas(mask, mx, my, mepsg, canvas, "nearest", fill=0) == VALID
    layers, files, native, dropped = {}, [], None, []
    for name, pol in zip(("co", "cross"), pols, strict=True):
        path = _imagery(folder, pol)
        files.append(str(path))
        r = read_window(str(path), canvas, cache_dir)
        if r is None:
            raise AreaError(f"input {spec.key!r}: {path.name} does not cover the area")
        dn, x, y, epsg, _ = r
        # Kcal_dB is the Beta0 constant for Level-2B too (document eq. 10), not the Gamma0 or the bare constant tags
        g = gamma0_linear(dn, float(meta[f"Calibration_Constant_Beta0_{pol}"]), float(meta[f"Image_Noise_Bias_{pol}"]))
        native = abs(float(x[1] - x[0])) if len(x) > 1 else canvas.res
        layer = to_canvas(g, x, y, epsg, canvas, "bilinear")
        layer[~valid] = np.nan
        layers[name] = layer
        dropped.append((pol, 100 * float((valid & ~np.isfinite(layer)).sum() / max(valid.sum(), 1))))
    caveats = [str(spec.options["note"])] if spec.options.get("note") else []
    gap = ", ".join(f"{p} {pct:.0f}%" for p, pct in dropped)
    caveats.append(f"EOS-04 {meta['ImagingMode'].strip()} L2B gamma0, noise bias subtracted; pixels at or below the noise "
                   f"level are dropped ({gap} of valid area); layover and shadow masked; no speckle filter.")
    if meta.get("RTC_Apply_Flag") == "0":
        caveats.append("EOS-04: terrain registration failed, so this product is NOT terrain-normalised.")
    if native > canvas.res * 1.5:
        caveats.append(f"EOS-04: {native:g} m pixels resampled to this figure's {canvas.res:g} m grid.")
    credit = str(spec.options.get("credit", CREDIT))
    return Product(
        key=spec.key, layers=layers, x=canvas.x, y=canvas.y, epsg=canvas.epsg, valid=valid & np.isfinite(layers["co"]),
        kind="sar",
        meta=dict(platform="EOS-04", sensor="SAR", label=str(spec.options.get("label", "SAR")), start=when, end=when,
                  resolution_m=canvas.res, crs=crs_label(canvas.epsg), **_radar(folder),
                  backscatter="gamma0, " + ("not " if meta.get("RTC_Apply_Flag") == "0" else "") + "terrain-normalised",
                  attribution=str(spec.options.get("attribution", credit)),
                  credit=credit, items=files),
        facts=SimpleNamespace(date=f"{when.day} {when:%b %Y}", files=folder.name, polarisations="/".join(pols),
                              orbit=meta.get("Node", "").lower(), relative_orbit="", mode=meta["ImagingMode"].strip()),
        caveats=caveats,
    )


sensor("eos04")(SimpleNamespace(describe=describe, open=open_on_canvas, kind="sar"))
