"""Run a job: choose the canvas, read every needed input onto it, render each figure, write a lock file."""
from __future__ import annotations

import dataclasses
import json
from collections import Counter
from pathlib import Path

from satviz.area import AreaError
from satviz.arrangements import draw
from satviz.core import SENSORS, TEMPLATES, THEMES
from satviz.job import FigureSpec, Job, JobError
from satviz.layout import LayoutError, apply_text, default_layout, load_layout
from satviz.registry import load_builtin
from satviz.templates import TemplateError


def _sensor(spec):
    return SENSORS.get_or_raise(spec.sensor)


def choose_canvas(job: Job, needed: list[str]):
    """Canvas for the job: pixel size from [area] or the finest input; aligned to an input grid when one fits."""
    infos = {k: _sensor(job.inputs[k]).describe(job.inputs[k], job.scene.data_dir, job.area) for k in needed}
    res = job.area.resolution_m or min(i.resolution_m for i in infos.values())
    phase = next((i.phase for i in infos.values()
                  if i.phase and i.epsg == job.area.epsg and abs(i.resolution_m - res) < 1e-6), None)
    return job.area.canvas(res, phase), infos


def resolve_zooms(job: Job, canvas):
    from satviz.config import Zoom

    out = []
    for i, z in enumerate(job.zoom_specs, 1):
        key, name = str(z.get("key", chr(64 + i))), str(z.get("name", ""))
        if "rows" in z and "cols" in z:
            rows, cols = tuple(z["rows"]), tuple(z["cols"])
        elif "center" in z and "size_km" in z:
            rows, cols = canvas.window_around(*[float(v) for v in z["center"]], tuple(float(v) for v in z["size_km"]))
        else:
            raise JobError(f"{job.path} [[zooms]] #{i}: give `center` + `size_km`, or canvas `rows` + `cols`")
        out.append(Zoom(key, name, rows, cols))
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
    """The input-id tuples of a figure, one figure each: decided by its template (see `satviz.templates`)."""
    try:
        return TEMPLATES.get_or_raise(fig.template).plan(fig, job)
    except KeyError as e:
        raise JobError(str(e.args[0])) from None
    except TemplateError as e:
        raise JobError(f"{job.path}: {e}") from None


def read_products(job: Job, needed: list[str], cache_dir: str | Path | None = None):
    """Choose the canvas and read each needed input onto it: (canvas, source info per input, products per input)."""
    canvas, infos = choose_canvas(job, needed)
    products = {}
    for k in needed:
        spec = job.inputs[k]
        products[k] = _sensor(spec).open(spec, canvas, job.area, job.scene.data_dir, cache_dir, job.scene.name)
    return canvas, infos, products


def placeholders_job(job: Job, cache_dir: str | Path | None = None) -> dict:
    """The `{placeholders}` a wording file of this job can use, with their values: scene names, what the products share, and one
    namespace per input id (`{S1.date}`). Needs the data, because the values come from the products."""
    from satviz.layout import build_context_products

    load_builtin()
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
            written += draw(resolved, scene=scene, products=products, out_dir=out, layout=layout, combo=combo, theme=theme,
                            stem=stem, slot=list(job.inputs).index(combo[0]), strict=fig.strict, stretch=fig.stretch)
    _write_lock(job, out, canvas, infos, products, written)
    return written


def _write_lock(job: Job, out: Path, canvas, infos: dict, products: dict, written: list[Path]) -> None:
    """Record what was read and how it was placed, so a figure can be reproduced and credited exactly."""
    lock = {
        "job": str(job.path),
        "canvas": dataclasses.asdict(canvas),
        "area_lonlat_bbox": [round(v, 6) for v in canvas.lonlat_bbox()],
        "inputs": {k: {"sensor": job.inputs[k].sensor, "files": i.files, "native_resolution_m": i.resolution_m}
                   for k, i in infos.items()},
        "figures": [p.name for p in written],
    }
    (out / f"{job.path.stem}.lock.json").write_text(json.dumps(lock, indent=2) + "\n")


__all__ = ["AreaError", "LayoutError", "run_job"]

