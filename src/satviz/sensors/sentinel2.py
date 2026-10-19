"""Sentinel-2 L2A surface reflectance from Earth Search (public COGs, no login)."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from satviz.core import sensor
from satviz.sensors import stac_optical as so

SCL_CLOUD = (3, 8, 9, 10)  # cloud shadow, medium and high probability cloud, thin cirrus

SENTINEL2_L2A = so.OpticalCollection(
    sensor="sentinel2_l2a", provider="earth-search", collection="sentinel-2-l2a", platform="Sentinel-2", label="L2A",
    bands=dict(blue="blue", green="green", red="red", nir="nir", swir16="swir16", swir22="swir22"),
    reference_band="red", quality_asset="scl",
    cloud_mask=lambda q: np.isin(q, SCL_CLOUD), nodata_mask=lambda q: q == 0,
    attribution="Copernicus Sentinel", credit=lambda year: f"Contains modified Copernicus Sentinel data {year}",
)



def _describe(spec, data_dir, area=None):
    return so.describe(spec, SENTINEL2_L2A, area)


def _open(spec, canvas, area, data_dir, cache_dir=None, tag="job"):
    return so.open_on_canvas(spec, canvas, area, SENTINEL2_L2A, cache_dir)


def _search(spec, canvas, area, cache_dir=None):
    return so.search_rows(spec, SENTINEL2_L2A, area, canvas, cache_dir)


sensor("sentinel2_l2a")(SimpleNamespace(describe=_describe, open=_open, search=_search, kind="optical"))
