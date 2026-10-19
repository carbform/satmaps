"""Where an input's data comes from: a local path or glob. (STAC search is added with the optical readers.)"""
from __future__ import annotations

from pathlib import Path


class SourceError(ValueError):
    """An input's `source` is missing, ambiguous or points at nothing."""


def source_of(spec) -> dict:
    """The `source` table of an input; older configs with only `file` become ``{"path": file}``."""
    src = spec.options.get("source")
    if src is None:
        if not spec.file:
            raise SourceError(f"input {spec.key!r}: no `source` (e.g. source = {{ path = \"data/file.h5\" }})")
        return {"path": spec.file}
    if not isinstance(src, dict):
        raise SourceError(f"input {spec.key!r}: `source` must be a table like {{ path = \"...\" }}, not {src!r}")
    return src


def resolve_one_file(spec, data_dir: Path) -> Path:
    """The single local file a path/glob source names (relative paths are looked up in `data_dir`)."""
    src = source_of(spec)
    if "path" not in src:
        raise SourceError(f"input {spec.key!r}: source needs `path` for this sensor, got {sorted(src)}")
    pattern = str(Path(src["path"]).expanduser())
    base = Path(data_dir)
    hits = sorted(Path(pattern).parent.glob(Path(pattern).name)) if Path(pattern).is_absolute() else sorted(base.glob(pattern))
    if not hits:
        where = pattern if Path(pattern).is_absolute() else f"{pattern} in {base.resolve()}"
        raise FileNotFoundError(
            f"input {spec.key!r}: nothing matches {where}. Put the file there, pass --data-dir, or set SATVIZ_DATA_DIR."
        )
    if len(hits) > 1:
        names = "\n  ".join(h.name for h in hits[:6])
        raise SourceError(f"input {spec.key!r}: {pattern} matches {len(hits)} files, narrow it down:\n  {names}")
    return hits[0]
