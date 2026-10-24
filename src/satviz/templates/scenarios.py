"""The three content scenarios: `sar`, `optical` and `sar_optical`.

`sar` takes any number of SAR inputs (NISAR, Sentinel-1, EOS-04): one figure per input, every pair split-view, or all on one grid. With
two or more, the relation is read from the products and stated on the figure (see `satviz.relations`): same band from different
sensors, different bands from different sensors, or one sensor in two bands, plus the time gap and the backscatter convention.

`optical` takes Sentinel-2 and LISS-IV the same way, and also shows one product band by band (`arrangement = "bands"`): a panel per
spectral band in wavelength order, labelled with band id, centre wavelength and native pixel size, on one shared stretch
(`stretch = "per-band"` for each its own). `composites = ["true_colour", "nir_fcc"]` appends those recipes as extra panels.

`sar_optical` puts each SAR input against each optical input, SAR on the left.
"""
from __future__ import annotations

from satviz.recipes.bands import bands_of
from satviz.templates.base import Resolved, Template, TemplateError, auto_title, pairs, register

MAX_TILES = 6


class _OneKind(Template):
    """One kind of product: a figure per input (single), per pair (compare), or all tiled on one page (grid)."""

    def default_arrangement_for(self, n: int) -> str:
        return "single" if n == 1 else "compare"

    def arrangement_of(self, fig) -> str:
        arrangement = fig.arrangement or self.default_arrangement_for(len(fig.inputs))
        if arrangement not in self.arrangements:
            raise TemplateError(f"template {self.name!r}: arrangement must be one of {', '.join(self.arrangements)}, not {arrangement!r}")
        return arrangement

    def plan(self, fig, job):
        ids = self.sorted_inputs(fig, job)[self.kinds[0]]
        if not ids:
            raise TemplateError(f"template {self.name!r} needs at least one {self.kinds[0]} input")
        arrangement = self.arrangement_of(fig)
        if arrangement in ("single", "bands"):
            return [(k,) for k in ids]
        if len(ids) < 2:
            raise TemplateError(f"template {self.name!r} with arrangement {arrangement!r} needs at least two inputs")
        if arrangement == "grid":
            if len(ids) > MAX_TILES:
                raise TemplateError(f"grid shows 2 to {MAX_TILES} inputs, got {len(ids)}")
            return [tuple(ids)]
        return pairs(ids)


@register
class Sar(_OneKind):
    name = "sar"
    summary = "SAR (NISAR, Sentinel-1, EOS-04): one figure per input, every pair compared, or all tiled"
    kinds = ("sar",)
    arrangements = ("single", "compare", "grid")


@register
class Optical(_OneKind):
    name = "optical"
    summary = "Optical (Sentinel-2, LISS-IV): one figure per input, pairs, a grid, or band by band"
    kinds = ("optical",)
    arrangements = ("single", "compare", "grid", "bands")
    hints = {"sar": "a SAR product has no spectral bands; use template 'sar', or 'sar_optical' for both"}

    def resolve(self, fig, combo, products, scene):
        if self.arrangement_of(fig) != "bands":
            return super().resolve(fig, combo, products, scene)
        p = products[combo[0]]
        n = len(bands_of(p))
        label = f"{p.meta['platform']} {p.meta.get('label', '')}".strip().upper()
        subtitle = f"{label} · {n} BAND{'S' if n != 1 else ''}" + (f"  ·  {scene.region.upper()}" if scene.region else "")
        text = {"subtitle": subtitle, **({"title": auto_title([p])} if not scene.name else {})}
        return Resolved("bands", {}, text, (), {"composites": tuple(fig.composites)})


@register
class SarOptical(Template):
    name = "sar_optical"
    summary = "Radar next to optical: each SAR input against each optical input (SAR on the left), or all tiled"
    default_arrangement = "compare"
    arrangements = ("compare", "grid")

    def plan(self, fig, job):
        by_kind = self.sorted_inputs(fig, job)
        sar, optical = by_kind["sar"], by_kind["optical"]
        if not sar or not optical:
            raise TemplateError("template 'sar_optical' needs at least one SAR and one optical input")
        if self.arrangement_of(fig) == "grid":
            if len(sar) + len(optical) > MAX_TILES:
                raise TemplateError(f"grid shows 2 to {MAX_TILES} inputs, got {len(sar) + len(optical)}")
            return [tuple(sar + optical)]
        return [(s, o) for s in sar for o in optical]
