"""Command line: `satviz render <figure>... --config legacy/configs/brahmaputra.toml --data-dir /path/to/granules`."""
from __future__ import annotations

import argparse
import importlib
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Figure:
    module: str
    inputs: tuple[str, ...]  # input ids (scene [[inputs]]) the figure needs
    layout: str  # legacy/layouts/<layout>.toml
    kwargs: dict = field(default_factory=dict)
    themed: bool = False  # accepts --theme; the clean and publication figures are plain on purpose
    products: bool = False  # template modules take generic Products; the older figure modules take NISAR working datasets


FIGURES = {
    "ls-social": Figure("satviz.arrangements.compare", ("L", "S"), "ls_social", {"inputs": ("L", "S")}, themed=True,
                        products=True),
    "ls-publication": Figure("satviz.legacy.ls_publication", ("L", "S"), "ls_publication"),
    "ls-clean": Figure("satviz.legacy.ls_clean", ("L", "S"), "ls_clean"),
    "sband-publication": Figure("satviz.legacy.sband_publication", ("S",), "sband_publication"),
    "sband-social": Figure("satviz.arrangements.single", ("S",), "sband_social", {"input": "S", "chip_slot": "b"},
                         themed=True, products=True),
    "lband-social": Figure("satviz.arrangements.single", ("L",), "lband_social", {"input": "L", "chip_slot": "a"},
                         themed=True, products=True),
}


def load_products(scene, keys, cache) -> dict:
    """Read each input with the reader of its sensor. Needed inputs are read once, whichever figures use them."""
    from satviz.core import SENSORS
    from satviz.registry import load_builtin

    load_builtin()
    return {k: SENSORS.get_or_raise(scene.inputs[k].sensor).load(scene, k, cache) for k in keys}


