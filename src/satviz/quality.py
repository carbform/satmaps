"""Quality profiles: how large a figure is drawn and what is written for it.

`quick` is for looking: a coarse canvas and a small PNG, in seconds. `publication` is the full-size figure with a PDF next to the
PNG (text stays text; the picture panels are embedded at the figure's dpi). Notices and credits are drawn in both: a quick figure
makes the same claims as a publication one. The canvas size only applies to a job with no pixel size of its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    name: str
    target_px: int  # pixels along the longer side of an automatic area
    dpi: int
    pdf: bool  # also write a PDF next to the PNG


PROFILES = {"quick": Profile("quick", 800, 100, False), "publication": Profile("publication", 2000, 180, True)}
DEFAULT = PROFILES["publication"]


def profile_of(name: str | None) -> Profile:
    if name is None:
        return DEFAULT
    if name not in PROFILES:
        raise ValueError(f"quality must be one of {', '.join(PROFILES)}, not {name!r}")
    return PROFILES[name]


def save(fig, out: Path, facecolor, profile: Profile | None = None) -> None:
    """Write the figure as PNG (and PDF for a profile that asks for it). Call it while the theme's rc context is still open."""
    import matplotlib as mpl

    profile = profile or DEFAULT
    fig.savefig(out, dpi=profile.dpi, facecolor=facecolor)
    if profile.pdf:
        with mpl.rc_context({"pdf.fonttype": 42}):  # TrueType in the PDF: selectable, editable text
            fig.savefig(Path(out).with_suffix(".pdf"), dpi=profile.dpi, facecolor=facecolor)
