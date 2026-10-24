"""The Python API: `inspect` a product, `render` figures from paths. `satviz quick` is a command line over `render`.

``render`` writes no figure logic of its own. It builds the same tables a job file holds, resolves the automatic parts (sensor,
area, pixel size), and hands them to `run_job`; ``save_job`` writes those resolved tables, so running the saved file gives the
same figures. Importing `satviz` stays light: the heavy modules load when a function is called.
"""
from __future__ import annotations

import os
from pathlib import Path


class TooLarge(ValueError):
    """An automatic area is too large to draw quickly. `suggestion` is a (west, south, east, north) box around its centre."""

    def __init__(self, message: str, suggestion: tuple[float, float, float, float]):
        super().__init__(message)
        self.suggestion = suggestion


MAX_TILES = 6
MAX_AUTO_KM2 = 15_000  # an automatic area above this (about 120 x 120 km) needs --bbox or --allow-large


def inspect(path: str | os.PathLike) -> dict:
    """What satviz knows about a product without reading its pixels: sensor, kind, native pixel size, where it has data.

    ``footprint`` is a (lon, lat) ring and ``bbox`` its (west, south, east, north); both are None when the product's metadata does
    not state where it is."""
    from satviz.config import InputSpec
    from satviz.core import SENSORS
    from satviz.detect import detect

    path = Path(path).expanduser().resolve()
    name = detect(path)
    reader = SENSORS[name]
    info = reader.describe(InputSpec("x", name, "", {"source": {"path": str(path)}}), path.parent, None)
    ring = info.footprint
    bbox = None
    if ring:
        lons, lats = zip(*ring, strict=True)
        bbox = (min(lons), min(lats), max(lons), max(lats))
    return {"path": str(path), "sensor": name, "kind": reader.kind, "resolution_m": info.resolution_m, "epsg": info.epsg,
            "bbox": bbox, "footprint": ring}


def scan(folder: str | os.PathLike) -> list[dict]:
    """The products directly inside a folder: ``{"path", "name", "sensor", "kind", "note"}`` for each one a sensor reads, and
    ``{"path", "name", "sensor": None, "kind": None, "note": "unzip it"}`` for a zip. Anything else is skipped.

    It looks at names and a few files, not pixels, so it is quick on a slow disk; `inspect` reads a product's footprint."""
    from satviz.core import SENSORS
    from satviz.detect import DetectError, detect

    root = Path(folder).expanduser()
    if not root.is_dir():
        raise ValueError(f"{root}: not a folder")
    rows = []
    for p in sorted(root.iterdir(), key=lambda q: q.name.lower()):
        if p.name.startswith("."):
            continue
        if p.suffix.lower() == ".zip":
            rows.append({"path": str(p), "name": p.name, "sensor": None, "kind": None, "note": "unzip it"})
            continue
        try:
            name = detect(p)
        except DetectError:
            continue
        rows.append({"path": str(p), "name": p.name, "sensor": name, "kind": SENSORS[name].kind, "note": ""})
    return rows


def _area_table(area) -> dict:
    """The `[area]` table for what a caller passed: nothing (automatic), a (w, s, e, n) box, or a table of the job-file keys."""
    if area is None:
        return {}
    if isinstance(area, dict):
        return dict(area)
    if len(area) == 4:
        return {"bbox": [float(v) for v in area]}
    raise ValueError("area must be a (west, south, east, north) box in degrees "
                     "or a dict like {'center': [lat, lon], 'size_km': [w, h]}")


def _default_arrangement(template: str, kinds: list[str]) -> str:
    n = len(kinds)
    if n > MAX_TILES:
        raise ValueError(f"{n} inputs on one figure is too many (at most {MAX_TILES}); render them in groups")
    if template == "sar_optical":
        return "compare" if n == 2 else "grid"
    return "single" if n == 1 else "compare" if n == 2 else "grid"


def build_job(paths, *, area=None, theme: str = "minimal", quality: str = "quick", title: str | None = None,
              template: str | None = None, arrangement: str | None = None, bands: bool = False, resolution_m: float | None = None,
              allow_different_passes: bool = False, allow_large: bool = False, data_dir=None):
    """The `Job` for some paths, with sensors detected, ids chosen, template and arrangement picked from what the inputs are, and
    the area and pixel size resolved. Also returns the job-file tables that reproduce it."""
    import dataclasses

    from satviz.detect import detect, input_id
    from satviz.job import JobError, job_from_dict
    from satviz.run import resolve_area

    if not paths:
        raise ValueError("give at least one product path")
    inputs, taken = [], set()
    for p in paths:
        p = Path(p).expanduser().resolve()
        sensor = detect(p)
        key = input_id(sensor, p, taken)
        taken.add(key)
        inputs.append({"id": key, "sensor": sensor, "source": {"path": str(p)}})
    ids = [i["id"] for i in inputs]
    from satviz.core import SENSORS
    from satviz.registry import load_builtin

    load_builtin()
    kinds = [SENSORS[i["sensor"]].kind for i in inputs]
    chosen = template or ("sar_optical" if len(set(kinds)) > 1 else kinds[0])
    arrangement = "bands" if bands else arrangement or _default_arrangement(chosen, kinds)
    name = _figure_name([i["sensor"] for i in inputs], quality)
    fig = {"name": name, "template": chosen, "inputs": ids, "theme": theme,
           "arrangement": arrangement, **({"text": {"title": title}} if title else {}),
           **({"allow_different_passes": True} if allow_different_passes else {})}
    table = _area_table(area)
    if resolution_m:
        table["resolution_m"] = float(resolution_m)
    raw = {"quality": quality, "scene": {"name": title or ""}, "area": table, "inputs": inputs, "figures": [fig]}
    root = Path(data_dir) if data_dir else Path.cwd()
    job = job_from_dict(raw, root / f"{name}.toml", root)
    try:
        job = resolve_area(job, ids)
        job = _with_pixel_size(job, ids)
    except JobError as e:
        raise ValueError(str(e).removeprefix(f"{job.path}: ")) from None
    if not allow_large and not ({"center", "bbox"} & set(table)):
        _check_size(job.area)
    raw["area"] = _resolved_area_table(job.area)
    return dataclasses.replace(job, auto_area={}), raw


