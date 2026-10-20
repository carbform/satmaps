"""The multispectral template: one optical product, band by band. No comparison, no pairs, no relation text.

Each input gets its own figure (arrangement `bands`): a panel per spectral band in wavelength order, labelled with band id, centre
wavelength and native pixel size, on one shared stretch (`stretch = "per-band"` for each its own). `composites = ["true_colour",
"nir_fcc"]` appends those recipes as extra panels; they are off by default, because the point is the bands.
"""
from __future__ import annotations

from satviz.recipes.bands import bands_of
from satviz.templates.base import Resolved, Template, TemplateError, register


@register
class Multispectral(Template):
    name = "multispectral"
    summary = "One optical product band by band: a panel per spectral band, optional composites; no comparison"
    kinds = ("optical",)
    default_arrangement = "bands"
    arrangements = ("bands",)
    hints = {"sar": "a SAR product has no spectral bands; use template 'sar'"}

    def plan(self, fig, job):
        self.arrangement_of(fig)
        ids = self.sorted_inputs(fig, job)["optical"]
        if not ids:
            raise TemplateError("template 'multispectral' needs at least one optical input")
        return [(k,) for k in ids]

    def resolve(self, fig, combo, products, scene):
        p = products[combo[0]]
        n = len(bands_of(p))
        label = f"{p.meta['platform']} {p.meta.get('label', '')}".strip().upper()
        subtitle = f"{label} · {n} BAND{'S' if n != 1 else ''}" + (f"  ·  {scene.region.upper()}" if scene.region else "")
        return Resolved("bands", {}, {"subtitle": subtitle}, (), {"composites": tuple(fig.composites)})
