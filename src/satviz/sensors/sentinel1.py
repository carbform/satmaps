"""Sentinel-1 RTC (radiometrically terrain-corrected, linear gamma-nought power, VV/VH or HH/HV) from the Planetary Computer.

No noise floor is published with this product, so unlike NISAR nothing is screened for noise; the caveat says so.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from satviz.core import sensor
from satviz.sensors import stac_optical as so


def _bands_for(item: dict) -> dict:
    return dict(co="vv", cross="vh") if "vv" in item["assets"] else dict(co="hh", cross="hv")


def _caveats(platform, when, cloud_pct, group) -> list[str]:
    return [f"{platform}, {when:%d %b %Y}: no noise floor published, so weak returns (water, shadow) are not screened; "
            "no speckle filter."]


SENTINEL1_RTC = so.OpticalCollection(
    sensor="sentinel1_rtc", provider="planetary-computer", collection="sentinel-1-rtc", platform="Sentinel-1", label="RTC",
    bands=dict(co="vv", cross="vh"), reference_band="co", quality_asset=None,
    cloud_mask=lambda q: np.zeros(q.shape, bool), nodata_mask=lambda q: q == 0,
    # CC BY 4.0 (Planetary Computer collection metadata): the RTC processor (Catalyst) and the host are credited too
    attribution=("Copernicus Sentinel", "Catalyst"),
    credit=lambda year, platform: (f"Contains modified Copernicus Sentinel data {year}; "
                                   "RTC by Catalyst via Microsoft Planetary Computer (CC BY 4.0)"),
    kind="sar",
    group_key=lambda it: f"{it['properties']['datetime'][:10]}_{it['properties'].get('sat:relative_orbit', '')}",
    platform_of=lambda it: it["properties"].get("platform", "sentinel-1").title(),  # "sentinel-1d" -> "Sentinel-1D"
    bands_for=_bands_for, make_caveats=_caveats, nodata_value=-32768.0,
    extra_query=lambda src: {"sat:orbit_state": {"eq": src["orbit"]}} if "orbit" in src else None,
)


def _describe(spec, data_dir, area=None):
    return so.describe(spec, SENTINEL1_RTC, area)


def _open(spec, canvas, area, data_dir, cache_dir=None, tag="job"):
    return so.open_on_canvas(spec, canvas, area, SENTINEL1_RTC, cache_dir)


def _search(spec, canvas, area, cache_dir=None):
    return so.search_rows(spec, SENTINEL1_RTC, area, canvas, cache_dir)


sensor("sentinel1_rtc")(SimpleNamespace(describe=_describe, open=_open, search=_search, kind="sar"))
