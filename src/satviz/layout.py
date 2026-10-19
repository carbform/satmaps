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
from satviz.sensors.nisar_gcov.facts import band_facts


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


def _date(dt) -> str:
    return f"{dt.day} {dt:%b %Y}"


def build_context(scene: Scene, bands: dict, stats_by_band: dict, per_band: bool, extra: dict | None = None) -> dict:
    """Placeholder values: scene names, file metadata (acquisition, pass, frequency, flags) and noise statistics."""
    metas = {k: d["meta"] for k, d in bands.items()}
    ref = metas.get("S") or next(iter(metas.values()))
    for key, m in metas.items():
        if (m.track, m.frame, m.pass_direction) != (ref.track, ref.frame, ref.pass_direction):
            raise LayoutError(
                f"bands are not from the same pass: {ref.key} is track {ref.track} frame {ref.frame} {ref.pass_direction}, "
                f"{key} is track {m.track} frame {m.frame} {m.pass_direction}"
            )
    start = min(m.start for m in metas.values())
    end = max(m.end for m in metas.values())
    band_ns = {key: band_facts(m, stats_by_band[key]) for key, m in metas.items()}
    uncal = [f"{k}-band" for k, m in metas.items() if not m.calibrated]
    cal = [f"{k}-band" for k, m in metas.items() if m.calibrated]
    ctx = {
        "name": scene.name, "reach": scene.reach, "locality": scene.locality, "region": scene.region,
        "callout_caption": scene.callout_caption, "author": scene.author, "website": scene.website,
        "date": _date(start), "time_utc": f"{start:%H:%M}", "start_utc": f"{start:%H:%M:%S}", "end_utc": f"{end:%H:%M:%S}",
        "track": ref.track, "frame": ref.frame, "pass_direction": ref.pass_direction, "look_direction": ref.look_direction,
        "posting_m": int(ref.posting_m) if float(ref.posting_m).is_integer() else ref.posting_m, "crs": ref.crs,
        "polarisations": ref.polarisations,
        "stretch_note": "each band stretched on its own" if per_band else "same colours and stretch in both bands",
        "stretch_warning": "Colours are not comparable between bands (own stretch)." if per_band else "",
        # bands whose scale factors are zero/unpopulated; empty when all are calibrated (lines using it can be conditional)
        "uncal_bands": " and ".join(uncal),
        "cal_bands": " and ".join(cal),
    }
    if extra:
        # whole-number floats print as integers ('30 m', not '30.0 m')
        ctx.update({k: int(v) if isinstance(v, float) and v.is_integer() else v for k, v in extra.items()})
    for k, v in list(ctx.items()):
        if isinstance(v, str):
            ctx[f"{k}_upper"] = v.upper()
    ctx.update(band_ns)
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
