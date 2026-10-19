"""Optical sensors read from a STAC catalogue: pick the scene by date and by cloud in *your* area, read it onto the canvas.

Selection (``source = { stac = "earth-search", date = "2026-09-25", window_days = 7, max_cloud = 20 }``):

1. search the catalogue for scenes touching the area within ``date`` +/- ``window_days``;
2. group tiles of the same acquisition day, order the groups by distance from ``date`` (``pick = "closest"``) or by cloud;
3. read the quality layer under the canvas and measure cloud, shadow and cirrus *in the area* (not the tile-wide figure);
4. take the first group within ``max_cloud`` that covers at least ``min_coverage`` of the area.

Pin a scene exactly with ``item = "S2B_46RFR_20260924_0_L2A"`` (the lock file records what was chosen).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np

from satviz import stac
from satviz.area import Area, AreaError, Canvas
from satviz.cog import read_window
from satviz.core import Product, SourceInfo
from satviz.geo import crs_label
from satviz.grid import to_canvas
from satviz.sources import SourceError, source_of

SOURCE_KEYS = {"stac", "collection", "date", "window_days", "max_cloud", "pick", "min_coverage", "item", "items", "orbit"}
MAX_EVALUATED = 8  # scene groups whose cloud is measured before giving up


@dataclass(frozen=True)
class OpticalCollection:
    sensor: str  # registry name
    provider: str  # default STAC provider
    collection: str
    platform: str  # printed on the figure, e.g. "Sentinel-2"
    label: str  # e.g. "L2A"
    bands: dict  # layer name -> asset key; layers are surface reflectance 0..1
    reference_band: str  # layer whose asset gives the grid (CRS, pixel size, phase)
    quality_asset: str | None  # per-pixel quality layer; None: coverage is judged from the reference band, cloud is 0
    cloud_mask: Callable[[np.ndarray], np.ndarray]  # quality array -> bool, cloud / shadow / cirrus
    nodata_mask: Callable[[np.ndarray], np.ndarray]  # quality array -> bool, no data
    attribution: str | tuple  # text (or every fragment of a tuple) that must appear in the credits
    credit: Callable[[int, str], str]  # (year, platform) -> credit line
    kind: str = "optical"  # layer vocabulary of the product: "optical" or "sar"
    group_key: Callable[[dict], str] = field(default=lambda it: it["properties"]["datetime"][:10])
    platform_of: Callable[[dict], str] | None = None  # platform name from an item (Landsat 8 or 9); default: `platform`
    bands_for: Callable[[dict], dict] | None = None  # layer -> asset for this item, when it varies (SAR polarisations)
    make_caveats: Callable[..., list] | None = None  # (platform, when, cloud_pct, group) -> caveats; default: cloud text
    nodata_value: float | None = None  # raw value to treat as no data when the asset does not say
    extra_query: Callable[[dict], dict] | None = None  # source table -> STAC query, e.g. orbit direction


def _naive_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)


def parse_source(spec, coll: OpticalCollection) -> dict:
    src = source_of(spec)
    if "orbit" in src and coll.extra_query is None:
        raise SourceError(f"input {spec.key!r}: `orbit` only applies to radar collections")
    if "stac" not in src:
        raise SourceError(f"input {spec.key!r}: {coll.sensor} reads from a catalogue, e.g. "
                          f'source = {{ stac = "{coll.provider}", date = "2026-09-25" }}')
    if unknown := set(src) - SOURCE_KEYS:
        raise SourceError(f"input {spec.key!r}: unknown source key(s) {sorted(unknown)}; allowed: {sorted(SOURCE_KEYS)}")
    pick = src.get("pick", "closest")
    if pick not in ("closest", "least_cloudy"):
        raise SourceError(f"input {spec.key!r}: pick must be \"closest\" or \"least_cloudy\", not {pick!r}")
    if not (src.get("item") or src.get("items") or src.get("date")):
        raise SourceError(f"input {spec.key!r}: give `date` (e.g. \"2026-09-25\") or `item`")
    return src


def _target_and_range(src: dict) -> tuple[date, str]:
    try:
        target = date.fromisoformat(str(src["date"]))
    except (KeyError, ValueError):
        raise SourceError(f"source date must look like 2026-09-25, got {src.get('date')!r}") from None
    w = int(src.get("window_days", 7))
    lo, hi = target - timedelta(days=w), target + timedelta(days=w)
    return target, f"{lo.isoformat()}T00:00:00Z/{hi.isoformat()}T23:59:59Z"


_search_cache: dict = {}


def candidates(spec, coll: OpticalCollection, area: Area) -> list[list[dict]]:
    """Scene groups (tiles of one acquisition day) in the order they should be tried."""
    src = parse_source(spec, coll)
    bbox = area.lonlat_bbox()
    key = (repr(sorted(src.items())), bbox, coll.collection)
    if key in _search_cache:
        return _search_cache[key]
    prov, collection = src["stac"], src.get("collection", coll.collection)
    pinned = src.get("items") or ([src["item"]] if src.get("item") else None)
    if pinned:
        items = stac.search(prov, collection, bbox, "", ids=list(pinned))
        target = None
    else:
        target, rng = _target_and_range(src)
        items = stac.search(prov, collection, bbox, rng, query=coll.extra_query(src) if coll.extra_query else None)
    if not items:
        raise SourceError(f"input {spec.key!r}: no {collection} scenes in {prov} for this area"
                          + (f" within {src.get('window_days', 7)} days of {src['date']}; widen window_days" if target else ""))
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(coll.group_key(it), []).append(it)
    ordered = list(groups.values())
    if target is not None:
        ordered.sort(key=lambda g: abs((_naive_utc(g[0]["properties"]["datetime"]).date() - target).days))
    _search_cache[key] = ordered
    return ordered


def describe_group(it: dict, coll: OpticalCollection) -> tuple[float, int, tuple[float, float]]:
    """(pixel size, EPSG, centre of one pixel) of an item's reference band, from catalogue metadata."""
    a = it["assets"][(coll.bands_for(it) if coll.bands_for else coll.bands)[coll.reference_band]]
    tr = a.get("proj:transform") or it["properties"].get("proj:transform")
    epsg = a.get("proj:epsg") or it["properties"].get("proj:epsg")
    if not tr or not epsg:
        raise SourceError(f"{it['id']}: the catalogue gives no grid (proj:transform/epsg) for {coll.reference_band}")
    res = abs(float(tr[0]))
    return res, int(epsg), (tr[2] + res / 2, tr[5] - res / 2)


