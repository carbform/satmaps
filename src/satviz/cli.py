"""Command line: `satviz quick <products…>` for a figure with no setup, `satviz run job.toml` for a job file. Also `inspect`,
`init` (starter job files), `list` and `placeholders`."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


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


# Streamlit looks up its latest version on PyPI at start-up (one launch in ten) and has no setting to stop it. satviz is local
# only, so it starts Streamlit through this line, which turns that check off first.
STREAMLIT_LAUNCH = ("import sys, streamlit.version as v; v.should_show_new_version_notice = lambda: False; "
                    "from streamlit.web.cli import main; sys.exit(main())")


def _app(args) -> int:
    """Start Streamlit on localhost with the app script. Settings go by environment: the script has no command line of its own."""
    import importlib.util
    import os
    import subprocess

    if importlib.util.find_spec("streamlit") is None:
        print('error: the app needs Streamlit: pip install "satviz[app]"', file=sys.stderr)
        return 2
    script = Path(importlib.util.find_spec("satviz.app").origin)  # found, not imported: importing it would run the app

    def absolute(p) -> str:
        return str(Path(p).expanduser().resolve())

    env = dict(os.environ, SATVIZ_DATA_DIR=absolute(args.data_dir or os.environ.get("SATVIZ_DATA_DIR") or "data"),
               SATVIZ_OUT_DIR=absolute(args.out), SATVIZ_CACHE_DIR=absolute(args.cache))
    cmd = [sys.executable, "-c", STREAMLIT_LAUNCH, "run", str(script), "--server.address", "localhost",
           "--server.port", str(args.port), "--browser.gatherUsageStats", "false",
           "--server.headless", str(args.no_browser).lower()]
    return subprocess.call(cmd, env=env)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="satviz", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    qk = sub.add_parser("quick", help="render a figure from product paths: sensor, area, template and pixel size are worked out")
    qk.add_argument("paths", nargs="+", help="products: a NISAR .h5, or an unzipped Sentinel-1/2 .SAFE, EOS-04 or LISS-IV folder")
    qk.add_argument("--quality", choices=("quick", "medium", "publication"), default="quick",
                    help="quick: a small PNG in seconds; medium: finer, still no PDF; publication: full size, with a PDF "
                         "(default: %(default)s)")
    qk.add_argument("--theme", default="minimal", help="neo_retro, minimal, neo_brutal, newspaper or xkcd (default: %(default)s)")
    qk.add_argument("--title", default=None, help="the figure's title")
    qk.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                    help="draw this box (degrees) instead of the overlap of the inputs")
    qk.add_argument("--resolution", type=float, default=None, metavar="M", help="pixel size in metres (default: from --quality)")
    qk.add_argument("--template", choices=("sar", "optical", "sar_optical"), default=None, help="default: from the inputs")
    qk.add_argument("--arrangement", choices=("single", "compare", "grid", "bands"), default=None,
                    help="default: one input single, two compare, three to six grid")
    qk.add_argument("--bands", action="store_true", help="optical: one panel per spectral band (same as --arrangement bands)")
    qk.add_argument("--allow-large", action="store_true",
                    help="draw an automatic area even above 15,000 km2 (a whole frame: slow); the default asks for --bbox")
    qk.add_argument("--allow-different-passes", action="store_true", help="NISAR: lift the same-track-and-frame check")
    qk.add_argument("--out", default="outputs", help="output folder (default: %(default)s)")
    qk.add_argument("--data-dir", default=None)
    qk.add_argument("--cache", default="cache", help="read cache folder (default: %(default)s)")
    qk.add_argument("--no-cache", action="store_true")
    qk.add_argument("--save-job", default=None, metavar="FILE", help="also write the job file that reproduces this figure")

    ap = sub.add_parser("app", help="open the local app in your browser to pick products, preview and download (satviz[app])")
    ap.add_argument("--data-dir", default=None, help="folder with the products (default: $SATVIZ_DATA_DIR, then ./data)")
    ap.add_argument("--out", default="outputs", help="where figures are written (default: %(default)s)")
    ap.add_argument("--cache", default="cache", help="read cache folder (default: %(default)s)")
    ap.add_argument("--port", type=int, default=8501, help="port on localhost (default: %(default)s)")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")

    ins = sub.add_parser("inspect", help="say which sensor reads a product and where it has data, without reading pixels")
    ins.add_argument("paths", nargs="+")

    rn = sub.add_parser("run", help="render the figures of a job file")
    rn.add_argument("job", help="job TOML (see `satviz init`)")
    rn.add_argument("--data-dir", default=None, help="where source paths are looked up (default: $SATVIZ_DATA_DIR, then ./data)")
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
        from satviz.api import inspect
        from satviz.detect import DetectError

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
        from satviz.api import render
        from satviz.area import AreaError
        from satviz.detect import DetectError
        from satviz.job import JobError
        from satviz.layout import LayoutError
        from satviz.sources import SourceError

        try:
            paths = render(args.paths, out=args.out, cache=None if args.no_cache else args.cache, save_job=args.save_job,
                           area=args.bbox, theme=args.theme, quality=args.quality, title=args.title, template=args.template,
                           arrangement=args.arrangement, bands=args.bands, resolution_m=args.resolution,
                           allow_different_passes=args.allow_different_passes, allow_large=args.allow_large,
                           data_dir=args.data_dir)
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
        from satviz.area import AreaError
        from satviz.job import JobError, load_job
        from satviz.layout import LayoutError
        from satviz.run import run_job
        from satviz.sources import SourceError

        try:
            job = load_job(args.job, args.data_dir)
            for path in run_job(job, args.out, None if args.no_cache else args.cache, args.layouts_dir):
                print(path)
        except (JobError, AreaError, SourceError, LayoutError, FileNotFoundError, KeyError, ValueError) as e:
            print(f"error: {e.args[0] if isinstance(e, KeyError) and e.args else e}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "list":
        from satviz.core import TEMPLATES
        from satviz.registry import describe

        for kind, names in describe().items():
            print(f"{kind}: {', '.join(names)}")
        print("\ntemplates:")
        for name in sorted(TEMPLATES):
            print(f"  {name:13} {TEMPLATES[name].summary}")
        return 0

    if args.cmd == "placeholders":
        from types import SimpleNamespace

        from satviz.area import AreaError
        from satviz.job import JobError, load_job
        from satviz.layout import LayoutError
        from satviz.run import placeholders_job
        from satviz.sources import SourceError

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
