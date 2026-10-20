"""Import the built-in plugins so they register themselves, then expose the registries."""
from __future__ import annotations

from satviz.core import RECIPES, SENSORS, TEMPLATES, THEMES


def load_builtin() -> None:
    import satviz.recipes.optical  # noqa: F401
    import satviz.recipes.sar_fcc  # noqa: F401
    import satviz.sensors.eos04  # noqa: F401
    import satviz.sensors.geotiff  # noqa: F401
    import satviz.sensors.landsat  # noqa: F401
    import satviz.sensors.liss4  # noqa: F401
    import satviz.sensors.nisar_gcov  # noqa: F401
    import satviz.sensors.sentinel1  # noqa: F401
    import satviz.sensors.sentinel1_grd  # noqa: F401
    import satviz.sensors.sentinel2  # noqa: F401
    import satviz.sensors.sentinel2_safe  # noqa: F401
    import satviz.themes.minimal  # noqa: F401
    import satviz.themes.neo_brutal  # noqa: F401
    import satviz.themes.neo_retro  # noqa: F401
    import satviz.themes.newspaper  # noqa: F401
    import satviz.themes.xkcd  # noqa: F401

    _register_templates()


def _register_templates() -> None:
    import satviz.templates  # noqa: F401


def describe() -> dict[str, list[str]]:
    load_builtin()
    return {"sensors": sorted(SENSORS), "recipes": sorted(RECIPES), "themes": sorted(THEMES), "templates": sorted(TEMPLATES)}
