"""Scene configuration: which granules to read, which region of each, and what the place is called.

Acquisition facts (date, pass, frequency, posting, CRS, processing flags) are read from the files, see `metadata`.
Figure wording lives in the layout files, see `layout`."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DATA_DIR_ENV = "NISAR_DATA_DIR"


@dataclass(frozen=True)
class BandSpec:
    key: str  # "L" or "S"
    file: str
    group: str  # HDF5 group of the GCOV product, e.g. science/SSAR/GCOV
    rows: tuple[int, int]
    cols: tuple[int, int]


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
    bands: dict[str, BandSpec]
    zooms: tuple[Zoom, ...]
    callouts: dict[str, tuple[float, float]]  # key -> (lat, lon)
    data_dir: Path

    def band_path(self, key: str) -> Path:
        return self.data_dir / self.bands[key].file


def load_scene(config: str | os.PathLike, data_dir: str | os.PathLike | None = None) -> Scene:
    """Read a scene TOML. Data dir: argument, then $NISAR_DATA_DIR, then ./data if present, else the current directory."""
    with open(config, "rb") as f:
        raw = tomllib.load(f)
    s = raw["scene"]
    bands = {
        key: BandSpec(
            key=key, file=b["file"], group=b["group"], rows=tuple(b["rows"]), cols=tuple(b["cols"]),
        )
        for key, b in raw["bands"].items()
    }
    zooms = tuple(Zoom(z["key"], z["name"], tuple(z["rows"]), tuple(z["cols"])) for z in raw.get("zooms", []))
    callouts = {k: (float(v["lat"]), float(v["lon"])) for k, v in raw.get("callouts", {}).items()}
    root = data_dir or os.environ.get(DATA_DIR_ENV) or (Path("data") if Path("data").is_dir() else Path.cwd())
    return Scene(
        name=s["name"], reach=s["reach"], locality=s["locality"], region=s["region"], callout_caption=s["callout_caption"],
        author=s["author"], website=s["website"],
        bands=bands, zooms=zooms, callouts=callouts, data_dir=Path(root).expanduser(),
    )
