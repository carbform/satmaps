"""Run a job: choose the canvas, read every needed input onto it, render each figure, write a lock file."""
from __future__ import annotations

import dataclasses
import json
from collections import Counter
from pathlib import Path

from satmaps.area import AreaError
from satmaps.arrangements import draw
from satmaps.core import SENSORS, TEMPLATES, THEMES
from satmaps.furniture import Furniture
from satmaps.job import FigureSpec, Job, JobError
from satmaps.layout import LayoutError, apply_text, default_layout, load_layout
from satmaps.registry import load_builtin
from satmaps.templates import TemplateError


def _sensor(spec):
    return SENSORS.get_or_raise(spec.sensor)


def _source_name(spec) -> str:
    """The file or folder name an input reads, as an error message names it."""
    src = spec.options.get("source") or {}
    return Path(src.get("path") or spec.file or spec.key).name


def resolve_area(job: Job, needed: list[str]) -> Job:
    """The job with its area filled in. A job that names no area gets the largest rectangle inside every needed input's footprint,
    at a pixel size that gives about `target_px` pixels along its longer side (never finer than the finest input)."""
    if job.area is not None:
        return job
    from satmaps.autoarea import common_area, pick_resolution

    infos = {k: _sensor(job.inputs[k]).describe(job.inputs[k], job.scene.data_dir, None) for k in needed}
    missing = [k for k, i in infos.items() if not i.footprint]
    if missing:
        raise JobError(f"{job.path}: no footprint for input(s) {missing}; give an [area]")
    try:
        area = common_area({k: i.footprint for k, i in infos.items()},
                           {k: f"{k} ({_source_name(job.inputs[k])})" for k in infos})
    except AreaError as e:
        raise JobError(f"{job.path}: {e}") from None
    res = job.auto_area.get("resolution_m") or pick_resolution(
        area, min(i.resolution_m for i in infos.values()), int(job.auto_area.get("target_px", job.quality.target_px)))
    return dataclasses.replace(job, area=dataclasses.replace(area, resolution_m=float(res)))


def choose_canvas(job: Job, needed: list[str]):
    """Canvas for the job: pixel size from [area] or the finest input; aligned to an input grid when one fits."""
    infos = {k: _sensor(job.inputs[k]).describe(job.inputs[k], job.scene.data_dir, job.area) for k in needed}
    res = job.area.resolution_m or min(i.resolution_m for i in infos.values())
    phase = next((i.phase for i in infos.values()
                  if i.phase and i.epsg == job.area.epsg and abs(i.resolution_m - res) < 1e-6), None)
    return job.area.canvas(res, phase), infos


def resolve_zooms(job: Job, canvas):
    from satmaps.config import Zoom

    out = []
    if len(job.zoom_specs) > 3:
        raise JobError(f"{job.path}: {len(job.zoom_specs)} [[zooms]]; a page has room for three")
    for i, z in enumerate(job.zoom_specs, 1):
        key, name, fit = str(z.get("key", chr(64 + i))), str(z.get("name", "")), False
        if "rows" in z and "cols" in z:
            rows, cols = tuple(z["rows"]), tuple(z["cols"])
        elif "center" in z and "size_km" in z:
            try:
                rows, cols = canvas.window_around(*[float(v) for v in z["center"]], tuple(float(v) for v in z["size_km"]),
                                                  clamp=True)
            except AreaError as e:
                raise JobError(f"zoom {key}: {e}") from None
            fit = True
        else:
            raise JobError(f"{job.path} [[zooms]] #{i}: give `center` + `size_km`, or canvas `rows` + `cols`")
        out.append(Zoom(key, name, rows, cols, fit))
    return tuple(out)


def _layout(fig: FigureSpec, job: Job, layouts_dir, arrangement: str, defaults: dict | None = None) -> dict:
    """The figure's wording: its `layout` file (looked up next to the job file, then the working directory, then
    `layouts_dir`) or the arrangement's built-in one. The template's default wording goes in first (not with a wording file
    of its own), then the job's `text`."""
    if fig.layout:
        name = Path(fig.layout).expanduser()
        if name.suffix != ".toml":
            name = name.with_name(name.name + ".toml")
        tried = [name] if name.is_absolute() else [job.path.parent / name, Path.cwd() / name, Path(layouts_dir) / name]
        found = next((p for p in tried if p.is_file()), None)
        if found is None:
            raise JobError(f"layout {fig.layout!r} not found; looked in: " + ", ".join(str(p.parent) for p in tried))
        data = load_layout(found.parent, found.stem)
    else:
        data = default_layout(arrangement)
    return apply_text(data if fig.layout else apply_text(data, defaults or {}), fig.text)  # a wording file's own text wins


