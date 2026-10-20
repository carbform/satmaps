"""Job file: one TOML that says where, what data, and which figures. `satviz run job.toml` does the rest.

Sections: ``extends`` (a base file), ``[scene]`` (names and wording defaults, all optional), ``[area]``, ``[[inputs]]``,
``[[zooms]]``, ``[callouts.*]`` and ``[[figures]]``. See docs/architecture.md and the presets (`satviz init`).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from satviz.area import Area
from satviz.config import DATA_DIR_ENV, LEGACY_DATA_DIR_ENV, InputSpec, Scene

TOP_LEVEL = {"extends", "scene", "area", "inputs", "figures", "zooms", "callouts"}
SCENE_KEYS = ("name", "reach", "locality", "region", "callout_caption", "author", "website")
FIGURE_KEYS = {"template", "inputs", "recipes", "theme", "layout", "text", "pairs", "stretch", "name", "allow_different_passes",
               "arrangement"}


class JobError(ValueError):
    """The job file is invalid; the message names the section and the fix."""


@dataclass(frozen=True)
class FigureSpec:
    template: str
    inputs: tuple[str, ...]
    recipes: dict = field(default_factory=dict)  # input id -> recipe name; "default" applies to the rest
    themes: tuple[str, ...] = ("neo_retro",)
    layout: str | None = None  # name or path of a layout file; default: the template's built-in one
    text: dict = field(default_factory=dict)  # wording overrides: title, subtitle, ... or dotted layout keys
    pairs: str | None = None  # "all": one figure per unordered pair of `inputs`
    stretch: str | None = None  # compare: "per-band" or "pooled"
    name: str | None = None  # output filename stem
    arrangement: str | None = None  # single, compare or grid; default: the template's own (optical_sar and sar_vs_sar compare)
    strict: bool = True  # inputs must share a pass (NISAR track/frame); allow_different_passes = true lifts it


@dataclass(frozen=True)
class Job:
    path: Path
    scene: Scene
    area: Area
    inputs: dict[str, InputSpec]
    figures: tuple[FigureSpec, ...]
    zoom_specs: tuple[dict, ...] = ()


def _merge(base: dict, over: dict) -> dict:
    """Tables merge key by key; everything else (including lists of tables) is replaced by the overriding file."""
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def read_toml(path: Path, _seen: tuple = ()) -> dict:
    path = Path(path)
    if path.resolve() in _seen:
        raise JobError(f"{path}: `extends` loops back to itself")
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        raise JobError(f"job file {path} not found") from None
    except tomllib.TOMLDecodeError as e:
        raise JobError(f"{path}: not valid TOML: {e}") from None
    if "extends" in raw:
        base = read_toml(path.parent / raw["extends"], (*_seen, path.resolve()))
        raw = _merge(base, {k: v for k, v in raw.items() if k != "extends"})
    return raw


def load_job(path: str | os.PathLike, data_dir: str | os.PathLike | None = None) -> Job:
    path = Path(path)
    raw = read_toml(path)
    if unknown := set(raw) - TOP_LEVEL:
        raise JobError(f"{path}: unknown section(s) {sorted(unknown)}; allowed: {sorted(TOP_LEVEL)}")
    if "area" not in raw:
        raise JobError(f"{path}: missing [area] (give `center` + `radius_km`, or a `bbox`)")
    area = Area.from_config(raw["area"])

    inputs: dict[str, InputSpec] = {}
    for i, spec in enumerate(raw.get("inputs", []), 1):
        if "id" not in spec or "sensor" not in spec:
            raise JobError(f"{path} [[inputs]] #{i}: needs `id` and `sensor`")
        if spec["id"] in inputs:
            raise JobError(f"{path}: input id {spec['id']!r} appears twice")
        opts = {k: v for k, v in spec.items() if k not in ("id", "sensor", "file")}
        inputs[spec["id"]] = InputSpec(spec["id"], spec["sensor"], spec.get("file", ""), opts)
    if not inputs:
        raise JobError(f"{path}: no [[inputs]]")

    s = raw.get("scene", {})
    if unknown := set(s) - set(SCENE_KEYS):
        raise JobError(f"{path} [scene]: unknown key(s) {sorted(unknown)}; allowed: {list(SCENE_KEYS)}")
    callouts = {k: (float(v["lat"]), float(v["lon"])) for k, v in raw.get("callouts", {}).items()}
    env = os.environ.get(DATA_DIR_ENV) or os.environ.get(LEGACY_DATA_DIR_ENV)
    root = data_dir or env or (Path("data") if Path("data").is_dir() else path.resolve().parent)
    scene = Scene(
        **{k: str(s.get(k, "")) for k in SCENE_KEYS if k != "name"}, name=str(s.get("name") or path.stem),
        zooms=(), callouts=callouts, data_dir=Path(root).expanduser(), inputs=inputs,
    )

    figures = []
    for i, f in enumerate(raw.get("figures") or [_default_figure(list(inputs))], 1):
        figures.append(_figure(path, i, f, inputs))
    return Job(path, scene, area, inputs, tuple(figures), tuple(raw.get("zooms", [])))


def _default_figure(ids: list[str]) -> dict:
    return {"template": "single" if len(ids) == 1 else "compare", "inputs": ids[:2]}


def _figure(path: Path, i: int, f: dict, inputs: dict) -> FigureSpec:
    where = f"{path} [[figures]] #{i}"
    if unknown := set(f) - FIGURE_KEYS:
        raise JobError(f"{where}: unknown key(s) {sorted(unknown)}; allowed: {sorted(FIGURE_KEYS)}")
    if "template" not in f:
        raise JobError(f"{where}: needs `template` (optical, sar, optical_sar, sar_vs_sar; or single, compare, grid)")
    ids = tuple(f.get("inputs") or inputs)
    if missing := [k for k in ids if k not in inputs]:
        raise JobError(f"{where}: unknown input(s) {missing}; the job defines {list(inputs)}")
    themes = f.get("theme", "neo_retro")
    themes = (themes,) if isinstance(themes, str) else tuple(themes)
    if f.get("pairs") not in (None, "all"):
        raise JobError(f"{where}: pairs must be \"all\"")
    if f.get("stretch") not in (None, "per-band", "pooled"):
        raise JobError(f"{where}: stretch must be \"per-band\" or \"pooled\"")
    return FigureSpec(template=f["template"], inputs=ids, recipes=dict(f.get("recipes", {})), themes=themes,
                      layout=f.get("layout"), text=dict(f.get("text", {})), pairs=f.get("pairs"),
                      stretch=f.get("stretch"), name=f.get("name"), arrangement=f.get("arrangement"),
                      strict=not f.get("allow_different_passes", False))
