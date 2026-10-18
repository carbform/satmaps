"""Command line: `nisar-viz render <figure>... --config configs/brahmaputra.toml --data-dir /path/to/granules`."""
from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

FIGURES = {
    "ls-social": ("nisar_viz.figures.ls_social", ("L", "S")),
    "ls-publication": ("nisar_viz.figures.ls_publication", ("L", "S")),
    "ls-clean": ("nisar_viz.figures.ls_clean", ("L", "S")),
    "sband-publication": ("nisar_viz.figures.sband_publication", ("S",)),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nisar-viz", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render one or more figures")
    r.add_argument("figures", nargs="+", choices=[*FIGURES, "all"], help="figure name(s), or 'all'")
    r.add_argument("--config", default="configs/brahmaputra.toml", help="scene TOML (default: %(default)s)")
    r.add_argument("--data-dir", default=None, help="folder with the .h5 granules (default: $NISAR_DATA_DIR, then cwd)")
    r.add_argument("--out", default="outputs", help="output folder (default: %(default)s)")
    r.add_argument("--cache", default="cache", help="ROI cache folder (default: %(default)s)")
    r.add_argument("--no-cache", action="store_true", help="always read the HDF5 files")
    r.add_argument("--pooled-stretch", action="store_true", help="ls-social: use one colour stretch pooled over both bands")
    r.add_argument("-v", "--verbose", action="store_true")

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

    names = list(FIGURES) if "all" in args.figures else args.figures
    mods = {n: importlib.import_module(FIGURES[n][0]) for n in names}
    need = sorted({b for n in names for b in FIGURES[n][1]})
    bands = {b: load_roi(scene, b, cache) for b in need}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for n in names:
        kw = {"per_band": not args.pooled_stretch} if n == "ls-social" else {}
        for path in mods[n].render(scene, bands, out, **kw):
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
