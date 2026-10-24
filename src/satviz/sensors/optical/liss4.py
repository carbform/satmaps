"""ResourceSat-2 LISS-IV (NRSC/ISRO) multispectral product folders: green, red and near-infrared at 5 m.

```toml
[[inputs]]
id = "liss"
sensor = "liss4"
source = { path = "R2F05OCT2026080242010300062SSANSTUC00GTDA" }   # the unzipped product folder (BAND2/3/4.tif + .meta)
```
Digital numbers become top-of-atmosphere reflectance from the product's `.meta`: L = DN x SR / 1024 (SR = the band's saturation
radiance, mW/cm2/sr/um), then rho = pi L d^2 / (ESUN cos(zenith)). There is no blue band, so only false-colour recipes
(`nir_fcc`) and `ndvi` / `ndwi` apply. TOA reflectance is not surface reflectance: haze lifts green and red, so compare
it with Sentinel-2 L2A by pattern, not by value.

Sources: the NRSC R2 Data User Handbook (docs/) gives 10-bit quantisation and nominal saturation radiances of 53 / 47 / 31.5
mW/cm2/sr/um for B2 / B3 / B4, but no irradiance values or DN-to-radiance formula. Those two come from the Disasters Charter
LISS-4 page (see ESUN below). The product's own SaturationRadiance (47.56 / 45.70 / 31.50) is used rather than `B*_Lmax`
(52 / 47 / 31.5); that choice moves absolute green reflectance by about 9 %, and nothing in docs/ settles it.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from satviz.area import Area, AreaError, Canvas
from satviz.cog import _rasterio, raster_epsg, read_converted, valid_ring
from satviz.core import BandInfo, Product, SourceInfo, footprint_or_none, sensor
from satviz.geo import crs_label
from satviz.grid import to_canvas
from satviz.sensors import nrsc
from satviz.sources import SourceError, resolve_one_file

BANDS = {"green": 2, "red": 3, "nir": 4}
# Mean TOA solar irradiance in the same mW/cm2/um family as the saturation radiance (the Disasters Charter LISS-4 page,
# citing ISRO's RE-01 note, prints 181.89 / 156.96 / 110.48). Checked by order of magnitude: median green DN 145 gives ~0.14.
ESUN = {"green": 181.89, "red": 156.96, "nir": 110.48}
DN_RANGE = 1024.0
# Nominal band limits in nm from the NRSC R2 Data User Handbook (LISS-IV table, section 2.3.4):
# B2 0.52-0.59, B3 0.62-0.68, B4 0.77-0.86 um.
RANGES_NM = {"green": (520.0, 590.0), "red": (620.0, 680.0), "nir": (770.0, 860.0)}
PLATFORMS = {"IRS-R2": "ResourceSat-2", "IRS-R2A": "ResourceSat-2A"}
KEYS = {"label", "credit", "attribution", "note"}


def read_meta(folder: Path) -> dict[str, str]:
    return nrsc.read_meta(folder, "*.meta")


def sniff(path) -> bool:
    """An unzipped LISS-IV folder: a `.meta` file with the BAND2, BAND3 and BAND4 images."""
    folder = nrsc.product_folder(Path(path))
    return folder.is_dir() and any(folder.glob("*.meta")) and all((folder / f"BAND{n}.tif").is_file() for n in BANDS.values())


def _folder(spec, data_dir) -> Path:
    return nrsc.product_folder(resolve_one_file(spec, data_dir))


def _when(meta: dict) -> datetime:
    return nrsc.parse_time(meta["SceneCenterTime"])


def earth_sun_distance(when: datetime) -> float:
    """Astronomical units, from the day of year (good to ~1e-4, far below the calibration uncertainty)."""
    return 1.0 - 0.01672 * math.cos(math.radians(0.9856 * (when.timetuple().tm_yday - 4)))


def radiance_scale(meta: dict, band: str) -> tuple[float, str]:
    """(saturation radiance, name of the metadata field it came from): the product's own `B*SaturationRadiance` when it has one
    (ResourceSat-2 products), else `B*_Lmax` (ResourceSat-2A products carry only that)."""
    n = BANDS[band]
    for field_name in (f"B{n}SaturationRadiance", f"B{n}_Lmax"):
        if meta.get(field_name):
            return float(meta[field_name]), field_name.replace(f"B{n}", "B*", 1)
    raise SourceError(f"LISS-IV product has neither B{n}SaturationRadiance nor B{n}_Lmax in its .meta")


def platform_of(meta: dict) -> str:
    return PLATFORMS.get(meta.get("SatID", ""), meta.get("SatID") or "ResourceSat")


def toa_reflectance(dn: np.ndarray, band: str, meta: dict, when: datetime) -> np.ndarray:
    radiance = dn.astype(np.float32) * radiance_scale(meta, band)[0] / DN_RANGE
    sin_elev = math.sin(math.radians(float(meta["SunElevationAtCenter"])))
    return math.pi * radiance * earth_sun_distance(when) ** 2 / (ESUN[band] * sin_elev)


def _check(spec) -> None:
    if unknown := set(spec.options) - KEYS - {"source"}:
        raise SourceError(f"input {spec.key!r}: unknown key(s) {sorted(unknown)}; allowed: {sorted(KEYS | {'source'})}")


def _best_footprint(folder: Path, image: Path):
    """Where the data is, from the image's non-zero pixels; the corner quad of the metadata when they cannot be read."""
    return (footprint_or_none(valid_ring, str(image), lambda dn: dn > 0)
            or footprint_or_none(lambda: nrsc.corners(read_meta(folder))))


