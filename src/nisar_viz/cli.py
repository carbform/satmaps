"""Command line: `nisar-viz render <figure>... --config configs/brahmaputra.toml --data-dir /path/to/granules`."""
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
    bands: tuple[str, ...]  # granules the figure needs
    layout: str  # layouts/<layout>.toml
    kwargs: dict = field(default_factory=dict)


FIGURES = {
    "ls-social": Figure("nisar_viz.figures.ls_social", ("L", "S"), "ls_social"),
    "ls-publication": Figure("nisar_viz.figures.ls_publication", ("L", "S"), "ls_publication"),
    "ls-clean": Figure("nisar_viz.figures.ls_clean", ("L", "S"), "ls_clean"),
    "sband-publication": Figure("nisar_viz.figures.sband_publication", ("S",), "sband_publication"),
    "sband-social": Figure("nisar_viz.figures.band_social", ("S",), "sband_social", {"band": "S"}),
    "lband-social": Figure("nisar_viz.figures.band_social", ("L",), "lband_social", {"band": "L"}),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nisar-viz", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render one or more figures")
    r.add_argument("figures", nargs="+", choices=[*FIGURES, "all"], help="figure name(s), or 'all'")
    r.add_argument("--config", default="configs/brahmaputra.toml", help="scene TOML (default: %(default)s)")
    r.add_argument("--data-dir", default=None, help="folder with the .h5 granules (default: $NISAR_DATA_DIR, then cwd)")
    r.add_argument("--layouts-dir", default="layouts", help="folder with the figure wording files (default: %(default)s)")
    r.add_argument("--out", default="outputs", help="output folder (default: %(default)s)")
    r.add_argument("--cache", default="cache", help="ROI cache folder (default: %(default)s)")
    r.add_argument("--no-cache", action="store_true", help="always read the HDF5 files")
    r.add_argument("--pooled-stretch", action="store_true", help="ls-social: pooled colour stretch (overrides the layout)")
    r.add_argument("-v", "--verbose", action="store_true")

    ph = sub.add_parser("placeholders", help="list the {placeholders} available in layout files, with their values")
    ph.add_argument("--config", default="configs/brahmaputra.toml")
    ph.add_argument("--data-dir", default=None)
    ph.add_argument("--cache", default="cache")
    ph.add_argument("--no-cache", action="store_true")

    s = sub.add_parser("stats", help="print noise and backscatter statistics for each band")
    s.add_argument("--config", default="configs/brahmaputra.toml")
    s.add_argument("--data-dir", default=None)
    s.add_argument("--cache", default="cache")
    s.add_argument("--no-cache", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING, format="%(message)s")
    import matplotlib

    matplotlib.use("Agg")  # headless; set here so importing the library never changes the backend
    from nisar_viz.config import load_scene
    from nisar_viz.io import load_roi

    scene = load_scene(args.config, args.data_dir)
    cache = None if args.no_cache else args.cache

    if args.cmd == "stats":
        import json

        from nisar_viz.processing import stats

        for key in scene.bands:
            print(key, json.dumps(stats(load_roi(scene, key, cache)), indent=1))
        return 0

    if args.cmd == "placeholders":
        from types import SimpleNamespace

        from nisar_viz.layout import build_context
        from nisar_viz.processing import stats

        bands = {key: load_roi(scene, key, cache) for key in scene.bands}
        extra = {"k": 3, "block_m": 30, "both_pct": 0}  # figure-specific values, shown with example numbers
        ctx = build_context(scene, bands, {k: stats(d) for k, d in bands.items()}, per_band=True, extra=extra)
        for key, val in ctx.items():
            if isinstance(val, SimpleNamespace):
                for attr, v in vars(val).items():
                    print(f"{{{key}.{attr}}} = {v!r}")
            elif not key.endswith("_upper"):
                print(f"{{{key}}} = {val!r}")
        return 0

    from nisar_viz.layout import load_layout

    names = list(FIGURES) if "all" in args.figures else args.figures
    mods = {n: importlib.import_module(FIGURES[n].module) for n in names}
    need = sorted({b for n in names for b in FIGURES[n].bands})
    bands = {b: load_roi(scene, b, cache) for b in need}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for n in names:
        kw = dict(FIGURES[n].kwargs)
        if n == "ls-social" and args.pooled_stretch:
            kw["per_band"] = False
        layout = load_layout(args.layouts_dir, FIGURES[n].layout)
        for path in mods[n].render(scene, bands, out, layout, **kw):
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
