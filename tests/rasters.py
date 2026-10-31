"""Small GeoTIFF fixtures shared by the sensor tests: a 100 x 100 raster in UTM 46N and a 60 x 60 canvas inside it."""
import importlib.util

import pytest

from satmaps.area import Area

needs_rasterio = pytest.mark.skipif(importlib.util.find_spec("rasterio") is None, reason="pip install -e '.[rasters]'")

EPSG = 32646
X0, Y0 = 500000.0, 3000000.0
AREA = Area(EPSG, X0 + 100, Y0 - 700, X0 + 700, Y0 - 100, 10)  # 60 x 60 canvas inside the rasters below


def write_tif(path, arrays, res=10.0, size=100, nodata=None):
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", height=size, width=size, count=len(arrays), dtype=arrays[0].dtype,
                       crs=f"EPSG:{EPSG}", transform=from_origin(X0, Y0, res, res), nodata=nodata) as dst:
        for i, a in enumerate(arrays, 1):
            dst.write(a, i)