def describe(spec, data_dir, area: Area | None = None) -> SourceInfo:
    _check(spec)
    folder = _folder(spec, data_dir)
    path = folder / f"BAND{BANDS['red']}.tif"
    with _rasterio().open(path) as src:
        t = src.transform
        res = abs(t.a)
        return SourceInfo(epsg=raster_epsg(src), resolution_m=res, phase=(t.c + res / 2, t.f - res / 2), files=[str(path)],
                          footprint=None if area is not None else _best_footprint(folder, path))


def _reflectance(dn: np.ndarray, band: str, meta: dict, when: datetime) -> np.ndarray:
    refl = toa_reflectance(dn, band, meta, when)
    refl[dn == 0] = np.nan  # DN 0 is outside the scene
    return refl


def open_on_canvas(spec, canvas: Canvas, area: Area, data_dir, cache_dir=None, tag="job") -> Product:
    _check(spec)
    folder = _folder(spec, data_dir)
    meta = read_meta(folder)
    when = _when(meta)
    layers, files, native = {}, [], None
    for name, n in BANDS.items():
        path = folder / f"BAND{n}.tif"
        files.append(str(path))
        r = read_converted(str(path), canvas, lambda dn, name=name: _reflectance(dn, name, meta, when),
                           f"liss4-toa|{name}", cache_dir)
        if r is None:
            raise AreaError(f"input {spec.key!r}: {path.name} does not cover the area")
        refl, x, y, epsg, native = r
        layers[name] = to_canvas(refl, x, y, epsg, canvas, "bilinear")
    valid = np.isfinite(layers["red"]) & np.isfinite(layers["green"]) & np.isfinite(layers["nir"])
    caveats = [str(spec.options["note"])] if spec.options.get("note") else []
    platform = platform_of(meta)
    field_used = radiance_scale(meta, "red")[1]
    irradiance = ("published ResourceSat-2 solar irradiances, which may differ for 2A (none found in docs/)"
                  if platform.endswith("2A") else "published solar irradiances")
    caveats.append(f"{platform} LISS-IV top-of-atmosphere reflectance from the product's {field_used} and {irradiance}; "
                   "no atmospheric correction, no cloud screening. No blue band: false colour only.")
    if native > canvas.res * 1.5:
        caveats.append(f"LISS-IV: {native:g} m pixels are resampled to this figure's {canvas.res:g} m grid.")
    credit = str(spec.options.get("credit", f"{platform} LISS-IV data, NRSC/ISRO"))
    bands = tuple(BandInfo(id=f"B{n}", layer=name, name=name, range_nm=RANGES_NM[name], resolution_m=native)
                  for name, n in BANDS.items())
    return Product(
        key=spec.key, layers=layers, x=canvas.x, y=canvas.y, epsg=canvas.epsg, valid=valid, kind="optical",
        meta=dict(platform=platform, sensor="LISS-IV", reflectance="top-of-atmosphere",
                  label=str(spec.options.get("label", "LISS-IV")), start=when, end=when, resolution_m=canvas.res,
                  crs=crs_label(canvas.epsg),
                  attribution=str(spec.options.get("attribution", credit)), credit=credit, items=files, time_known=True),
        facts=SimpleNamespace(date=f"{when.day} {when:%b %Y}", files=folder.name, path_row=f"{meta['Path']}/{meta['Row']}"),
        caveats=caveats, bands=bands,
    )


sensor("liss4")(SimpleNamespace(describe=describe, open=open_on_canvas, sniff=sniff, kind="optical"))
