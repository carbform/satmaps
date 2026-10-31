"""An example page: what a layout and a theme look like, drawn before any data is read.

It is not a mock-up. It builds small stand-in products (smooth made-up images, labelled as examples) and draws them with the
real arrangements, themes and wording, so the page is exactly what a figure of that layout and theme would be, with the
panels waiting for your data. Used by the app's layout preview.
"""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from satviz.config import InputSpec, Scene
from satviz.core import BandInfo, Product
from satviz.job import FigureSpec
from satviz.quality import PROFILES

SIZE = 200  # pixels along a side of an example panel: enough for a smooth picture, quick to draw
WHEN = datetime(2026, 1, 15, 10, 0)
EXAMPLE_BANDS = (("B02", "blue", 490), ("B03", "green", 560), ("B04", "red", 665), ("B08", "nir", 835),
                 ("B11", "swir16", 1610), ("B12", "swir22", 2190))
DEFAULT_KINDS = {"single": ["sar"], "compare": ["sar", "optical"], "grid": ["sar", "sar", "optical", "optical"],
                 "bands": ["optical"]}


def _scene_pattern(seed: int) -> np.ndarray:
    """A smooth 0..1 picture with a winding dark 'river' and gentle texture: plainly made up, but reads like imagery."""
    from scipy.ndimage import gaussian_filter

    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE] / SIZE
    texture = gaussian_filter(rng.standard_normal((SIZE, SIZE)), 3)
    land = 0.55 + 0.10 * np.sin(5 * xx + seed) * np.cos(4 * yy) + 0.9 * texture
    d = np.abs(yy - (0.5 + 0.2 * np.sin(5 * xx + seed)))
    river = 1 - np.clip((d - 0.03) / 0.03, 0, 1)  # 1 in the channel, easing to 0 over a few pixels
    return np.clip(land * (1 - river) + 0.12 * river, 0.02, 0.98)


def example_product(key: str, kind: str, index: int) -> Product:
    """A stand-in product of a kind ('sar' or 'optical'): made-up pixels, plausible facts, and a notice saying so."""
    pat = _scene_pattern(index + 1)
    x = 500000.0 + 50.0 * np.arange(SIZE)
    y = 3000000.0 - 50.0 * np.arange(SIZE)
    letter = "ABCDEF"[index % 6]
    meta = dict(platform=f"Example {'radar' if kind == 'sar' else 'optical'}", sensor="EXAMPLE", label=f"product {letter}",
                start=WHEN, end=WHEN, resolution_m=70, crs="UTM 46N", attribution="Example",
                credit="Example credit: your product's own credit")
    caveats = ["Example notice: the notices your products insist on go here."]
    facts = SimpleNamespace(date="15 Jan 2026", polarisations="VV/VH", files="example")
    common = dict(key=key, x=x, y=y, epsg=32646, valid=np.ones((SIZE, SIZE), bool), facts=facts, caveats=caveats)
    if kind == "sar":
        co = (10 ** (-1.6 + 1.4 * pat)).astype(np.float32)
        cross = (co * 10 ** (-0.9 - 0.5 * _scene_pattern(index + 7))).astype(np.float32)
        band, freq, wl = ("C", 5.4, 5.55) if index % 2 == 0 else ("L", 1.26, 23.8)
        meta.update(radar_band=band, freq_ghz=freq, wavelength_cm=wl, backscatter="sigma0, ellipsoid")
        return Product(layers={"co": co, "cross": cross}, meta=meta, kind="sar", **common)
    base = {"blue": 0.05 + 0.04 * pat, "green": 0.07 + 0.08 * pat, "red": 0.06 + 0.10 * pat, "nir": 0.10 + 0.30 * (1 - pat),
            "swir16": 0.08 + 0.18 * pat, "swir22": 0.05 + 0.12 * pat}
    layers = {role: a.astype(np.float32) for role, a in base.items()}
    infos = []
    for code, role, nm in EXAMPLE_BANDS:
        layers[code] = layers[role]
        infos.append(BandInfo(id=code, layer=code, name=role, wavelength_nm=float(nm), resolution_m=10.0))
    meta.update(reflectance="surface", label=f"product {letter}")
    return Product(layers=layers, meta=meta, kind="optical", bands=tuple(infos), **common)


def usable_channels(channels: dict | None, products: dict) -> dict | None:
    """The false-colour choices the stand-in products can show (they have the six colour bands, not every band a sensor has)."""
    if not channels:
        return None
    have = set.intersection(*(set(p.layers) for p in products.values() if p.kind == "optical")) if any(
        p.kind == "optical" for p in products.values()) else set()
    return {kind: picked for kind, picked in channels.items() if kind == "sar" or all(c in have for c in picked)}


def render_example(kinds: list[str] | None, arrangement: str, theme: str, furniture=None, channels: dict | None = None,
                   **words) -> bytes:
    """PNG bytes of an example page: `kinds` ('sar' / 'optical' per product; None for a typical set), the layout, the theme.
    `words` (title, subtitle, place, author, website, credits) are the wording typed so far, shown as it will print."""
    from satviz.api import channel_recipes, details
    from satviz.arrangements import draw
    from satviz.core import TEMPLATES, THEMES
    from satviz.layout import apply_text, default_layout
    from satviz.registry import load_builtin

    load_builtin()
    THEMES.get_or_raise(theme)
    kinds = list(kinds) if kinds else list(DEFAULT_KINDS[arrangement])
    if arrangement == "bands":
        kinds = ["optical"]
    elif arrangement == "single":
        kinds = kinds[:1]
    elif arrangement == "compare" and len(kinds) > 2 and len(set(kinds)) == 1:
        kinds = kinds[:2]
    template = "sar_optical" if len(set(kinds)) > 1 else kinds[0]
    ids = [f"{k[:1].upper()}{i + 1}" for i, k in enumerate(kinds)]
    products = {key: example_product(key, kind, i) for i, (key, kind) in enumerate(zip(ids, kinds, strict=True))}
    fields, typed = details(**words)
    fields = {"name": "Your title", "region": "Your place", "author": "", "website": "", **fields}
    scene = Scene(name=fields["name"], reach="", locality="", region=fields["region"], callout_caption="",
                  author=fields["author"], website=fields["website"], zooms=(), callouts={}, data_dir=Path("."),
                  inputs={k: InputSpec(k, "", "", {}) for k in ids})
    if arrangement == "compare" and len(ids) > 2:
        combo = (ids[0], ids[-1])  # one pair is enough to show the page
    else:
        combo = tuple(ids)
    recipes = channel_recipes(usable_channels(channels, products), {k: products[k].kind for k in combo})
    fig = FigureSpec(template=template, inputs=combo, arrangement=arrangement, themes=(theme,), recipes=recipes)
    resolved = TEMPLATES[template].resolve(fig, combo, products, scene)
    layout = apply_text(default_layout(resolved.arrangement), {**resolved.text, **typed})
    with tempfile.TemporaryDirectory() as tmp:
        (png,) = draw(resolved, scene=scene, products=products, out_dir=Path(tmp), layout=layout, combo=combo, theme=theme,
                      stem="preview", slot=0, strict=False, profile=PROFILES["quick"], furniture=furniture)
        return png.read_bytes()
