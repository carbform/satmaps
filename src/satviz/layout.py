"""Layout files: the wording on each figure (title, subtitle, how-to-read, notes, credits), as TOML with placeholders.

Placeholders use Python format syntax, e.g. ``{track}``, ``{L.wavelength_cm:.0f}`` or ``{S.noisy_hv_pct:.0f}``.
Acquisition facts and noise statistics are filled in from the data files, never typed into a layout. For every
top-level text value ``{x}`` there is also ``{x_upper}``, and ``{x!u}`` upper-cases any value, including ``{L.rfi!u}``.
Run ``nisar-viz placeholders`` to list everything available.
"""
from __future__ import annotations

import string
import tomllib
from pathlib import Path

from satviz.config import Scene


class _Formatter(string.Formatter):
    """str.format plus a `!u` conversion that upper-cases any value, e.g. ``{L.rfi!u}``."""

    def convert_field(self, value, conversion):
        if conversion == "u":
            return str(value).upper()
        return super().convert_field(value, conversion)


class LayoutError(ValueError):
    """A layout file is missing a key or uses a placeholder that does not exist."""


def load_layout(layouts_dir: str | Path, name: str) -> dict:
    path = Path(layouts_dir) / f"{name}.toml"
    if not path.exists():
        raise LayoutError(f"layout file {path} not found (see layouts/ in the repository)")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    data["_path"] = str(path)
    return data


def default_layout(template: str) -> dict:
    """The wording file that ships with the package for a template (src/satviz/layouts/default_<template>.toml)."""
    path = Path(__file__).parent / "layouts" / f"default_{template}.toml"
    if not path.exists():
        raise LayoutError(f"no built-in layout for template {template!r}")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    data["_path"] = str(path)
    return data


def apply_text(data: dict, text: dict) -> dict:
    """Wording overrides from a job: ``title``/``subtitle``/``date``/``time``/``info_line`` set the header; a dotted key
    (``"credits.lines"``, ``"how_to_read.title"``) sets anything else."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in data.items()}
    for key, value in text.items():
        dotted = key if "." in key else f"header.{key}"
        node = out
        *parents, leaf = dotted.split(".")
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
    return out


def _date(dt) -> str:
    return f"{dt.day} {dt:%b %Y}"


def _dates_label(starts: list) -> str:
    """One date, '24 · 25 Sep 2026' within a month, or full dates joined by ' · ' (the header must not hide a gap)."""
    days = sorted({s.date() for s in starts})
    if len(days) == 1:
        return _date(starts[0])
    if len({(d.year, d.month) for d in days}) == 1:
        return f"{' · '.join(str(d.day) for d in days)} {days[0]:%b %Y}"
    return " · ".join(f"{d.day} {d:%b %Y}" for d in days)


def build_context(scene: Scene, bands: dict, stats_by_band: dict, per_band: bool, extra: dict | None = None) -> dict:
    """`build_context_products` for NISAR working datasets (the older figures pass these plus their own statistics)."""
    from satviz.sensors.nisar_gcov import to_product

    products = {k: to_product(d, stats_by_band[k]) for k, d in bands.items()}
    return build_context_products(scene, products, per_band, extra)


def build_context_products(scene: Scene, products: dict, per_band: bool = True, extra: dict | None = None,
                           strict: bool = True) -> dict:
    """Placeholder values: scene names, facts every product has (dates, resolution, CRS), what the sensors share
    (e.g. NISAR track and frame) and each product's own namespace under its input id (``{L.wavelength_cm}``).

    With ``strict`` the products must agree on everything the sensors call shared (same pass); a before/after template
    passes ``strict=False`` and gets the reference input's values."""
    metas = {k: p.meta for k, p in products.items()}
    order = [k for k in scene.inputs if k in products] or list(products)
    ref_key = order[0]
    ref = products[ref_key]
    if strict:
        for key, p in products.items():
            diff = {k: (ref.shared[k], v) for k, v in p.shared.items() if k in ref.shared and ref.shared[k] != v}
            if diff:
                what = ", ".join(f"{k} {a} vs {b}" for k, (a, b) in diff.items())
                raise LayoutError(f"inputs are not from the same pass: {ref_key} and {key} differ in {what}")
    starts = [m["start"] for m in metas.values()]
    start = min(starts)
    end = max(m["end"] for m in metas.values())
    res = ref.meta["resolution_m"]
    uncal = [m["label"] for m in metas.values() if m.get("calibrated") is False]
    cal = [m["label"] for m in metas.values() if m.get("calibrated") is True]
    by_platform: dict[str, list[str]] = {}
    for m in metas.values():
        by_platform.setdefault(m.get("platform", ""), []).append(m.get("label", ""))
    labels = [f"{plat} {' + '.join(x for x in labs if x)}".strip() for plat, labs in by_platform.items()]
    ctx = {
        "inputs_line": "  ·  ".join(x.upper() for x in labels),  # e.g. "NISAR L-BAND  ·  SENTINEL-2 L2A"
        "platforms": " + ".join(dict.fromkeys(m["platform"] for m in metas.values() if m.get("platform"))),
        "name": scene.name, "reach": scene.reach, "locality": scene.locality, "region": scene.region,
        "callout_caption": scene.callout_caption, "author": scene.author, "website": scene.website,
        "date": _dates_label(list(starts)), "times_utc": " / ".join(dict.fromkeys(f"{s:%H:%M}" for s in starts)),
        "time_utc": f"{start:%H:%M}", "start_utc": f"{start:%H:%M:%S}", "end_utc": f"{end:%H:%M:%S}",
        "posting_m": int(res) if float(res).is_integer() else res, "crs": ref.meta["crs"],
        **ref.shared,
        "stretch_note": "each band stretched on its own" if per_band else "same colours and stretch in both bands",
        "stretch_warning": "Colours are not comparable between bands (own stretch)." if per_band else "",
        # inputs whose calibration is unpopulated; empty when all are calibrated (lines using it can be conditional)
        "uncal_bands": " and ".join(uncal),
        "cal_bands": " and ".join(cal),
    }
    if extra:
        # whole-number floats print as integers ('30 m', not '30.0 m')
        ctx.update({k: int(v) if isinstance(v, float) and v.is_integer() else v for k, v in extra.items()})
    for k, v in list(ctx.items()):
        if isinstance(v, str):
            ctx[f"{k}_upper"] = v.upper()
    for p in products.values():
        if not hasattr(p.facts, "date"):
            p.facts.date = _date(p.meta["start"])
    ctx.update({k: p.facts for k, p in products.items()})
    return ctx


