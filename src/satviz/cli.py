"""Command line: `satviz run job.toml --out outputs/`. Also `init` (starter job files), `list` and `placeholders`."""
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="satviz", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

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
