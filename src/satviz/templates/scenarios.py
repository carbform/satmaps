"""The four content scenarios: optical only, SAR only, optical + SAR, and SAR against SAR.

For SAR against SAR the relation is read from the products and stated on the figure (see `satviz.relations`): same band from
different sensors, different bands from different sensors, or one sensor in different bands.
"""
from __future__ import annotations

from satviz.templates.base import Template, TemplateError, pairs, register


class _Single(Template):
    """One kind of product, one figure per input (arrangement single), or compared (compare) or tiled (grid)."""

    def plan(self, fig, job):
        ids = self.sorted_inputs(fig, job)[self.kinds[0]]
        arrangement = self.arrangement_of(fig)
        if arrangement == "single":
            return [(k,) for k in ids]
        if len(ids) < 2:
            raise TemplateError(f"template {self.name!r} with arrangement {arrangement!r} needs at least two inputs")
        if arrangement == "grid":
            if len(ids) > 6:
                raise TemplateError(f"grid shows 2 to 6 inputs, got {len(ids)}")
            return [tuple(ids)]
        return pairs(ids)


@register
class Optical(_Single):
    name = "optical"
    summary = "Optical imagery only: one figure per input, or several compared or tiled"
    kinds = ("optical",)


@register
class Sar(_Single):
    name = "sar"
    summary = "SAR only: one figure per input, or several compared or tiled"
    kinds = ("sar",)


@register
class OpticalSar(Template):
    name = "optical_sar"
    summary = "Radar next to optical: each SAR input against each optical input (SAR on the left)"
    default_arrangement = "compare"

    def plan(self, fig, job):
        by_kind = self.sorted_inputs(fig, job)
        sar, optical = by_kind["sar"], by_kind["optical"]
        if not sar or not optical:
            raise TemplateError("template 'optical_sar' needs at least one SAR and one optical input")
        arrangement = self.arrangement_of(fig)
        if arrangement == "single":
            raise TemplateError("template 'optical_sar' shows several inputs; use arrangement 'compare' or 'grid'")
        if arrangement == "grid":
            if len(sar) + len(optical) > 6:
                raise TemplateError(f"grid shows 2 to 6 inputs, got {len(sar) + len(optical)}")
            return [tuple(sar + optical)]
        return [(s, o) for s in sar for o in optical]


@register
class SarVsSar(Template):
    name = "sar_vs_sar"
    summary = "SAR against SAR: same band from different sensors, different bands, or one sensor in two bands"
    kinds = ("sar",)
    default_arrangement = "compare"
    min_inputs = 2

    def plan(self, fig, job):
        ids = self.sorted_inputs(fig, job)["sar"]
        if len(ids) < 2:
            raise TemplateError("template 'sar_vs_sar' needs at least two SAR inputs")
        arrangement = self.arrangement_of(fig)
        if arrangement == "single":
            raise TemplateError("template 'sar_vs_sar' shows several inputs; use arrangement 'compare' or 'grid'")
        if arrangement == "grid":
            if len(ids) > 6:
                raise TemplateError(f"grid shows 2 to 6 inputs, got {len(ids)}")
            return [tuple(ids)]
        return pairs(ids)
