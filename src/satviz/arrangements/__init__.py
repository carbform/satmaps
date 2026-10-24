"""Page arrangements: how products sit on a page. `single` (one hero), `compare` (split view), `grid` (2 to 6 panels) and `bands`
(one optical product, a panel per spectral band).

They draw; a template (`satviz.templates`) decides which one and with what recipes, and a theme (`satviz.themes`) styles the chrome.
"""
from __future__ import annotations

from pathlib import Path


def draw(resolved, *, scene, products: dict, out_dir: Path, layout: dict, combo: tuple[str, ...], theme: str,
         stem: str | None = None, slot: int = 0, strict: bool = True, stretch: str | None = None,
         profile=None) -> list[Path]:
    """Draw one figure from a template's `Resolved` decisions. `slot` is the input's position in the job (chip colour)."""
    from satviz.arrangements import bands, compare, grid, single

    common = dict(theme=theme, stem=stem, extra_caveats=resolved.caveats, profile=profile)
    if resolved.arrangement == "bands":
        return bands.render(scene, products, out_dir, layout, input=combo[0], composites=tuple(resolved.options.get("composites", ())),
                            stretch=stretch or "pooled", **common)
    if resolved.arrangement == "single":
        k = combo[0]
        return single.render(scene, products, out_dir, layout, input=k, recipe=resolved.recipes[k], chip_slot="ab"[min(slot, 1)],
                             **common)
    if resolved.arrangement == "grid":
        return grid.render(scene, products, out_dir, layout, inputs=combo, recipe=resolved.recipes, strict=strict, **common)
    per_band = None if stretch is None else stretch == "per-band"
    return compare.render(scene, products, out_dir, layout, inputs=combo, recipe=resolved.recipes, per_band=per_band,
                          strict=strict, **common)
