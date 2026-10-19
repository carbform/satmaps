"""Landsat Collection 2 Level 2 surface reflectance (Landsat 8 and 9) from the Planetary Computer (anonymous token).

Earth Search lists Landsat too, but its files sit in a requester-pays bucket, so the Planetary Computer is the free route.
"""
from __future__ import annotations

from types import SimpleNamespace

from satviz.core import sensor
from satviz.sensors import stac_optical as so

LANDSAT_C2L2 = so.OpticalCollection(
    sensor="landsat_c2l2", provider="planetary-computer", collection="landsat-c2-l2", platform="Landsat", label="Collection 2 L2",
    bands=dict(blue="blue", green="green", red="red", nir="nir08", swir16="swir16", swir22="swir22"),
    reference_band="red", quality_asset="qa_pixel",
    # QA_PIXEL bits: 0 fill, 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow. Value 0 only occurs outside the scene.
    cloud_mask=lambda q: (q & 0b11110) != 0, nodata_mask=lambda q: (q == 0) | ((q & 1) != 0),
    attribution="U.S. Geological Survey",
    credit=lambda year, platform: f"{platform} imagery courtesy of the U.S. Geological Survey",
    group_key=lambda it: f"{it['properties']['datetime'][:10]}_{it['properties'].get('landsat:wrs_path', '')}",
    platform_of=lambda it: it["properties"].get("platform", "landsat").replace("landsat-", "Landsat "),
)


def _describe(spec, data_dir, area=None):
    return so.describe(spec, LANDSAT_C2L2, area)


def _open(spec, canvas, area, data_dir, cache_dir=None, tag="job"):
    return so.open_on_canvas(spec, canvas, area, LANDSAT_C2L2, cache_dir)


def _search(spec, canvas, area, cache_dir=None):
    return so.search_rows(spec, LANDSAT_C2L2, area, canvas, cache_dir)


sensor("landsat_c2l2")(SimpleNamespace(describe=_describe, open=_open, search=_search, kind="optical"))
