"""Scene and input dataclasses: what the place is called, which products to read and with which reader.

A job file (`satmaps.job`) builds these. Acquisition facts (date, pass, frequency, posting, CRS, processing flags) are read from
the files by each sensor; figure wording lives in wording files, see `layout`."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR_ENV = "SATMAPS_DATA_DIR"


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

    For ``nisar`` the options are ``group``, ``rows`` and ``cols`` (see `BandSpec`)."""

    key: str
    sensor: str
    file: str
    options: dict = field(default_factory=dict)


NISAR = "nisar"


@dataclass(frozen=True)
class Zoom:
    key: str
    name: str
    rows: tuple[int, int]
    cols: tuple[int, int]
    fit: bool = False  # from a centre and size: the page widens it to its panel's shape (rows/cols are drawn as given)


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
