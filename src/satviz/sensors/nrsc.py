"""Helpers shared by the NRSC/ISRO readers (`liss4`, `eos04`): their products carry a plain `key=value` metadata file."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from satviz.sources import SourceError


def product_folder(path: Path) -> Path:
    """The product folder for a source path that names the folder itself or a file inside it."""
    return path if path.is_dir() else path.parent


def read_meta(folder: Path, pattern: str) -> dict[str, str]:
    """`key=value` lines of the first file in `folder` matching `pattern` (``*.meta`` or ``BAND_META.txt``)."""
    files = sorted(folder.glob(pattern))
    if not files:
        raise SourceError(f"{folder}: no {pattern} file; point `source.path` at the unzipped product folder")
    out = {}
    for line in files[0].read_text(errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_time(text: str) -> datetime:
    """``05-OCT-2026 04:47:22.601994`` -> naive UTC datetime (fraction of a second dropped)."""
    return datetime.strptime(text.split(".")[0], "%d-%b-%Y %H:%M:%S")
