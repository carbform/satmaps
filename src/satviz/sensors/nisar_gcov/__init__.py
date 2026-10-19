"""NISAR L2 GCOV (L-SAR and S-SAR): the first sensor plugin.

``load(scene, key, cache_dir)`` returns the working dataset; ``to_product`` gives the generic `Product` view."""
from __future__ import annotations

from types import SimpleNamespace

from satviz.core import Product, sensor
from satviz.sensors.nisar_gcov.facts import band_facts
from satviz.sensors.nisar_gcov.io import load_roi
from satviz.sensors.nisar_gcov.processing import stats

LAYER_KEYS = ("hh", "hv", "hh_ns", "hv_ns", "snr_hh", "snr_hv", "n_hh", "n_hv", "eta")


def to_product(d: dict) -> Product:
    """Wrap a working dataset from `load_roi` as a generic `Product` (the dict stays available as ``native``)."""
    m = d["meta"]
    caveats = []
    if not m.calibrated:
        caveats.append(f"{m.radar_band}-band calibration metadata not yet populated: dB values are provisional and relative")
    return Product(
        key=d["band"], layers={k: d[k] for k in LAYER_KEYS}, x=d["x"], y=d["y"], epsg=d["epsg"], valid=d["valid"],
        meta=dict(platform="NISAR", sensor=m.instrument, start=m.start, end=m.end, resolution_m=m.posting_m, crs=m.crs),
        facts=band_facts(m, stats(d)), caveats=caveats, native=d,
    )


NISAR_GCOV = sensor("nisar_gcov")(SimpleNamespace(load=load_roi, to_product=to_product))