def plan_figure(fig: FigureSpec, job: Job) -> list[tuple[str, ...]]:
    """The input-id tuples of a figure, one figure each: decided by its template (see `satmaps.templates`)."""
    try:
        return TEMPLATES.get_or_raise(fig.template).plan(fig, job)
    except KeyError as e:
        raise JobError(str(e.args[0])) from None
    except TemplateError as e:
        raise JobError(f"{job.path}: {e}") from None


def read_products(job: Job, needed: list[str], cache_dir: str | Path | None = None):
    """Choose the canvas and read each needed input onto it: (canvas, source info per input, products per input)."""
    from satmaps.progress import get_progress

    p = get_progress()
    if p:
        p.update("Aligning canvas grids...")
    canvas, infos = choose_canvas(job, needed)
    products = {}
    for i, k in enumerate(needed, 1):
        spec = job.inputs[k]
        if p:
            p.update(f"Reading input [{i}/{len(needed)}] '{k}' ({_source_name(spec)})...")
        products[k] = _sensor(spec).open(spec, canvas, job.area, job.scene.data_dir, cache_dir, job.scene.name)
    return canvas, infos, products


def placeholders_job(job: Job, cache_dir: str | Path | None = None) -> dict:
    """The `{placeholders}` a wording file of this job can use, with their values: scene names, what the products share, and one
    namespace per input id (`{S1.date}`). Needs the data, because the values come from the products."""
    from satmaps.layout import build_context_products

    load_builtin()
    job = resolve_area(job, list(job.inputs))
    canvas, _, products = read_products(job, list(job.inputs), cache_dir)
    scene = dataclasses.replace(job.scene, zooms=resolve_zooms(job, canvas))
    return build_context_products(scene, products, per_band=True, strict=False)


def run_job(job: Job, out_dir: str | Path, cache_dir: str | Path | None = None,
            layouts_dir: str | Path = "layouts") -> list[Path]:
    load_builtin()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    plan = [(fig, c) for fig in job.figures for c in plan_figure(fig, job)]
    needed = [k for k in job.inputs if any(k in c for _, c in plan)]
    for fig in job.figures:
        for th in fig.themes:
            THEMES.get_or_raise(th)

    from satmaps.progress import get_progress

    p = get_progress()
    if p:
        p.update("Resolving area and footprint overlap...")
    job = resolve_area(job, needed)
    canvas, infos, products = read_products(job, needed, cache_dir)
    scene = dataclasses.replace(job.scene, zooms=resolve_zooms(job, canvas))

    written = []
    per_figure = Counter(id(f) for f, _ in plan)
    for fig, combo in plan:
        try:
            resolved = TEMPLATES[fig.template].resolve(fig, combo, products, job.scene)
        except TemplateError as e:
            raise JobError(f"{job.path}: {e}") from None
        layout = _layout(fig, job, layouts_dir, resolved.arrangement, resolved.text)
        for theme in fig.themes:
            stem = None
            if fig.name:
                parts = [fig.name]
                if len(combo) == 2 and len(plan) > 1:
                    parts.append(f"{combo[0]}vs{combo[1]}")
                elif len(combo) == 1 and per_figure[id(fig)] > 1:  # one file per input must not overwrite its siblings
                    parts.append(combo[0])
                stem = "_".join([*parts, THEMES[theme].tag])
            if p:
                p.update(f"Drawing figure '{stem or fig.template}' ({theme} theme)...")
            written += draw(resolved, scene=scene, products=products, out_dir=out, layout=layout, combo=combo, theme=theme,
                            stem=stem, slot=list(job.inputs).index(combo[0]), strict=fig.strict, stretch=fig.stretch,
                            profile=job.quality, furniture=Furniture(scale=fig.scalebar, north=fig.north, grid=fig.grid))
    _write_lock(job, out, canvas, infos, products, written)
    if p:
        p.done(f"Finished: {len(written)} figure(s) saved.")
    return written


def _write_lock(job: Job, out: Path, canvas, infos: dict, products: dict, written: list[Path]) -> None:
    """Record what was read and how it was placed, so a figure can be reproduced and credited exactly."""
    lock = {
        "job": str(job.path),
        "canvas": dataclasses.asdict(canvas),
        "quality": job.quality.name,
        "inputs_detected": {k: s.sensor for k, s in job.inputs.items()},
        "area_lonlat_bbox": [round(v, 6) for v in canvas.lonlat_bbox()],
        "inputs": {k: {"sensor": job.inputs[k].sensor, "files": i.files, "native_resolution_m": i.resolution_m}
                   for k, i in infos.items()},
        "figures": [p.name for p in written],
    }
    (out / f"{job.path.stem}.lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


__all__ = ["AreaError", "LayoutError", "run_job"]

