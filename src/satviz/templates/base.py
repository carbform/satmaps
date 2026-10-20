"""What a template decides, and the base class the scenario templates share.

A **template** is a content scenario: which kinds of products it takes (optical, SAR, both), how they relate, which recipe
each gets, which page arrangement shows them and what the figure must say about the combination. It does not draw. The
**arrangement** (`satviz.arrangements`: single, compare, grid) draws, and the **theme** styles the chrome.

    job file -> Template.plan (which input ids go in which figure)
             -> Template.resolve (arrangement, recipes, default wording, relation notes)
             -> arrangements.draw (page) styled by a Theme
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from satviz.core import RECIPES, SENSORS, Product, template
from satviz.relations import relate

ARRANGEMENTS = ("single", "compare", "grid")
OPTICAL_PREFERENCE = ("true_colour", "nir_fcc")  # true colour when there is a blue band, else NIR false colour
SAR_PREFERENCE = ("sar_fcc",)


class TemplateError(ValueError):
    """The inputs of a figure do not fit its template; the message says which template to use instead."""


@dataclass(frozen=True)
class Resolved:
    """A template's decisions for one figure: handed to `arrangements.draw`."""

    arrangement: str
    recipes: dict[str, str]  # input id -> recipe name
    text: dict = field(default_factory=dict)  # default wording; the job's own `text` overrides it
    caveats: tuple[str, ...] = ()  # relation statements added to the notice strip


def input_kind(spec) -> str:
    """'sar' or 'optical' for an input, known before any pixels are read (the sensor, or `kind` for a generic GeoTIFF)."""
    kind = SENSORS.get_or_raise(spec.sensor).kind
    return spec.options.get("kind", kind) if kind == "any" else kind


def default_recipe(product: Product, input_id: str = "") -> str:
    """The recipe an input gets when the job names none: the first of the preference list whose layers it has."""
    for name in SAR_PREFERENCE if product.kind == "sar" else OPTICAL_PREFERENCE:
        if all(layer in product.layers for layer in RECIPES[name].needs):
            return name
    raise TemplateError(f"input {input_id!r} ({product.meta.get('label', product.kind)}) has layers {sorted(product.layers)}; "
                        f"no default recipe fits, set recipes = {{ {input_id} = \"...\" }} in the figure")


def pick_recipes(named: dict, products: dict, combo: tuple[str, ...]) -> dict[str, str]:
    """Per input: its entry in the figure's `recipes`, else `default`, else the sensor-appropriate default."""
    return {k: named.get(k) or named.get("default") or default_recipe(products[k], k) for k in combo}


def pairs(ids: list[str]) -> list[tuple[str, ...]]:
    return list(itertools.combinations(ids, 2))


class Template:
    """Base: subclasses set `name`, `kinds` (what they accept) and `default_arrangement`."""

    name = ""
    summary = ""
    kinds: tuple[str, ...] = ("sar", "optical")
    default_arrangement = "single"
    min_inputs = 1

    def arrangement_of(self, fig) -> str:
        arrangement = fig.arrangement or self.default_arrangement
        if arrangement not in ARRANGEMENTS:
            raise TemplateError(f"arrangement must be one of {', '.join(ARRANGEMENTS)}, not {arrangement!r}")
        return arrangement

    def sorted_inputs(self, fig, job) -> dict[str, list[str]]:
        """The figure's input ids by kind, in the order listed; inputs of a kind the template does not take are refused."""
        out: dict[str, list[str]] = {k: [] for k in self.kinds}
        for i in fig.inputs:
            kind = input_kind(job.inputs[i])
            if kind not in out:
                others = {"sar": "optical_sar", "optical": "optical_sar"}.get(kind, "single")
                raise TemplateError(f"template {self.name!r} takes {' and '.join(self.kinds)} inputs only; input {i!r} is {kind} "
                                    f"(see template {others!r})")
            out[kind].append(i)
        return out

    def plan(self, fig, job) -> list[tuple[str, ...]]:
        raise NotImplementedError

    def text_defaults(self, products: list[Product], scene) -> dict:
        return {}

    def resolve(self, fig, combo: tuple[str, ...], products: dict, scene) -> Resolved:
        ps = [products[k] for k in combo]
        rel = relate(ps)
        text = self.text_defaults(ps, scene)
        if rel.label:
            text.setdefault("subtitle", f"{rel.label}  ·  {scene.region.upper()}" if scene.region else rel.label)
        note = (" · ".join(rel.notes),) if rel.notes else ()  # one line, so the notice strip stays short
        return Resolved(self.arrangement_of(fig), pick_recipes(fig.recipes, products, combo), text, note)


def register(cls):
    """Class decorator: one instance in the TEMPLATES registry under `cls.name`."""
    return template(cls.name)(cls())
