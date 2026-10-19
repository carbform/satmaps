"""Run a job: choose the canvas, read every needed input onto it, render each figure, write a lock file."""
from __future__ import annotations

import dataclasses
import itertools
import json
from pathlib import Path

from satviz.area import AreaError
from satviz.core import SENSORS, THEMES
from satviz.job import FigureSpec, Job, JobError
from satviz.layout import LayoutError, apply_text, default_layout, load_layout
from satviz.registry import load_builtin
from satviz.templates import compare, single

DEFAULT_RECIPE = {"sar": "sar_fcc", "optical": "true_colour"}  # by product kind, when a figure names none
CHIP_SLOT = ("a", "b")


def _sensor(spec):
    return SENSORS.get_or_raise(spec.sensor)


def choose_canvas(job: Job, needed: list[str]):
    """Canvas for the job: pixel size from [area] or the finest input; aligned to an input grid when one fits."""
    infos = {k: _sensor(job.inputs[k]).describe(job.inputs[k], job.scene.data_dir) for k in needed}
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


def _layout(fig: FigureSpec, layouts_dir) -> dict:
    if fig.layout:
        p = Path(fig.layout)
        data = load_layout(p.parent, p.stem) if p.suffix == ".toml" and p.exists() else load_layout(layouts_dir, fig.layout)
    else:
        data = default_layout(fig.template)
    return apply_text(data, fig.text)


def combos(fig: FigureSpec) -> list[tuple[str, ...]]:
    if fig.template == "single":
        return [(k,) for k in fig.inputs]
    if fig.template == "compare":
        if fig.pairs == "all":
            if len(fig.inputs) < 2:
                raise JobError("compare with pairs = \"all\" needs at least two inputs")
            return list(itertools.combinations(fig.inputs, 2))
        if len(fig.inputs) != 2:
            raise JobError(f"compare needs exactly 2 inputs (or pairs = \"all\"), got {list(fig.inputs)}")
        return [tuple(fig.inputs)]
    raise JobError(f"unknown template {fig.template!r}; available: single, compare")


def run_job(job: Job, out_dir: str | Path, cache_dir: str | Path | None = None,
            layouts_dir: str | Path = "layouts") -> list[Path]:
    load_builtin()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    plan = [(fig, c) for fig in job.figures for c in combos(fig)]
    needed = [k for k in job.inputs if any(k in c for _, c in plan)]
    for fig in job.figures:
        for th in fig.themes:
            THEMES.get_or_raise(th)

    canvas, infos = choose_canvas(job, needed)
    scene = dataclasses.replace(job.scene, zooms=resolve_zooms(job, canvas))
    products = {}
    for k in needed:
        spec = job.inputs[k]
        products[k] = _sensor(spec).open(spec, canvas, job.scene.data_dir, cache_dir, job.scene.name)

    written = []
    for fig, combo in plan:
        layout = _layout(fig, layouts_dir)
        recipes = {k: fig.recipes.get(k) or fig.recipes.get("default") or DEFAULT_RECIPE[products[k].kind] for k in combo}
        for theme in fig.themes:
            stem = None
            if fig.name:
                parts = [fig.name]
                if len(combo) == 2 and len(plan) > 1:
                    parts.append(f"{combo[0]}vs{combo[1]}")
                stem = "_".join([*parts, THEMES[theme].tag])
            if fig.template == "single":
                k = combo[0]
                paths = single.render(scene, products, out, layout, input=k, recipe=recipes[k],
                                      chip_slot=CHIP_SLOT[min(list(job.inputs).index(k), 1)], theme=theme, stem=stem)
            else:
                per_band = None if fig.stretch is None else fig.stretch == "per-band"
                paths = compare.render(scene, products, out, layout, inputs=combo, recipe=recipes, per_band=per_band,
                                       theme=theme, strict=False, stem=stem)
            written += paths
    _write_lock(job, out, canvas, infos, written)
    return written


def _write_lock(job: Job, out: Path, canvas, infos: dict, written: list[Path]) -> None:
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
