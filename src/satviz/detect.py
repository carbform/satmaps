"""Which sensor reads a path, found by looking at the path itself (`sniff` on each registered sensor).

``detect("data/S1D_….SAFE")`` gives ``"sentinel1"``. A path that no sensor recognises, or that several do, is an error that
lists what each sensor expects, so the fix is in the message. A `.zip` is refused with "unzip it": the readers take folders.
"""
from __future__ import annotations

from pathlib import Path

from satviz.core import SENSORS
from satviz.registry import load_builtin

FIXED_IDS = {"sentinel1": "S1", "eos04": "E", "sentinel2": "S2", "liss4": "L4"}  # NISAR is L or S by its band


class DetectError(ValueError):
    """A path is not a product any sensor reads, or more than one does."""


def detect(path: str | Path) -> str:
    """The name of the one sensor that reads `path`."""
    load_builtin()
    path = Path(path).expanduser()
    if not path.exists():
        raise DetectError(f"{path}: no such file or folder")
    if path.suffix.lower() == ".zip":
        raise DetectError(f"{path.name} is a zip: unzip it (the readers take the product folder) and pass the folder")
    found = [name for name, s in sorted(SENSORS.items()) if getattr(s, "sniff", None) and s.sniff(path)]
    if len(found) == 1:
        return found[0]
    if found:
        raise DetectError(f"{path.name} looks like more than one product ({', '.join(found)}); name the sensor in a job file")
    sniffers = {name: s.sniff for name, s in sorted(SENSORS.items()) if getattr(s, "sniff", None)}
    expects = "\n".join(f"  {name:10} {' '.join(f.__doc__.split())}" for name, f in sniffers.items())
    raise DetectError(f"{path.name} is not a product satviz reads. It reads:\n{expects}")


def input_id(sensor: str, path: str | Path, taken: set[str]) -> str:
    """A short id for an input (`L`, `S` for NISAR by band; `S1`, `E`, `S2`, `L4`), numbered on a collision (`S1_2`)."""
    if sensor == "nisar":
        from satviz.sensors.sar.nisar.canvas import find_group

        base = find_group(Path(path)).split("/")[1][0]  # science/LSAR/GCOV -> "L"
    else:
        base = FIXED_IDS[sensor]
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    return key