def describe(spec, coll: OpticalCollection, area: Area) -> SourceInfo:
    """Grid of the scenes (CRS, pixel size, phase) from catalogue metadata, before any pixel is read."""
    res, epsg, phase = describe_group(candidates(spec, coll, area)[0][0], coll)
    return SourceInfo(epsg=epsg, resolution_m=res, phase=phase, files=[])


def _layer(items, asset, prov, collection, canvas, cache_dir, *, quality: bool, nodata_value=None) -> np.ndarray:
    """One band (reflectance, NaN where empty) or the quality layer (integer classes, 0 where empty), mosaicked over tiles."""
    shape = (canvas.height, canvas.width)
    out = np.zeros(shape, np.uint16) if quality else np.full(shape, np.nan, np.float32)
    for it in items:
        r = read_window(stac.sign(prov, collection, stac.href_of(it, asset)), canvas, cache_dir)
        if r is None:
            continue
        arr, x, y, epsg, nodata = r
        if quality:
            new = to_canvas(arr.astype(np.uint16), x, y, epsg, canvas, "nearest", fill=0)
            out = np.where(out == 0, new, out)
        else:
            a = arr.astype(np.float32)
            nd = nodata if nodata is not None and not np.isnan(nodata) else nodata_value
            if nd is not None:
                a[arr == nd] = np.nan
            scale, offset = stac.scale_offset(it, asset)
            new = to_canvas(a * scale + offset, x, y, epsg, canvas, "bilinear")
            out = np.where(np.isnan(out), new, out)
    return out


def _bands(group, coll) -> dict:
    return coll.bands_for(group[0]) if coll.bands_for else coll.bands


def _assess(group, coll, prov, collection, canvas, cache_dir) -> dict:
    if coll.quality_asset is None:  # no quality layer: coverage from the reference band, no cloud
        ref = _layer(group, _bands(group, coll)[coll.reference_band], prov, collection, canvas, cache_dir, quality=False,
                     nodata_value=coll.nodata_value)
        seen = np.isfinite(ref)
        return dict(qa=np.where(seen, 1, 0).astype(np.uint16), coverage=float(seen.mean()), cloud_pct=0.0)
    qa = _layer(group, coll.quality_asset, prov, collection, canvas, cache_dir, quality=True)
    nodata = coll.nodata_mask(qa)
    seen = ~nodata
    cloud = coll.cloud_mask(qa) & seen
    n = int(seen.sum())
    return dict(qa=qa, coverage=n / qa.size, cloud_pct=100 * float(cloud.sum()) / max(n, 1))


