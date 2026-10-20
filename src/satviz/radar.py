"""Radar band facts: every SAR product states its band, centre frequency and wavelength, read from its own files."""
from __future__ import annotations

C_M_S = 299_792_458.0
BANDS = (("L", 1.0, 2.0), ("S", 2.0, 4.0), ("C", 4.0, 8.0), ("X", 8.0, 12.0))  # IEEE radar bands, GHz


def band_of(freq_ghz: float) -> str:
    """IEEE radar band letter of a centre frequency (GHz); empty when it falls outside L to X."""
    return next((b for b, lo, hi in BANDS if lo <= freq_ghz < hi), "")


def radar_facts(freq_ghz: float, band: str | None = None) -> dict:
    """The `meta` entries every SAR product carries: ``radar_band``, ``freq_ghz``, ``wavelength_cm``."""
    return dict(radar_band=band or band_of(freq_ghz), freq_ghz=round(freq_ghz, 4),
                wavelength_cm=round(C_M_S / (freq_ghz * 1e9) * 100, 2))
