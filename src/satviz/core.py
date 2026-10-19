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
THEMES = Registry("theme")

sensor, recipe, theme = SENSORS.register, RECIPES.register, THEMES.register


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
    shared: dict = field(default_factory=dict)  # top-level placeholders this sensor adds (track, frame, ...); inputs must agree
    native: dict | None = None  # the sensor's own working dataset, for recipes that need more than `layers`


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


@dataclass
class Rendered:
    """A recipe's output: the picture plus what must be said about it."""

    rgba: np.ndarray
    extent: list[float]  # [left, right, bottom, top] in the product CRS, metres
    legend: list[LegendItem] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    components_extent: list[float] | None = None
    lims: dict | None = None  # stretch limits used, as placeholders ({lim.HH_lo}); None if the recipe has none


@dataclass
class Recipe:
    """``render(product, lims)`` gives a `Rendered`; ``shared_lims(products)`` (optional) gives stretch limits pooled over
    several products so one colour means the same thing in all of them."""

    render: Callable[..., Rendered]
    shared_lims: Callable[[list[Product]], dict] | None = None
