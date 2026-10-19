"""Scene configuration: which granules to read, which region of each, and what the place is called.

Acquisition facts (date, pass, frequency, posting, CRS, processing flags) are read from the files, see `metadata`.
Figure wording lives in the layout files, see `layout`."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR_ENV = "SATVIZ_DATA_DIR"
LEGACY_DATA_DIR_ENV = "NISAR_DATA_DIR"  # still honoured


@dataclass(frozen=True)
class BandSpec:
    key: str  # "L" or "S"
    file: str
    group: str  # HDF5 group of the GCOV product, e.g. science/SSAR/GCOV
    rows: tuple[int, int]
    cols: tuple[int, int]


@dataclass(frozen=True)
class InputSpec:
    """One input product: which sensor reader handles it, which file, and the reader's own options.

    For ``nisar_gcov`` the options are ``group``, ``rows`` and ``cols`` (see `BandSpec`)."""

    key: str
    sensor: str
    file: str
    options: dict = field(default_factory=dict)


NISAR = "nisar_gcov"


@dataclass(frozen=True)
class Zoom:
    key: str
    name: str
    rows: tuple[int, int]
    cols: tuple[int, int]


@dataclass(frozen=True)
class Scene:
    name: str
    reach: str
    locality: str
    region: str
    callout_caption: str
    author: str
    website: str
    zooms: tuple[Zoom, ...]
    callouts: dict[str, tuple[float, float]]  # key -> (lat, lon)
    data_dir: Path
    inputs: dict[str, InputSpec] = field(default_factory=dict)  # in file order; the first is the reference for shared facts
    bands: dict[str, BandSpec] = field(default_factory=dict)  # NISAR view of `inputs`, kept for the older figures

    def __post_init__(self):
        # `inputs` and `bands` describe the same thing; give whichever was left out
        if not self.inputs and self.bands:
            ins = {k: InputSpec(k, NISAR, b.file, dict(group=b.group, rows=list(b.rows), cols=list(b.cols)))
                   for k, b in self.bands.items()}
            object.__setattr__(self, "inputs", ins)
        elif self.inputs and not self.bands:
            bands = {k: BandSpec(k, i.file, i.options["group"], tuple(i.options["rows"]), tuple(i.options["cols"]))
                     for k, i in self.inputs.items() if i.sensor == NISAR and {"group", "rows", "cols"} <= set(i.options)}
            object.__setattr__(self, "bands", bands)

    def input_path(self, key: str) -> Path:
        return self.data_dir / self.inputs[key].file

    def band_path(self, key: str) -> Path:
        return self.input_path(key)


def load_scene(config: str | os.PathLike, data_dir: str | os.PathLike | None = None) -> Scene:
    """Read a scene TOML. Data dir: argument, $SATVIZ_DATA_DIR (legacy $NISAR_DATA_DIR), ./data if present, else cwd."""
    with open(config, "rb") as f:
        raw = tomllib.load(f)
    s = raw["scene"]
    inputs = {}
    for i in raw.get("inputs", []):  # [[inputs]] id = "S", sensor = "nisar_gcov", file = ..., plus reader options
        opts = {k: v for k, v in i.items() if k not in ("id", "sensor", "file")}
        inputs[i["id"]] = InputSpec(i["id"], i.get("sensor", NISAR), i["file"], opts)
    for key, b in raw.get("bands", {}).items():  # older form: [bands.S]
        inputs[key] = InputSpec(key, NISAR, b["file"], dict(group=b["group"], rows=list(b["rows"]), cols=list(b["cols"])))
    if not inputs:
        raise KeyError("scene config has no [[inputs]]")
    zooms = tuple(Zoom(z["key"], z["name"], tuple(z["rows"]), tuple(z["cols"])) for z in raw.get("zooms", []))
    callouts = {k: (float(v["lat"]), float(v["lon"])) for k, v in raw.get("callouts", {}).items()}
    env = os.environ.get(DATA_DIR_ENV) or os.environ.get(LEGACY_DATA_DIR_ENV)
    root = data_dir or env or (Path("data") if Path("data").is_dir() else Path.cwd())
    return Scene(
        name=s["name"], reach=s["reach"], locality=s["locality"], region=s["region"], callout_caption=s["callout_caption"],
        author=s["author"], website=s["website"],
        inputs=inputs, zooms=zooms, callouts=callouts, data_dir=Path(root).expanduser(),
    )