class Layout:
    """A loaded layout file bound to the placeholder values for one render."""

    def __init__(self, data: dict, ctx: dict):
        self.data, self.ctx = data, ctx
        self.path = data.get("_path", "<layout>")

    def raw(self, dotted: str):
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                raise LayoutError(f"{self.path}: missing key [{dotted}]")
            node = node[part]
        return node

    def get(self, dotted: str, default=None):
        try:
            return self.raw(dotted)
        except LayoutError:
            return default

    def render(self, template: str, where: str = "", **extra) -> str:
        ctx = {**self.ctx, **extra}
        try:
            return _Formatter().vformat(template, (), ctx)
        except KeyError as e:
            names = ", ".join(sorted(ctx))
            raise LayoutError(f"{self.path} [{where}]: unknown placeholder {{{e.args[0]}}}. Available: {names}") from None
        except (AttributeError, IndexError, ValueError) as e:
            raise LayoutError(f"{self.path} [{where}]: bad placeholder in {template!r}: {e}") from None

    def text(self, dotted: str, **extra) -> str:
        return self.render(str(self.raw(dotted)), dotted, **extra).strip()

    def lines(self, dotted: str, limit: int | None = None, **extra) -> list[str]:
        """Rendered lines of a list. An entry is a string, or ``{ text = "...", if = "placeholder" }`` which is shown only
        when that placeholder is non-empty (e.g. a calibration warning that disappears once scale factors are populated).
        Lines that render empty are dropped."""
        out = []
        for t in self.raw(dotted):
            if isinstance(t, dict):
                cond = t.get("if")
                if cond and not self.render("{" + cond + "}", dotted, **extra).strip():
                    continue
                t = t["text"]
            out.append(self.render(str(t), dotted, **extra).strip())
        out = [t for t in out if t]
        if limit is not None and len(out) > limit:
            raise LayoutError(f"{self.path} [{dotted}]: {len(out)} lines, at most {limit} fit")
        return out
