"""Placeholder values for one NISAR GCOV band: file metadata plus noise statistics, as used in layout files."""
from __future__ import annotations

from types import SimpleNamespace


def band_facts(m, st: dict) -> SimpleNamespace:
    """`m` is a `BandMeta`, `st` the dict from `processing.stats`."""
    return SimpleNamespace(
        instrument=m.instrument, crid=m.crid, product_version=m.product_version, spec_version=m.spec_version,
        processing_center=m.processing_center, freq_ghz=m.freq_ghz, wavelength_cm=m.wavelength_cm,
        bandwidth_mhz=m.bandwidth_mhz if m.bandwidth_mhz is not None else float("nan"),
        looks=m.looks if m.looks is not None else float("nan"), polarisations=m.polarisations, rfi=m.rfi,
        rfi_state="applied" if m.rfi_applied else "not applied",
        calibration="populated" if m.calibrated else "NOT populated", calibrated=m.calibrated,
        start_utc=f"{m.start:%H:%M:%S}", noisy_hv_pct=100 * st["noisy_hv_frac_of_valid"],
        noisy_hv_pct_gamma=100 * st["noisy_hv_frac_if_gamma_referenced"], exc64_pct=100 * st["exc64_frac_of_valid"],
        eta_p1=st["eta_p1_p50_p99"][0], eta_p99=st["eta_p1_p50_p99"][2], nebs_hv_db_median=st["nebs_hv_db_median"],
    )
