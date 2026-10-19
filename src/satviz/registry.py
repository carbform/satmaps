"""Import the built-in plugins so they register themselves, then expose the registries."""
from __future__ import annotations

from satviz.core import RECIPES, SENSORS, THEMES


def load_builtin() -> None:
    import satviz.recipes.sar_fcc  # noqa: F401
    import satviz.sensors.nisar_gcov  # noqa: F401
    import satviz.themes.minimal  # noqa: F401
    import satviz.themes.neo_brutal  # noqa: F401
    import satviz.themes.neo_retro  # noqa: F401


def describe() -> dict[str, list[str]]:
    load_builtin()
    return {"sensors": sorted(SENSORS), "recipes": sorted(RECIPES), "themes": sorted(THEMES)}
