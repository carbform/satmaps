"""Import the built-in plugins so they register themselves, then expose the registries."""
from __future__ import annotations

from satmaps.core import RECIPES, SENSORS, TEMPLATES, THEMES


def load_builtin() -> None:
    import satmaps.recipes.optical  # noqa: F401
    import satmaps.recipes.sar_compact  # noqa: F401
    import satmaps.recipes.sar_fcc  # noqa: F401
    import satmaps.sensors.optical.liss4  # noqa: F401  # noqa: F401
    import satmaps.sensors.optical.sentinel2  # noqa: F401  # noqa: F401
    import satmaps.sensors.sar.eos04  # noqa: F401  # noqa: F401
    import satmaps.sensors.sar.nisar  # noqa: F401  # noqa: F401
    import satmaps.sensors.sar.sentinel1  # noqa: F401  # noqa: F401
    import satmaps.themes.minimal  # noqa: F401
    import satmaps.themes.neo_brutal  # noqa: F401
    import satmaps.themes.neo_retro  # noqa: F401
    import satmaps.themes.newspaper  # noqa: F401
    import satmaps.themes.retro_80s  # noqa: F401
    import satmaps.themes.xkcd  # noqa: F401

    _register_templates()


def _register_templates() -> None:
    import satmaps.templates  # noqa: F401


def describe() -> dict[str, list[str]]:
    load_builtin()
    return {"sensors": sorted(SENSORS), "recipes": sorted(RECIPES), "themes": sorted(THEMES), "templates": sorted(TEMPLATES)}
