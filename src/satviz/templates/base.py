"""What a template decides, and the base class the scenario templates share.

A **template** is a content scenario: which kinds of products it takes (optical, SAR, both), how they relate, which recipe
each gets, which page arrangement shows them and what the figure must say about the combination. It does not draw. The
**arrangement** (`satviz.arrangements`: single, compare, grid, bands) draws, and the **theme** styles the chrome.

    job file -> Template.plan (which input ids go in which figure)
             -> Template.resolve (arrangement, recipes, default wording, relation notes)
             -> arrangements.draw (page) styled by a Theme
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from satviz.core import RECIPES, SENSORS, Product, template
from satviz.relations import relate

OPTICAL_PREFERENCE = ("true_colour", "nir_fcc")  # true colour when there is a blue band, else NIR false colour
SAR_PREFERENCE = ("sar_compact", "sar_fcc")  # compact-pol products have the layers the first needs; the rest take the second


class TemplateError(ValueError):
    """The inputs of a figure do not fit its template; the message says which template to use instead."""


@dataclass(frozen=True)
class Resolved:
    """A template's decisions for one figure: handed to `arrangements.draw`."""

    arrangement: str
    recipes: dict[str, str]  # input id -> recipe name
    text: dict = field(default_factory=dict)  # default wording; the job's own `text` overrides it
    caveats: tuple[str, ...] = ()  # relation statements added to the notice strip
    options: dict = field(default_factory=dict)  # arrangement-specific choices, e.g. the composites of the bands arrangement


def input_kind(spec) -> str:
    """'sar' or 'optical' for an input, known before any pixels are read (the sensor's own kind)."""
    return SENSORS.get_or_raise(spec.sensor).kind


def default_recipe(product: Product, input_id: str = "") -> str:
    """The recipe an input gets when the job names none: the first of the preference list whose layers it has."""
    for name in SAR_PREFERENCE if product.kind == "sar" else OPTICAL_PREFERENCE:
        if all(layer in product.layers for layer in RECIPES[name].needs):
            return name
    raise TemplateError(f"input {input_id!r} ({product.meta.get('label', product.kind)}) has layers {sorted(product.layers)}; "
                        f"no default recipe fits, set recipes = {{ {input_id} = \"...\" }} in the figure")


def shared_optical_recipe(products: list[Product]) -> str | None:
    """The first preferred optical recipe every product can do, so several optical inputs show the same composite."""
    for name in OPTICAL_PREFERENCE:
        if all(layer in p.layers for p in products for layer in RECIPES[name].needs):
            return name
    return None


def pick_recipes(named: dict, products: dict, combo: tuple[str, ...]) -> dict[str, str]:
    """Per input: its entry in the figure's `recipes`, else `default`, else a sensor-appropriate default.

    With several optical inputs and nothing named, they all get one recipe (LISS-IV, which has no blue band, next to Sentinel-2
    gets NIR false colour on both sides), so the figure compares like with like."""
    optical = [products[k] for k in combo if products[k].kind == "optical"]
    shared = shared_optical_recipe(optical) if len(optical) > 1 else None
    return {k: named.get(k) or named.get("default") or (shared if shared and products[k].kind == "optical" else None)
            or default_recipe(products[k], k) for k in combo}


def product_name(p: Product) -> str:
    """'NISAR L-band', 'Sentinel-2C L2A', 'EOS-04 SAR': the platform and its label, as the products state them."""
    return f"{p.meta.get('platform', '')} {p.meta.get('label', '')}".strip()


MAX_TITLE = 32  # characters that fit the header beside the date at the larger size


def short_names(products: list[Product]) -> list[str]:
    """Platform names, with the label added only where the platform repeats (NISAR L-band and NISAR S-band)."""
    platforms = [p.meta.get("platform", "") for p in products]
    return [f"{pf} {p.meta.get('label', '')}".strip() if platforms.count(pf) > 1 else pf for pf, p in zip(platforms, products, strict=True)]


def auto_title(products: list[Product]) -> str:
    """A title for a figure whose job names none: the product and its date; for several, their names when they fit the header
    ('Sentinel-1D and Sentinel-2C'), else what the figure compares."""
    if len(products) == 1:
        p = products[0]
        when = p.meta.get("start")
        return f"{product_name(p)} · {when.day} {when:%b %Y}" if when else product_name(p)
    names = short_names(products)
    joined = " and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 2 else names)
    if len(joined) <= MAX_TITLE:
        return joined
    kinds = {p.kind for p in products}
    return "Radar and optical" if len(kinds) > 1 else "Radar compared" if kinds == {"sar"} else "Optical compared"


def pairs(ids: list[str]) -> list[tuple[str, ...]]:
    return list(itertools.combinations(ids, 2))


class Template:
    """Base: subclasses set `name`, `kinds` (what they accept) and `default_arrangement`."""

    name = ""
    summary = ""
    kinds: tuple[str, ...] = ("sar", "optical")
    default_arrangement = "single"
    arrangements: tuple[str, ...] = ("single", "compare", "grid")  # the page arrangements this template can use
    hints: dict = {}  # kind -> what to use instead, when an input of that kind is refused
    min_inputs = 1

    def arrangement_of(self, fig) -> str:
        arrangement = fig.arrangement or self.default_arrangement
        if arrangement not in self.arrangements:
            raise TemplateError(f"template {self.name!r}: arrangement must be one of {', '.join(self.arrangements)}, not {arrangement!r}")
        return arrangement

    def sorted_inputs(self, fig, job) -> dict[str, list[str]]:
        """The figure's input ids by kind, in the order listed; inputs of a kind the template does not take are refused."""
        out: dict[str, list[str]] = {k: [] for k in self.kinds}
        for i in fig.inputs:
            kind = input_kind(job.inputs[i])
            if kind not in out:
                hint = self.hints.get(kind) or "use template 'sar_optical' to mix SAR and optical"
                raise TemplateError(f"template {self.name!r} takes {' and '.join(self.kinds)} inputs only; input {i!r} is {kind} "
                                    f"({hint})")
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
        if not scene.name:  # no title anywhere in the job (a quick figure): say what the figure shows
            text.setdefault("title", auto_title(ps))
        if rel.label and text.get("title", "").upper() != rel.label.upper():  # not the title said twice
            text.setdefault("subtitle", f"{rel.label}  ·  {scene.region.upper()}" if scene.region else rel.label)
        note = (" · ".join(rel.notes),) if rel.notes else ()  # one line, so the notice strip stays short
        return Resolved(self.arrangement_of(fig), pick_recipes(fig.recipes, products, combo), text, note)


def register(cls):
    """Class decorator: one instance in the TEMPLATES registry under `cls.name`."""
    return template(cls.name)(cls())
