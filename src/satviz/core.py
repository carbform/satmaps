"""Core types and registries. See docs/architecture.md for how sensors, recipes, themes and templates fit together.

Each axis has a registry. A new sensor, recipe, theme or template is one module that registers itself with the
decorator, e.g. ``@sensor("sentinel2_l2a")``; `satviz list` shows what is registered.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np


class Registry(dict):
    """name -> object, filled by decorator. Unknown names raise with the list of known ones."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind

    def register(self, name: str) -> Callable:
        def deco(obj):
            if name in self:
                raise ValueError(f"{self.kind} {name!r} is already registered")
            self[name] = obj
            return obj

        return deco

    def get_or_raise(self, name: str):
        if name not in self:
            raise KeyError(f"unknown {self.kind} {name!r}; available: {', '.join(sorted(self)) or 'none'}")
        return self[name]


SENSORS = Registry("sensor")
RECIPES = Registry("recipe")
TEMPLATES = Registry("template")
THEMES = Registry("theme")

sensor, recipe, theme, template = SENSORS.register, RECIPES.register, THEMES.register, TEMPLATES.register


@dataclass(frozen=True)
class BandInfo:
    """One spectral band of an optical product, as a multispectral figure labels its panel.

    Everything here is read from the product's own files where they carry it; a field the product does not state stays None
    (a sensor that gives only a nominal range says so in `range_nm` and leaves `wavelength_nm` as that range's midpoint)."""

    id: str  # the sensor's own name for the band, e.g. "B04" or "B3"
    layer: str  # key in `Product.layers` that holds its pixels
    name: str = ""  # common name: "red", "nir", "red edge", ...
    wavelength_nm: float | None = None  # centre wavelength
    range_nm: tuple[float, float] | None = None  # nominal or measured band limits
    resolution_m: float | None = None  # native pixel size, before resampling to the canvas


@dataclass
class Product:
    """One scene from one sensor, as the recipes and templates see it.

    ``layers`` are named 2-D arrays on the product grid (sensor-specific names, e.g. HH/HV or red/nir). ``x``/``y`` are
    pixel-centre coordinates in ``epsg``. ``meta`` holds the generic facts every sensor must give (``platform``, ``sensor``,
    ``start``, ``end``, ``resolution_m``, ``crs``); ``facts`` is a namespace of sensor-specific placeholder values;
    ``caveats`` are statements the sensor insists on printing (e.g. "calibration not populated", "cloud 38%").
    """

    key: str
    layers: dict[str, np.ndarray]
    x: np.ndarray
    y: np.ndarray
    epsg: int
    valid: np.ndarray
    meta: dict
    facts: SimpleNamespace = field(default_factory=SimpleNamespace)
    caveats: list[str] = field(default_factory=list)
    kind: str = "sar"  # layer vocabulary: "sar" or "optical"; a recipe needs one kind
    shared: dict = field(default_factory=dict)  # top-level placeholders this sensor adds (track, frame, ...); inputs must agree
    native: dict | None = None  # the sensor's own working dataset, for recipes that need more than `layers`
    bands: tuple[BandInfo, ...] = ()  # spectral bands in wavelength order (optical sensors that can state them)


@dataclass
class SourceInfo:
    """What a reader knows about an input before reading pixels: used to choose the canvas."""

    epsg: int
    resolution_m: float
    phase: tuple[float, float] | None = None  # (x, y) of one pixel centre: the canvas aligns to it
    files: list = field(default_factory=list)  # what will be read (for the lock file and messages)


@dataclass
class LegendItem:
    color: str  # hex, or "noise" for the neutral grey drawn in the data
    text: str


@dataclass
class Component:
    """One input of a recipe shown on its own (e.g. a colour channel), for templates that have room for them."""

    key: str
    img: np.ndarray  # float RGB 0..1
    color: str  # hex, the chip colour
    label: str = ""  # default chip text; a layout's channels.labels overrides it


def check_recipe(name: str, rec: Recipe, product: Product, input_id: str) -> None:
    """Raise a readable error if the product is the wrong kind or lacks a layer the recipe needs."""
    if product.kind != rec.kind:
        raise ValueError(f"recipe {name!r} needs a {rec.kind} product but input {input_id!r} is {product.kind}")
    if missing := [n for n in rec.needs if n not in product.layers]:
        raise ValueError(f"recipe {name!r} needs band(s) {', '.join(missing)}, which input {input_id!r} does not have "
                         f"(it has: {', '.join(k for k in product.layers if k != 'cloud')})")


@dataclass
class Rendered:
    """A recipe's output: the picture plus what must be said about it."""

    rgba: np.ndarray
    extent: list[float]  # [left, right, bottom, top] in the product CRS, metres
    legend: list[LegendItem] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    components_extent: list[float] | None = None
    title: str = ""  # default chip text for the hero ("R+G+B  COMPOSITE", "TRUE COLOUR")
    lims: dict | None = None  # stretch limits used, as placeholders ({lim.HH_lo}); None if the recipe has none


@dataclass
class Recipe:
    """``render(product, lims)`` gives a `Rendered`; ``shared_lims(products)`` (optional) gives stretch limits pooled over
    several products so one colour means the same thing in all of them."""

    render: Callable[..., Rendered]
    kind: str = "sar"
    needs: tuple[str, ...] = ()  # layers the recipe reads; a product without them is refused with a clear message
    shared_lims: Callable[[list[Product]], dict] | None = None
