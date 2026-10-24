"""EOS-04 (RISAT-1A) SAR, NRSC/ISRO: Level-2B terrain-normalised gamma-nought ARD product folders (ScanSAR MRS).

```toml
[[inputs]]
id = "E"
sensor = "eos04"
source = { path = "E04_SAR_MRS_10SEP2026_...E094265" }   # the unzipped product folder
backscatter = "gamma0"                                    # or "sigma0"
```
The GeoTIFFs hold DN, a representation of gamma-nought (EOS-04 Data Products Format Document, section 6.3):
gamma0_dB = 20 log10(DN) - Kcal_dB, and in linear units gamma0 = DN^2 / Kcal_linear, with the image noise bias N
subtracted from DN^2 first (section 3.0). Layers are `co` and `cross` (linear power) for the two polarisations in the
product (HH/HV here). Only pixels flagged 128 in the mask file (valid, not layover, not shadow, inside the image) are used.

`backscatter = "sigma0"` undoes the terrain normalisation with the document's equations 13 and 14: Beta0 = Gamma0 x local
illumination area, Sigma0 = Beta0 x sin(local incidence angle), using the product's `*_area.tif` and `*_lia.tif`. On flat ground
that is gamma0 x cos(incidence); on slopes it differs. The result is the un-normalised sigma0 of a Level-2A product.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from satviz.area import Area, AreaError, Canvas
from satviz.cog import _rasterio, raster_epsg, read_window
from satviz.core import Product, SourceInfo, footprint_or_none, sensor
from satviz.geo import crs_label
from satviz.grid import to_canvas
from satviz.radar import radar_facts
from satviz.sensors import nrsc
from satviz.sources import SourceError, resolve_one_file

CREDIT = "EOS-04 SAR data, NRSC/ISRO"
VALID = 128  # mask value for undistorted valid image data (16 layover, 64 shadow, 0 outside)
KEYS = {"label", "credit", "attribution", "note", "backscatter"}
CONVENTIONS = ("gamma0", "sigma0")


def sniff(path) -> bool:
    """An unzipped EOS-04 Level-2B folder: `BAND_META.txt` that names two polarisations."""
    folder = nrsc.product_folder(Path(path))
    meta = folder / "BAND_META.txt"
    return folder.is_dir() and meta.is_file() and "TxRxPol1" in meta.read_text(errors="replace")


def _folder(spec, data_dir) -> Path:
    return nrsc.product_folder(resolve_one_file(spec, data_dir))


def _check(spec) -> None:
    if unknown := set(spec.options) - KEYS - {"source"}:
        raise SourceError(f"input {spec.key!r}: unknown key(s) {sorted(unknown)}; allowed: {sorted(KEYS | {'source'})}")
    if (c := spec.options.get("backscatter", "gamma0")) not in CONVENTIONS:
        raise SourceError(f"input {spec.key!r}: backscatter must be one of {', '.join(CONVENTIONS)}, not {c!r}")


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


def _aux(folder: Path, suffix: str) -> Path:
    hits = sorted(folder.glob(f"*_{suffix}.tif"))
    if not hits:
        raise FileNotFoundError(f"{folder}: no *_{suffix}.tif; it is needed for backscatter = \"sigma0\"")
    return hits[0]


def to_sigma0(gamma0: np.ndarray, area: np.ndarray, lia_deg: np.ndarray) -> np.ndarray:
    """Sigma-nought from the Level-2B gamma-nought, as the format document gives it (section 6.3):
    Beta0 = Gamma0 x local illumination area (eq. 13), Sigma0 = Beta0 x sin(local incidence angle) (eq. 14).
    This undoes the terrain normalisation, so the result is the un-normalised sigma0 of a Level-2A product.
    Pixels with no area or incidence angle (0 and -2 in the files) are NaN."""
    ok = np.isfinite(area) & np.isfinite(lia_deg) & (area > 0) & (lia_deg > 0)
    out = gamma0 * area * np.sin(np.deg2rad(lia_deg))
    out[~ok] = np.nan
    return out.astype(np.float32)


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
        return SourceInfo(epsg=raster_epsg(src), resolution_m=res, phase=(t.c + res / 2, t.f - res / 2), files=[str(path)],
                          footprint=footprint_or_none(lambda: nrsc.corners(nrsc.read_meta(folder, "BAND_META.txt"))))


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
    convention = spec.options.get("backscatter", "gamma0")
    aux = {}
    if convention == "sigma0":
        if meta.get("RTC_Apply_Flag") == "0":
            raise SourceError(f"input {spec.key!r}: {folder.name} was not terrain-normalised (RTC_Apply_Flag 0), so the "
                              "document's conversion from gamma0 to sigma0 does not apply; use backscatter = \"gamma0\"")
        for name in ("area", "lia"):
            r = read_window(str(_aux(folder, name)), canvas, cache_dir)
            if r is None:
                raise AreaError(f"input {spec.key!r}: the {name} layer does not cover the area")
            aux[name] = r[0]
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
        if aux:
            if aux["area"].shape != dn.shape or aux["lia"].shape != dn.shape:
                raise SourceError(f"input {spec.key!r}: the area and incidence-angle layers are not on the imagery's grid")
            g = to_sigma0(g, aux["area"], aux["lia"])
        native = abs(float(x[1] - x[0])) if len(x) > 1 else canvas.res
        layer = to_canvas(g, x, y, epsg, canvas, "bilinear")
        layer[~valid] = np.nan
        layers[name] = layer
        dropped.append((pol, 100 * float((valid & ~np.isfinite(layer)).sum() / max(valid.sum(), 1))))
    caveats = [str(spec.options["note"])] if spec.options.get("note") else []
    gap = ", ".join(f"{p} {pct:.0f}%" for p, pct in dropped)
    what = ("sigma0 from L2B gamma0 by the document's eq. 13-14 (terrain normalisation undone)" if aux else "L2B gamma0")
    caveats.append(f"EOS-04 {meta['ImagingMode'].strip()} {what}, noise bias subtracted; pixels at or below the noise "
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
                  backscatter=("sigma0, not terrain-normalised" if aux else
                               "gamma0, " + ("not " if meta.get("RTC_Apply_Flag") == "0" else "") + "terrain-normalised"),
                  attribution=str(spec.options.get("attribution", credit)),
                  credit=credit, items=files),
        facts=SimpleNamespace(date=f"{when.day} {when:%b %Y}", files=folder.name, polarisations="/".join(pols),
                              orbit=meta.get("Node", "").lower(), relative_orbit="", mode=meta["ImagingMode"].strip()),
        caveats=caveats,
    )


sensor("eos04")(SimpleNamespace(describe=describe, open=open_on_canvas, sniff=sniff, kind="sar"))