def _init(args) -> int:
    from importlib.resources import files

    found = sorted(files("satviz").joinpath("presets").iterdir(), key=lambda p: p.name)
    presets = {p.name.removesuffix(".toml"): p for p in found if p.name.endswith(".toml")}
    if not args.preset:
        for name, p in presets.items():
            print(f"{name:16} {p.read_text().splitlines()[0].lstrip('# ')}")
        return 0
    if args.preset not in presets:
        print(f"error: unknown preset {args.preset!r}; available: {', '.join(presets)}", file=sys.stderr)
        return 2
    dest = Path(args.output or f"{args.preset}.toml")
    if dest.exists() and not args.force:
        print(f"error: {dest} exists; pass --force to overwrite", file=sys.stderr)
        return 2
    dest.write_text(presets[args.preset].read_text())
    print(dest)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="satviz", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render one or more figures")
    r.add_argument("figures", nargs="+", choices=[*FIGURES, "all"], help="figure name(s), or 'all'")
    r.add_argument("--config", default="legacy/configs/brahmaputra.toml", help="scene TOML (default: %(default)s)")
    r.add_argument("--data-dir", default=None, help="folder with the .h5 granules (default: $SATVIZ_DATA_DIR, then ./data)")
    r.add_argument("--layouts-dir", default="legacy/layouts", help="folder with the figure wording files (default: %(default)s)")
    r.add_argument("--out", default="outputs", help="output folder (default: %(default)s)")
    r.add_argument("--cache", default="cache", help="ROI cache folder (default: %(default)s)")
    r.add_argument("--no-cache", action="store_true", help="always read the HDF5 files")
    r.add_argument("--theme", nargs="+", default=["neo_retro"], metavar="THEME",
                   help="look of the social graphics: one or more themes, or 'all' (default: neo_retro; see `satviz list`)")
    r.add_argument("--pooled-stretch", action="store_true", help="ls-social: pooled colour stretch (overrides the layout)")
    r.add_argument("-v", "--verbose", action="store_true")

    rn = sub.add_parser("run", help="render the figures of a job file")
    rn.add_argument("job", help="job TOML (see `satviz init`)")
    rn.add_argument("--data-dir", default=None, help="where source paths are looked up (default: $SATVIZ_DATA_DIR, then ./data)")
    rn.add_argument("--out", default="outputs", help="output folder (default: %(default)s)")
    rn.add_argument("--cache", default="cache", help="read cache folder (default: %(default)s)")
    rn.add_argument("--no-cache", action="store_true")
    rn.add_argument("--layouts-dir", default="legacy/layouts",
                    help="folder for layouts named without a path (default: %(default)s)")
    rn.add_argument("-v", "--verbose", action="store_true")

    se = sub.add_parser("search", help="list the catalogue scenes a job would use, with cloud cover in your area")
    se.add_argument("job")
    se.add_argument("--data-dir", default=None)
    se.add_argument("--cache", default="cache")
    se.add_argument("--no-cache", action="store_true")

    ini = sub.add_parser("init", help="write a starter job file for a preset")
    ini.add_argument("preset", nargs="?", help="preset name; omit to list them")
    ini.add_argument("-o", "--output", default=None, help="file to write (default: <preset>.toml)")
    ini.add_argument("--force", action="store_true", help="overwrite an existing file")

    sub.add_parser("list", help="list the registered sensors, recipes, themes and figures")

    ph = sub.add_parser("placeholders", help="list the {placeholders} available in layout files, with their values")
    ph.add_argument("--config", default="legacy/configs/brahmaputra.toml")
    ph.add_argument("--data-dir", default=None)
    ph.add_argument("--cache", default="cache")
    ph.add_argument("--no-cache", action="store_true")

    s = sub.add_parser("stats", help="print noise and backscatter statistics for each band")
    s.add_argument("--config", default="legacy/configs/brahmaputra.toml")
    s.add_argument("--data-dir", default=None)
    s.add_argument("--cache", default="cache")
    s.add_argument("--no-cache", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING, format="%(message)s")
    import matplotlib

    matplotlib.use("Agg")  # headless; set here so importing the library never changes the backend
    if args.cmd == "init":
        return _init(args)

    if args.cmd == "search":
        from satviz.area import AreaError
        from satviz.job import JobError, load_job
        from satviz.run import search_job
        from satviz.sources import SourceError
        from satviz.stac import StacError

        try:
            rows = search_job(load_job(args.job, args.data_dir), None if args.no_cache else args.cache)
        except (JobError, AreaError, SourceError, StacError, FileNotFoundError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        for key, found in rows.items():
            print(f"{key}:")
            for r in found:
                mark = "<- would be used" if r["chosen"] else ("" if r["ok"] else "(too cloudy or too little coverage)")
                print(f"  {r['date']}  cloud {r['cloud_pct']:4.0f}%  coverage {r['coverage_pct']:4.0f}%  "
                      f"{', '.join(r['scenes'])}  {mark}")
        return 0

    if args.cmd == "run":
        from satviz.area import AreaError
        from satviz.job import JobError, load_job
        from satviz.layout import LayoutError
        from satviz.run import run_job
        from satviz.sources import SourceError
        from satviz.stac import StacError

        try:
            job = load_job(args.job, args.data_dir)
            for path in run_job(job, args.out, None if args.no_cache else args.cache, args.layouts_dir):
                print(path)
        except (JobError, AreaError, SourceError, StacError, LayoutError, FileNotFoundError, KeyError, ValueError) as e:
            print(f"error: {e.args[0] if isinstance(e, KeyError) and e.args else e}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "list":
        from satviz.registry import describe

        for kind, names in {**describe(), "figures": sorted(FIGURES)}.items():
            print(f"{kind}: {', '.join(names)}")
        return 0

    from satviz.config import load_scene
    scene = load_scene(args.config, args.data_dir)
    cache = None if args.no_cache else args.cache

    if args.cmd == "stats":
        import json

        from satviz.sensors.nisar_gcov.io import load_roi
        from satviz.sensors.nisar_gcov.processing import stats

        for key in scene.bands:
            print(key, json.dumps(stats(load_roi(scene, key, cache)), indent=1))
        return 0

    if args.cmd == "placeholders":
        from types import SimpleNamespace

        from satviz.layout import build_context_products

        extra = {"k": 3, "block_m": 30, "both_pct": 0}  # figure-specific values, shown with example numbers
        ctx = build_context_products(scene, load_products(scene, list(scene.inputs), cache), per_band=True, extra=extra)
        for key, val in ctx.items():
            if isinstance(val, SimpleNamespace):
                for attr, v in vars(val).items():
                    print(f"{{{key}.{attr}}} = {v!r}")
            elif not key.endswith("_upper"):
                print(f"{{{key}}} = {val!r}")
        return 0

    from satviz.core import THEMES
    from satviz.layout import load_layout
    from satviz.registry import load_builtin

    load_builtin()
    themes = sorted(THEMES) if "all" in args.theme else args.theme
    for th in themes:
        THEMES.get_or_raise(th)
    names = list(FIGURES) if "all" in args.figures else args.figures
    mods = {n: importlib.import_module(FIGURES[n].module) for n in names}
    need = sorted({b for n in names for b in FIGURES[n].inputs})
    products = load_products(scene, need, cache)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for n in names:
        kw = dict(FIGURES[n].kwargs)
        if n == "ls-social" and args.pooled_stretch:
            kw["per_band"] = False
        layout = load_layout(args.layouts_dir, FIGURES[n].layout)
        for theme in themes if FIGURES[n].themed else [None]:
            if theme:
                kw["theme"] = theme
            given = {k: products[k] for k in FIGURES[n].inputs}
            if not FIGURES[n].products:  # older figure modules work on the NISAR working datasets
                given = {k: p.native for k, p in given.items()}
            for path in mods[n].render(scene, given, out, layout, **kw):
                print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
