"""Job file: one TOML that says where, what data, and which figures. `satmaps run job.toml` does the rest.

Sections: ``extends`` (a base file), ``quality`` ("quick" or "publication"), ``[scene]`` (names and wording defaults, all
optional), ``[area]`` (optional: left out, it is the overlap of the inputs), ``[[inputs]]`` (``sensor`` optional: found from
the path), ``[[zooms]]``, ``[callouts.*]`` and ``[[figures]]``. See docs/architecture.md and the presets (`satmaps init`).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from satmaps.area import Area
from satmaps.config import DATA_DIR_ENV, InputSpec, Scene
from satmaps.quality import DEFAULT, Profile, profile_of

TOP_LEVEL = {"extends", "scene", "area", "inputs", "figures", "zooms", "callouts", "quality"}
AUTO_AREA_KEYS = {"resolution_m", "target_px"}  # an [area] with no center or bbox: the inputs' overlap (`satmaps.autoarea`)
SCENE_KEYS = ("name", "reach", "locality", "region", "callout_caption", "author", "website")
FIGURE_KEYS = {"template", "inputs", "recipes", "theme", "layout", "text", "stretch", "name", "same_pass",
               "allow_different_passes", "arrangement", "composites", "grid", "north", "scalebar"}


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
    stretch: str | None = None  # compare: "per-band" or "pooled"
    name: str | None = None  # output filename stem
    composites: tuple[str, ...] = ()  # optical, bands: recipes added after the band panels
    arrangement: str | None = None  # single, compare, grid (or bands, optical only); default: single for one input, else compare
    grid: bool = False  # lat/lon grid with labels on every panel
    north: bool = False  # north arrow (true north) on the first panel
    scalebar: bool = True  # scale bar on the first panel
    strict: bool = False  # same_pass = true: inputs must share a pass (NISAR track/frame); else any products go together


@dataclass(frozen=True)
class Job:
    path: Path
    scene: Scene
    area: Area | None  # None: worked out from the inputs' footprints when the job runs (`satmaps.run.resolve_area`)
    inputs: dict[str, InputSpec]
    figures: tuple[FigureSpec, ...]
    zoom_specs: tuple[dict, ...] = ()
    auto_area: dict = field(default_factory=dict)  # resolution_m / target_px for an automatic area
    quality: Profile = DEFAULT  # quick or publication: canvas size, dpi, PDF


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
    return job_from_dict(read_toml(path), path, data_dir)


def job_from_dict(raw: dict, path: Path, data_dir: str | os.PathLike | None = None) -> Job:
    """A `Job` from the parsed tables of a job file (or the same tables built in code, as `satmaps.render` does)."""
    if unknown := set(raw) - TOP_LEVEL:
        raise JobError(f"{path}: unknown section(s) {sorted(unknown)}; allowed: {sorted(TOP_LEVEL)}")
    try:
        quality = profile_of(raw.get("quality"))
    except ValueError as e:
        raise JobError(f"{path}: {e}") from None
    cfg = raw.get("area", {})
    if {"center", "bbox"} & set(cfg):
        area, auto = Area.from_config(cfg), {}
    else:  # no place named: the overlap of the inputs
        if unknown := set(cfg) - AUTO_AREA_KEYS:
            raise JobError(f"{path} [area]: with no `center` or `bbox` the area is automatic; unknown key(s) {sorted(unknown)}, "
                           f"allowed: {sorted(AUTO_AREA_KEYS)}")
        area, auto = None, dict(cfg)

    s = raw.get("scene", {})
    env = os.environ.get(DATA_DIR_ENV)
    root = Path(data_dir or env or (Path("data") if Path("data").is_dir() else path.resolve().parent)).expanduser()
    inputs: dict[str, InputSpec] = {}
    for i, spec in enumerate(raw.get("inputs", []), 1):
        if "id" not in spec:
            raise JobError(f"{path} [[inputs]] #{i}: needs an `id`")
        if spec["id"] in inputs:
            raise JobError(f"{path}: input id {spec['id']!r} appears twice")
        opts = {k: v for k, v in spec.items() if k not in ("id", "sensor", "file")}
        sensor = spec.get("sensor") or _detect_sensor(path, i, InputSpec(spec["id"], "", spec.get("file", ""), opts), root)
        inputs[spec["id"]] = InputSpec(spec["id"], sensor, spec.get("file", ""), opts)
    if not inputs:
        raise JobError(f"{path}: no [[inputs]]")

    if unknown := set(s) - set(SCENE_KEYS):
        raise JobError(f"{path} [scene]: unknown key(s) {sorted(unknown)}; allowed: {list(SCENE_KEYS)}")
    callouts = {k: (float(v["lat"]), float(v["lon"])) for k, v in raw.get("callouts", {}).items()}
    scene = Scene(
        **{k: str(s.get(k, "")) for k in SCENE_KEYS if k != "name"}, name=str(s["name"]) if "name" in s else path.stem,
        zooms=(), callouts=callouts, data_dir=root, inputs=inputs,
    )

    figures = []
    for i, f in enumerate(raw.get("figures") or [_default_figure(inputs)], 1):
        figures.append(_figure(path, i, f, inputs))
    return Job(path, scene, area, inputs, tuple(figures), tuple(raw.get("zooms", [])), auto, quality)


def _detect_sensor(path: Path, i: int, spec: InputSpec, root: Path) -> str:
    """The sensor of an input that names none: found by looking at its source path (see `satmaps.detect`)."""
    from satmaps.detect import DetectError, detect
    from satmaps.sources import SourceError, resolve_one_file

    try:
        return detect(resolve_one_file(spec, root))
    except (DetectError, SourceError, FileNotFoundError) as e:
        raise JobError(f"{path} [[inputs]] #{i} ({spec.key!r}): no `sensor`, and none found from the source: {e}") from None


def _default_figure(inputs: dict) -> dict:
    """With no [[figures]]: the template that fits the kinds of the inputs, over all of them."""
    from satmaps.registry import load_builtin
    from satmaps.templates.base import input_kind

    load_builtin()
    kinds = {input_kind(spec) for spec in inputs.values()}
    return {"template": "sar_optical" if len(kinds) > 1 else next(iter(kinds)), "inputs": list(inputs)}


def _figure(path: Path, i: int, f: dict, inputs: dict) -> FigureSpec:
    where = f"{path} [[figures]] #{i}"
    if unknown := set(f) - FIGURE_KEYS:
        raise JobError(f"{where}: unknown key(s) {sorted(unknown)}; allowed: {sorted(FIGURE_KEYS)}")
    if "template" not in f:
        raise JobError(f"{where}: needs `template` "
                       "(sar, optical or sar_optical)")
    ids = tuple(f.get("inputs") or inputs)
    if missing := [k for k in ids if k not in inputs]:
        raise JobError(f"{where}: unknown input(s) {missing}; the job defines {list(inputs)}")
    themes = f.get("theme", "neo_retro")
    themes = (themes,) if isinstance(themes, str) else tuple(themes)
    if f.get("stretch") not in (None, "per-band", "pooled"):
        raise JobError(f"{where}: stretch must be \"per-band\" or \"pooled\"")
    return FigureSpec(template=f["template"], inputs=ids, recipes=dict(f.get("recipes", {})), themes=themes,
                      layout=f.get("layout"), text=dict(f.get("text", {})),
                      stretch=f.get("stretch"), name=f.get("name"), arrangement=f.get("arrangement"),
                      composites=tuple(f.get("composites", ())),
                      grid=bool(f.get("grid", False)), north=bool(f.get("north", False)), scalebar=bool(f.get("scalebar", True)),
                      strict=bool(f.get("same_pass", False)))  # allow_different_passes is the old, now default, behaviour
