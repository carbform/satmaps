"""Command line: `satmaps quick <products…>` for a figure with no setup, `satmaps run job.toml` for a job file. Also `inspect`,
`init` (starter job files), `list` and `placeholders`."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _init(args) -> int:
    from importlib.resources import files

    found = sorted(files("satmaps").joinpath("presets").iterdir(), key=lambda p: p.name)
    presets = {p.name.removesuffix(".toml"): p for p in found if p.name.endswith(".toml")}
    if not args.preset:
        for name, p in presets.items():
            print(f"{name:16} {p.read_text(encoding='utf-8').splitlines()[0].lstrip('# ')}")
        return 0
    if args.preset not in presets:
        print(f"error: unknown preset {args.preset!r}; available: {', '.join(presets)}", file=sys.stderr)
        return 2
    dest = Path(args.output or f"{args.preset}.toml")
    if dest.exists() and not args.force:
        print(f"error: {dest} exists; pass --force to overwrite", file=sys.stderr)
        return 2
    dest.write_text(presets[args.preset].read_text(encoding="utf-8"), encoding="utf-8")
    print(dest)
    return 0


# Streamlit looks up its latest version on PyPI at start-up (one launch in ten) and has no setting to stop it. satmaps is local
# only, so it starts Streamlit through this line, which turns that check off first.
STREAMLIT_LAUNCH = ("import sys, streamlit.version as v; v.should_show_new_version_notice = lambda: False; "
                    "from streamlit.web.cli import main; sys.exit(main())")


def _zoom(text: str) -> dict:
    """`--zoom LAT,LON,KM` (a square) or `LAT,LON,W_KM,H_KM`, with an optional `=NAME`, as a job-file zoom table."""
    spec, _, name = text.partition("=")
    try:
        v = [float(x) for x in spec.split(",")]
    except ValueError:
        v = []
    if len(v) not in (3, 4) or min(v[2:]) <= 0:
        raise ValueError(f"--zoom {text!r}: give LAT,LON,KM or LAT,LON,W_KM,H_KM, then =NAME if you like")
    return {"center": v[:2], "size_km": v[2:] * 2 if len(v) == 3 else v[2:], **({"name": name.strip()} if name.strip() else {})}


def _app(args) -> int:
    """Start Streamlit on localhost with the app script. Settings go by environment: the script has no command line of its own."""
    import importlib.util
    import os
    import subprocess

    if importlib.util.find_spec("streamlit") is None:
        print('error: the app needs Streamlit: pip install "satmaps[app]"', file=sys.stderr)
        return 2
    script = Path(importlib.util.find_spec("satmaps.app").origin)  # found, not imported: importing it would run the app

    def absolute(p) -> str:
        return str(Path(p).expanduser().resolve())

    env = dict(os.environ, SATMAPS_DATA_DIR=absolute(args.data_dir or os.environ.get("SATMAPS_DATA_DIR") or "data"),
               SATMAPS_OUT_DIR=absolute(args.out), SATMAPS_CACHE_DIR=absolute(args.cache))
    cmd = [sys.executable, "-c", STREAMLIT_LAUNCH, "run", str(script), "--server.address", "localhost",
           "--server.port", str(args.port), "--browser.gatherUsageStats", "false",
           "--server.headless", str(args.no_browser).lower(),
           "--theme.base", "light", "--theme.primaryColor", "#3d82cc", "--theme.backgroundColor", "#ffffff",
           "--theme.secondaryBackgroundColor", "#f8f9fa", "--theme.textColor", "#2c3e50", "--theme.font", "monospace"]
    return subprocess.call(cmd, env=env)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="satmaps", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    qk = sub.add_parser("quick", help="render a figure from product paths: sensor, area, template and pixel size are worked out")
    qk.add_argument("paths", nargs="+", help="products: a NISAR .h5, or an unzipped Sentinel-1/2 .SAFE, EOS-04 or LISS-IV folder")
    qk.add_argument("--quality", choices=("quick", "medium", "publication"), default="quick",
                    help="quick: a small PNG in seconds; medium: finer, still no PDF; publication: full size, with a PDF "
                         "(default: %(default)s)")
    qk.add_argument("--theme", default="minimal", help="neo_retro, minimal, neo_brutal, newspaper or xkcd (default: %(default)s)")
    qk.add_argument("--title", default=None, help="the figure's title")
    qk.add_argument("--subtitle", default=None, help="the line under the title")
    qk.add_argument("--place", default=None, help="the place, e.g. 'Dibrugarh, Assam' (the default subtitle when there is none)")
    qk.add_argument("--author", default=None, help="your name, for the credit line")
    qk.add_argument("--website", default=None, help="your website, for the credit line")
    qk.add_argument("--credit", default=None, help="one extra credit line (the data credits are always added as well)")
    qk.add_argument("--grid", action="store_true", help="draw a lat/lon grid with its labels on every panel")
    qk.add_argument("--north", action="store_true", help="draw a north arrow")
    qk.add_argument("--no-scale", action="store_true", help="leave the scale bar out")
    qk.add_argument("--zoom", action="append", default=[], metavar="LAT,LON,KM[=NAME]",
                    help="a zoom side panel (one product only) centred here, KM wide and high (or LAT,LON,W_KM,H_KM), "
                         "named if you add =NAME; up to three, repeat the flag")
    qk.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                    help="draw this box (degrees) instead of the overlap of the inputs")
    qk.add_argument("--resolution", type=float, default=None, metavar="M", help="pixel size in metres (default: from --quality)")
    qk.add_argument("--template", choices=("sar", "optical", "sar_optical"), default=None, help="default: from the inputs")
    qk.add_argument("--arrangement", choices=("single", "compare", "grid", "bands"), default=None,
                    help="default: one input single, two compare")
    qk.add_argument("--bands", action="store_true", help="optical: one panel per spectral band (same as --arrangement bands)")
    qk.add_argument("--sar-fcc", metavar="R,G,B", default=None,
                    help="SAR false-colour composite: three of co, cross, ratio for red, green, blue (default: co,cross,ratio)")
    qk.add_argument("--optical-fcc", metavar="R,G,B", default=None,
                    help="optical false-colour composite: three band names, e.g. nir,red,green or B12,B08,B03")
    qk.add_argument("--allow-large", action="store_true",
                    help="draw an automatic area even above 15,000 km2 (a whole frame: slow); the default asks for --bbox")
    qk.add_argument("--out", default="outputs", help="output folder (default: %(default)s)")
    qk.add_argument("--data-dir", default=None)
    qk.add_argument("--cache", default="cache", help="read cache folder (default: %(default)s)")
    qk.add_argument("--no-cache", action="store_true")
    qk.add_argument("--save-job", default=None, metavar="FILE", help="also write the job file that reproduces this figure")

    ap = sub.add_parser("app", help="open the local app in your browser to pick products, preview and download (satmaps[app])")
    ap.add_argument("--data-dir", default=None, help="folder with the products (default: $SATMAPS_DATA_DIR, then ./data)")
    ap.add_argument("--out", default="outputs", help="where figures are written (default: %(default)s)")
    ap.add_argument("--cache", default="cache", help="read cache folder (default: %(default)s)")
    ap.add_argument("--port", type=int, default=8501, help="port on localhost (default: %(default)s)")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")

    ins = sub.add_parser("inspect", help="say which sensor reads a product and where it has data, without reading pixels")
    ins.add_argument("paths", nargs="+")

    rn = sub.add_parser("run", help="render the figures of a job file")
    rn.add_argument("job", help="job TOML (see `satmaps init`)")
    rn.add_argument("--data-dir", default=None, help="where source paths are looked up (default: $SATMAPS_DATA_DIR, then ./data)")
    rn.add_argument("--out", default="outputs", help="output folder (default: %(default)s)")
    rn.add_argument("--cache", default="cache", help="read cache folder (default: %(default)s)")
    rn.add_argument("--no-cache", action="store_true")
    rn.add_argument("--layouts-dir", default="layouts",
                    help="folder for layouts named without a path (default: %(default)s)")
    rn.add_argument("-v", "--verbose", action="store_true")

    ini = sub.add_parser("init", help="write a starter job file for a preset")
    ini.add_argument("preset", nargs="?", help="preset name; omit to list them")
    ini.add_argument("-o", "--output", default=None, help="file to write (default: <preset>.toml)")
    ini.add_argument("--force", action="store_true", help="overwrite an existing file")

    sub.add_parser("list", help="list the registered sensors, recipes, themes and templates")

    ph = sub.add_parser("placeholders", help="list the {placeholders} a wording file of this job can use, with their values")
    ph.add_argument("job")
    ph.add_argument("--data-dir", default=None)
    ph.add_argument("--cache", default="cache")
    ph.add_argument("--no-cache", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING, format="%(message)s")
    import matplotlib

    matplotlib.use("Agg")  # headless; set here so importing the library never changes the backend
    if args.cmd == "init":
        return _init(args)

    if args.cmd == "app":
        return _app(args)

    if args.cmd == "inspect":
        from satmaps.api import inspect
        from satmaps.detect import DetectError

        status = 0
        for path in args.paths:
            try:
                info = inspect(path)
            except (DetectError, ValueError, FileNotFoundError, ImportError) as e:
                print(f"error: {e}", file=sys.stderr)
                status = 2
                continue
            box = "unknown" if info["bbox"] is None else "W {:.3f}  S {:.3f}  E {:.3f}  N {:.3f}".format(*info["bbox"])
            print(f"{Path(path).name}\n  {info['sensor']} ({info['kind']}), {info['resolution_m']:g} m pixels, "
                  f"EPSG:{info['epsg']}")
            print(f"  {box}")
        return status

    if args.cmd == "quick":
        from satmaps.api import render
        from satmaps.area import AreaError
        from satmaps.detect import DetectError
        from satmaps.job import JobError
        from satmaps.layout import LayoutError
        from satmaps.sources import SourceError

        channels = {k: tuple(v.split(",")) for k, v in (("sar", args.sar_fcc), ("optical", args.optical_fcc)) if v}
        try:
            zooms = [_zoom(z) for z in args.zoom]
            paths = render(args.paths, out=args.out, cache=None if args.no_cache else args.cache,
                           save_job=args.save_job, area=args.bbox, theme=args.theme, quality=args.quality, title=args.title,
                           template=args.template,
                           arrangement=args.arrangement, bands=args.bands, resolution_m=args.resolution,
                           allow_large=args.allow_large, channels=channels,
                           data_dir=args.data_dir, subtitle=args.subtitle, place=args.place, author=args.author,
                           website=args.website, credits=args.credit, grid=args.grid, north=args.north,
                           scalebar=not args.no_scale, zooms=zooms)
        except (DetectError, JobError, AreaError, SourceError, LayoutError, FileNotFoundError, KeyError, ValueError,
                ImportError) as e:
            print(f"error: {e.args[0] if isinstance(e, KeyError) and e.args else e}", file=sys.stderr)
            return 2
        for path in paths:
            print(path)
            if path.with_suffix(".pdf").exists():
                print(path.with_suffix(".pdf"))
        return 0

    if args.cmd == "run":
        from satmaps.area import AreaError
        from satmaps.job import JobError, load_job
        from satmaps.layout import LayoutError
        from satmaps.run import run_job
        from satmaps.sources import SourceError

        try:
            job = load_job(args.job, args.data_dir)
            for path in run_job(job, args.out, None if args.no_cache else args.cache, args.layouts_dir):
                print(path)
        except (JobError, AreaError, SourceError, LayoutError, FileNotFoundError, KeyError, ValueError) as e:
            print(f"error: {e.args[0] if isinstance(e, KeyError) and e.args else e}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "list":
        from satmaps.core import TEMPLATES
        from satmaps.registry import describe

        for kind, names in describe().items():
            print(f"{kind}: {', '.join(names)}")
        print("\ntemplates:")
        for name in sorted(TEMPLATES):
            print(f"  {name:13} {TEMPLATES[name].summary}")
        return 0

    if args.cmd == "placeholders":
        from types import SimpleNamespace

        from satmaps.area import AreaError
        from satmaps.job import JobError, load_job
        from satmaps.layout import LayoutError
        from satmaps.run import placeholders_job
        from satmaps.sources import SourceError

        try:
            ctx = placeholders_job(load_job(args.job, args.data_dir), None if args.no_cache else args.cache)
        except (JobError, AreaError, SourceError, LayoutError, FileNotFoundError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        for key, val in ctx.items():
            if isinstance(val, SimpleNamespace):
                for attr, v in vars(val).items():
                    print(f"{{{key}.{attr}}} = {v!r}")
            elif not key.endswith("_upper"):
                print(f"{{{key}}} = {val!r}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
