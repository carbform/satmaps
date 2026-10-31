"""NISAR L2 GCOV (L-SAR and S-SAR): the first sensor plugin.

``load(scene, key, cache_dir)`` returns a generic `Product`; ``load_dataset`` returns the sensor's own working dataset
(a dict), which the older figures and the SAR recipes use directly.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from satmaps.core import Product, SourceInfo, sensor
from satmaps.radar import radar_facts
from satmaps.sensors.sar.nisar.canvas import decimation, find_group, raw_on_canvas, window
from satmaps.sensors.sar.nisar.canvas import describe as describe_file
from satmaps.sensors.sar.nisar.facts import band_facts
from satmaps.sensors.sar.nisar.io import assemble, load_raw, load_roi
from satmaps.sensors.sar.nisar.metadata import read_band_metadata
from satmaps.sensors.sar.nisar.processing import stats
from satmaps.sources import resolve_one_file

LAYER_KEYS = ("hh", "hv", "hh_ns", "hv_ns", "snr_hh", "snr_hv", "n_hh", "n_hv", "eta", "s2", "s3")  # (s2, s3: compact-pol only)


def to_product(d: dict, st: dict | None = None) -> Product:
    """Wrap a working dataset from `load_roi` as a generic `Product` (the dict stays available as ``native``)."""
    m = d["meta"]
    caveats = []
    if not m.calibrated:
        caveats.append(f"{m.radar_band}-band calibration metadata not yet populated: dB values are provisional and relative")
    return Product(
        key=d["band"], layers={k: d[k] for k in LAYER_KEYS if k in d}, x=d["x"], y=d["y"], epsg=d["epsg"], valid=d["valid"],
        meta=dict(platform="NISAR", sensor=m.instrument, label=f"{m.radar_band}-band", start=m.start, end=m.end,
                  resolution_m=m.posting_m, crs=m.crs, calibrated=m.calibrated,
                  **radar_facts(m.freq_ghz, m.radar_band), backscatter="gamma0, terrain-corrected",
                  attribution="NISAR", credit="NISAR L2 GCOV (NASA-ISRO) · γ⁰"),
        facts=band_facts(m, st or stats(d)), caveats=caveats, native=d,
        shared=dict(track=m.track, frame=m.frame, pass_direction=m.pass_direction, look_direction=m.look_direction,
                    polarisations=m.polarisations),
    )


def load(scene, key: str, cache_dir=None) -> Product:
    return to_product(load_roi(scene, key, cache_dir))


def sniff(path) -> bool:
    """A NISAR L2 GCOV HDF5 file (it has a science/*/GCOV group)."""
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != ".h5":
        return False
    try:
        find_group(path)
    except (ValueError, OSError):
        return False
    return True


def describe(spec, data_dir, area=None) -> SourceInfo:
    """Grid of the input's file, read from its coordinate arrays, to choose the canvas before reading pixels."""
    return describe_file(resolve_one_file(spec, data_dir))


def open_on_canvas(spec, canvas, area, data_dir, cache_dir=None, tag: str = "job") -> Product:
    """Read the part of the file that covers `canvas`, then copy (aligned grids) or resample every layer onto it."""
    path = resolve_one_file(spec, data_dir)
    group = find_group(path)
    win = window(path, group, canvas)
    raw = load_raw(path, win, cache_dir, f"{tag}_{path.stem[-28:]}", decimation(path, group, canvas))
    d = assemble(raw_on_canvas(raw, canvas), spec.key)
    d["meta"] = read_band_metadata(path, win)
    product = to_product(d)
    product.meta["resolution_m"] = canvas.res  # the size the figure is drawn at, as the other readers state it
    return product


NISAR_GCOV = sensor("nisar")(SimpleNamespace(
    load=load, load_dataset=load_roi, to_product=to_product, describe=describe, open=open_on_canvas, sniff=sniff, kind="sar"))