def select(spec, coll: OpticalCollection, area: Area, canvas: Canvas, cache_dir,
           explain_only: bool = False) -> tuple[list[dict] | None, dict | None, list[dict]]:
    """(group, its assessment, assessments of every group tried), or an explanatory error.

    With `explain_only` nothing is raised: the group is None when no scene qualifies (used by `satviz search`)."""
    src = parse_source(spec, coll)
    prov, collection = src["stac"], src.get("collection", coll.collection)
    max_cloud, min_cov = float(src.get("max_cloud", 20)), float(src.get("min_coverage", 0.8))
    pinned = bool(src.get("item") or src.get("items"))
    tried = []
    for group in candidates(spec, coll, area)[:MAX_EVALUATED]:
        a = _assess(group, coll, prov, collection, canvas, cache_dir)
        a["date"] = group[0]["properties"]["datetime"][:10]
        a["ids"] = [g["id"] for g in group]
        tried.append(a)
        ok = a["coverage"] >= min_cov and (pinned or a["cloud_pct"] <= max_cloud)
        a["ok"] = ok
        if ok and (pinned or src.get("pick", "closest") == "closest"):
            return group, a, tried
    good = [(a, g) for a, g in zip(tried, candidates(spec, coll, area), strict=False) if a["ok"]]
    if good:  # least_cloudy
        a, g = min(good, key=lambda ag: ag[0]["cloud_pct"])
        return g, a, tried
    if explain_only:
        return None, None, tried
    lines = "\n  ".join(f"{a['date']}  cloud {a['cloud_pct']:.0f}%  coverage {100 * a['coverage']:.0f}%" for a in tried)
    raise AreaError(f"input {spec.key!r}: no scene has at most {max_cloud:g}% cloud over the area with at least "
                    f"{100 * min_cov:.0f}% coverage. Tried:\n  {lines}\nRaise max_cloud, widen window_days or move date.")


def open_on_canvas(spec, canvas: Canvas, area: Area, coll: OpticalCollection, cache_dir=None) -> Product:
    cache_dir = None if cache_dir is None else str(cache_dir)
    group, assess, _ = select(spec, coll, area, canvas, cache_dir)
    src = parse_source(spec, coll)
    prov, collection = src["stac"], src.get("collection", coll.collection)
    layers = {name: _layer(group, asset, prov, collection, canvas, cache_dir, quality=False, nodata_value=coll.nodata_value)
              for name, asset in _bands(group, coll).items()}
    ref = layers[coll.reference_band]
    valid = np.isfinite(ref) if coll.kind == "optical" else np.isfinite(ref) & (ref > 0)
    times = [_naive_utc(g["properties"]["datetime"]) for g in group]
    when = min(times)
    cloud = assess["cloud_pct"]
    qa = assess["qa"]
    platform = coll.platform_of(group[0]) if coll.platform_of else coll.platform
    if coll.quality_asset is not None:
        layers["cloud"] = (coll.cloud_mask(qa) & ~coll.nodata_mask(qa)).astype(np.float32)
    if coll.make_caveats:
        caveats = coll.make_caveats(platform, when, cloud, group)
    else:
        caveats = [f"{platform}, {when:%d %b %Y}: {cloud:.0f}% cloud, shadow or cirrus in view; clouds are shown, not masked."]
    native = describe_group(group[0], coll)[0]
    if native > canvas.res * 1.5:  # never let a smooth picture pass for a sharp one
        caveats = [*caveats, f"{platform}: {native:g} m pixels resampled to the {canvas.res:g} m grid."]
    props = group[0]["properties"]
    return Product(
        key=spec.key, layers=layers, x=canvas.x, y=canvas.y, epsg=canvas.epsg, valid=valid, kind=coll.kind,
        meta=dict(platform=platform, sensor=coll.label, label=coll.label, start=when, end=max(times),
                  resolution_m=canvas.res, crs=crs_label(canvas.epsg), attribution=coll.attribution,
                  credit=coll.credit(when.year, platform), items=assess["ids"]),
        facts=SimpleNamespace(cloud_pct=cloud, coverage_pct=100 * assess["coverage"], items=", ".join(assess["ids"]),
                              date=f"{when.day} {when:%b %Y}", collection=collection, provider=prov,
                              orbit=props.get("sat:orbit_state", ""), relative_orbit=props.get("sat:relative_orbit", ""),
                              polarisations="/".join(props.get("sar:polarizations", []))),
        caveats=caveats,
    )


def search_rows(spec, coll: OpticalCollection, area: Area, canvas: Canvas, cache_dir=None) -> list[dict]:
    """What `satviz search` prints: each scene group tried, with cloud and coverage in the area, and which one wins."""
    group, _, tried = select(spec, coll, area, canvas, None if cache_dir is None else str(cache_dir), explain_only=True)
    chosen = group[0]["id"] if group else None
    return [dict(date=a["date"], scenes=a["ids"], cloud_pct=a["cloud_pct"], coverage_pct=100 * a["coverage"], ok=a["ok"],
                 chosen=chosen in a["ids"]) for a in tried]
