"""Bands arrangement (4:5): one optical product shown band by band, one panel per spectral band, then any composites asked for.

No comparison: a single product, every panel on the same ground. Panels are linear greys on one shared stretch by default
(`stretch = "per-band"` gives each its own, printed on its label); composites (`composites = ["true_colour", "nir_fcc"]`) follow the
bands in a second chip colour. Each label states the band id, centre wavelength (or nominal range) and native pixel size.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from satmaps.arrangements.compare import platforms
from satmaps.arrangements.grid import AREA_BOX, FIG_H, FIG_W, layout_cells
from satmaps.config import Scene
from satmaps.core import RECIPES, THEMES, LegendItem, check_recipe
from satmaps.furniture import DEFAULT, Furniture, decorate
from satmaps.geo import utm_extent
from satmaps.layout import Layout, LayoutError, build_context_products
from satmaps.quality import Profile, save
from satmaps.recipes.bands import OUTSIDE_RGB, STRETCH_NOTE, bands_of, cloud_left_out, grey_rgba, label_lines, limits, usable
from satmaps.registry import load_builtin
from satmaps.themes.base import chip, img_axes, social_footer, social_header

FILENAME = "{scene}_{key}_Bands_{tag}.png"
GREY = "#8a8a8a"
NO_DATA = "#{:02x}{:02x}{:02x}".format(*OUTSIDE_RGB)


def render(scene: Scene, products: dict, out_dir: Path, layout: dict, input: str, composites: tuple[str, ...] = (),
           stretch: str = "pooled", theme: str = "retro_80s", stem: str | None = None,
           extra_caveats: tuple[str, ...] = (), profile: Profile | None = None, furniture: Furniture = DEFAULT) -> list[Path]:
    """`input` is the one product to show. `stretch` is "pooled" (one set of limits for all bands) or "per-band"."""
    load_builtin()
    t = THEMES.get_or_raise(theme)
    P = products[input]
    if P.kind != "optical":
        raise LayoutError(f"the bands arrangement shows spectral bands; input {input!r} is a {P.kind} product")
    if stretch not in ("pooled", "per-band"):
        raise LayoutError(f"stretch must be 'pooled' or 'per-band', not {stretch!r}")
    infos = bands_of(P)
    if not infos:
        raise LayoutError(f"input {input!r} has no spectral bands to show")
    arrays = [P.layers[b.layer] for b in infos]
    clear = usable(P)  # cloud does not set the stretch; it is drawn, saturated
    shared = limits(arrays, clear) if stretch == "pooled" else None

    panels = []  # (rgba, chip text, chip colour)
    for b, arr in zip(infos, arrays, strict=True):
        lims = shared or limits([arr], clear)
        panels.append((grey_rgba(arr, P.valid, *lims), label_lines(b, None if shared else lims), t.chip_a))
    legend = [LegendItem(GREY, f"ONE STRETCH {shared[0]:.2f}–{shared[1]:.2f} REFLECTANCE" if shared else "OWN STRETCH PER BAND (ON LABEL)"),
              LegendItem(NO_DATA, "NO DATA")]
    for name in composites:
        rec = RECIPES.get_or_raise(name)
        try:
            check_recipe(name, rec, P, input)
        except ValueError as e:
            raise LayoutError(str(e)) from None
        r = rec.render(P)
        panels.append((r.rgba, r.title, t.chip_b))
        legend += [i for i in r.legend if i.color != "noise" and i.text not in {x.text for x in legend}]
    caveats = [*P.caveats, *([STRETCH_NOTE] if cloud_left_out(P) else []), *extra_caveats]
    lay = Layout(layout, build_context_products(scene, {input: P}, True))
    ext = utm_extent(dict(x=P.x, y=P.y))
    H, W = panels[0][0].shape[:2]
    rows, cols, pw = layout_cells(len(panels), H / W)
    ph = pw * FIG_W * (H / W) / FIG_H
    gap = 0.012
    total_w, total_h = cols * pw + (cols - 1) * gap, rows * ph + (rows - 1) * gap * FIG_W / FIG_H
    x0 = AREA_BOX[0] + (AREA_BOX[2] - total_w) / 2
    ytop = AREA_BOX[1] + AREA_BOX[3] - (AREA_BOX[3] - total_h) / 2

    with plt.rc_context(t.rc_params()):
        fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=t.paper)
        social_header(fig, t, lay)
        for i, (rgba, text, colour) in enumerate(panels):
            r, c = divmod(i, cols)
            x = x0 + c * (pw + gap)
            y = ytop - (r + 1) * ph - r * gap * FIG_W / FIG_H
            ax = img_axes(fig, t, x, y, pw, ph)
            ax.imshow(rgba, extent=ext, origin="upper", aspect="auto", interpolation="antialiased")
            decorate(ax, t, ext, P.epsg, furniture, first=i == 0)
            chip(fig, t, x + 0.006, y + ph - 0.006, text, colour, fs=8.5 if "\n" in text else 9.5, va="top", ha="left")
        social_footer(fig, t, lay, legend=legend[:6], caveats=caveats,
                      required_credits=[(P.meta["attribution"], P.meta["credit"])])
        out = Path(out_dir) / (f"{stem}.png" if stem else FILENAME.format(
            scene=f"{platforms([P])}_{scene.name}", key=input, tag=t.tag))
        t.finish(fig)
        save(fig, out, t.paper, profile)
        plt.close(fig)
    return [out]
