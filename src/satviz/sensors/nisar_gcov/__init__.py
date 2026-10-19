"""NISAR L2 GCOV (L-SAR and S-SAR): the first sensor plugin.

``load(scene, key, cache_dir)`` returns a generic `Product`; ``load_dataset`` returns the sensor's own working dataset
(a dict), which the older figures and the SAR recipes use directly.
"""
from __future__ import annotations

from types import SimpleNamespace

from satviz.core import Product, sensor
from satviz.sensors.nisar_gcov.facts import band_facts
from satviz.sensors.nisar_gcov.io import load_roi
from satviz.sensors.nisar_gcov.processing import stats

LAYER_KEYS = ("hh", "hv", "hh_ns", "hv_ns", "snr_hh", "snr_hv", "n_hh", "n_hv", "eta")


def to_product(d: dict, st: dict | None = None) -> Product:
    """Wrap a working dataset from `load_roi` as a generic `Product` (the dict stays available as ``native``)."""
    m = d["meta"]
    caveats = []
    if not m.calibrated:
        caveats.append(f"{m.radar_band}-band calibration metadata not yet populated: dB values are provisional and relative")
    return Product(
        key=d["band"], layers={k: d[k] for k in LAYER_KEYS}, x=d["x"], y=d["y"], epsg=d["epsg"], valid=d["valid"],
        meta=dict(platform="NISAR", sensor=m.instrument, label=f"{m.radar_band}-band", start=m.start, end=m.end,
                  resolution_m=m.posting_m, crs=m.crs, calibrated=m.calibrated),
        facts=band_facts(m, st or stats(d)), caveats=caveats, native=d,
        shared=dict(track=m.track, frame=m.frame, pass_direction=m.pass_direction, look_direction=m.look_direction,
                    polarisations=m.polarisations),
    )


def load(scene, key: str, cache_dir=None) -> Product:
    return to_product(load_roi(scene, key, cache_dir))


NISAR_GCOV = sensor("nisar_gcov")(SimpleNamespace(load=load, load_dataset=load_roi, to_product=to_product))