def _with_pixel_size(job, ids: list[str]):
    """A caller's box has no pixel size yet: pick one for the profile, as an automatic area does."""
    import dataclasses

    from satviz.autoarea import pick_resolution
    from satviz.core import SENSORS

    if job.area.resolution_m:
        return job
    finest = min(SENSORS[job.inputs[k].sensor].describe(job.inputs[k], job.scene.data_dir, job.area).resolution_m for k in ids)
    res = pick_resolution(job.area, finest, job.quality.target_px)
    return dataclasses.replace(job, area=dataclasses.replace(job.area, resolution_m=res))


def _figure_name(sensors: list[str], quality: str) -> str:
    """The figure's name, and so its files' (`nisar_sentinel1_quick_Minimal.png`, `nisar_sentinel1_quick.lock.json`): the sensors
    in the order given, then the profile unless it is the full one."""
    names = list(dict.fromkeys(sensors))
    base = "_".join(names) if len(names) <= 3 else "overview"
    return base if quality == "publication" else f"{base}_{quality}"


def _check_size(area) -> None:
    """Refuse an automatic area that is very large: it means reading a whole frame, which is slow. Say how to ask for less."""
    km2 = (area.xmax - area.xmin) * (area.ymax - area.ymin) / 1e6
    if km2 <= MAX_AUTO_KM2:
        return
    from satviz.area import Area, _tf

    lon, lat = _tf(area.epsg, 4326).transform((area.xmin + area.xmax) / 2, (area.ymin + area.ymax) / 2)
    w, s, e, n = Area.from_config({"center": [lat, lon], "size_km": [60, 60]}).lonlat_bbox()
    size = f"{(area.xmax - area.xmin) / 1000:.0f} x {(area.ymax - area.ymin) / 1000:.0f} km ({km2:,.0f} km²)"
    raise TooLarge(f"the overlap of the inputs is {size}, and drawing all of it reads a whole frame: slow. Give the place you "
                   f"want: --bbox W S E N (for its centre 60 km: --bbox {w:.2f} {s:.2f} {e:.2f} {n:.2f}), "
                   "or --allow-large to draw it all.", (round(w, 2), round(s, 2), round(e, 2), round(n, 2)))


def _resolved_area_table(area) -> dict:
    """An `[area]` table that gives back this area: centre and size, written to 8 decimals so the canvas is the same."""
    from satviz.area import _tf

    lon, lat = _tf(area.epsg, 4326).transform((area.xmin + area.xmax) / 2, (area.ymin + area.ymax) / 2)
    return {"center": [round(lat, 8), round(lon, 8)], "size_km": [round((area.xmax - area.xmin) / 1000, 8),
                                                                  round((area.ymax - area.ymin) / 1000, 8)],
            "crs": f"EPSG:{area.epsg}", "resolution_m": area.resolution_m}


def render(paths, *, out: str | os.PathLike = "outputs", cache: str | os.PathLike | None = "cache", save_job=None,
           **options) -> list[Path]:
    """Render one figure from product paths and return the PNG paths written (and a PDF beside each for ``"publication"``).

    Options: ``area`` (None: the overlap of the inputs; a (west, south, east, north) box; or a dict of `[area]` keys),
    ``theme``, ``quality`` ("quick", "medium" or "publication"), ``title`` (default: what the figure shows), ``template`` and
    ``arrangement`` (normally picked from the inputs), ``bands`` (optical: one panel per band), ``resolution_m``,
    ``allow_different_passes``, ``allow_large`` (draw an automatic area above 15,000 km²), ``data_dir``.
    ``save_job`` writes the job file that reproduces the figure."""
    from satviz.run import run_job

    job, raw = build_job(paths, **options)
    if save_job:
        write_job(raw, Path(save_job))
    return run_job(job, out, cache)


def job_toml(raw: dict) -> str:
    """Job-file tables as TOML text (the subset a job uses: strings, numbers, booleans, lists, tables, arrays of tables)."""
    return _toml(raw)


def write_job(raw: dict, dest: Path) -> None:
    """Write job-file tables as a TOML file."""
    dest.write_text(_toml(raw))


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_value(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"cannot write {v!r} as TOML")


def _toml(raw: dict) -> str:
    lines = ["# Written by `satviz quick --save-job`: run it with  satviz run <this file>"]
    for k, v in raw.items():
        if not isinstance(v, (dict, list)) or (isinstance(v, list) and not all(isinstance(x, dict) for x in v)):
            lines.append(f"{k} = {_value(v)}")
    for k, v in raw.items():
        if isinstance(v, dict):
            lines += ["", f"[{k}]", *(f"{a} = {_value(b)}" for a, b in v.items())]
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            for item in v:
                lines += ["", f"[[{k}]]", *(f"{a} = {_value(b)}" for a, b in item.items())]
    return "\n".join(lines) + "\n"
