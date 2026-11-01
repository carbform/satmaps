import numpy as np
import pytest

from satmaps.area import Area, AreaError, utm_epsg
from satmaps.grid import is_aligned, to_canvas


def test_utm_zone_from_centre():
    assert utm_epsg(27.57, 94.9) == 32646 and utm_epsg(-33.9, 18.4) == 32734


def test_point_and_radius_makes_a_square():
    a = Area.from_config({"center": [27.57, 94.90], "radius_km": 5, "resolution_m": 10})
    assert a.epsg == 32646
    assert a.xmax - a.xmin == pytest.approx(10_000) and a.ymax - a.ymin == pytest.approx(10_000)
    c = a.canvas()
    assert (c.width, c.height) == (1000, 1000) and c.res == 10


def test_size_km_and_bbox():
    a = Area.from_config({"center": [27.5, 94.9], "size_km": [6, 4], "resolution_m": 20})
    assert a.canvas().width == 300 and a.canvas().height == 200
    b = Area.from_config({"bbox": [94.8, 27.5, 95.0, 27.7], "resolution_m": 30})
    c = b.canvas()
    w, s, e, n = c.lonlat_bbox()
    assert w <= 94.8 and e >= 95.0 and s <= 27.5 and n >= 27.7  # the canvas covers the box


@pytest.mark.parametrize("cfg, msg", [
    ({}, "exactly one of"),
    ({"center": [1, 2], "bbox": [0, 0, 1, 1]}, "exactly one of"),
    ({"center": [1, 2]}, "radius_km or size_km"),
    ({"center": [1, 2], "radius_km": 1, "size_km": [1, 1]}, "radius_km or size_km"),
    ({"bbox": [95, 27, 94, 28]}, "west < east"),
    ({"center": [1, 2], "radius_km": 1, "nope": 1}, "unknown key"),
    ({"center": [1, 2], "radius_km": 1, "crs": "utm"}, "EPSG"),
])
def test_bad_area_is_explained(cfg, msg):
    with pytest.raises(AreaError, match=msg):
        Area.from_config(cfg)


def test_no_resolution_and_huge_canvas_are_refused():
    a = Area.from_config({"center": [27.5, 94.9], "radius_km": 100})
    with pytest.raises(AreaError, match="no pixel size"):
        a.canvas()
    with pytest.raises(AreaError, match="coarser"):
        a.canvas(1)


def test_canvas_snaps_to_a_reference_grid():
    a = Area.from_config({"center": [27.5, 94.9], "radius_km": 1, "resolution_m": 10})
    sx, sy = 555125.0 + 10 * np.arange(200), 3347995.0 - 10 * np.arange(200)  # real NISAR S-band phase: centres at 5 mod 10
    c = a.canvas(phase=(sx[0], sy[0]))
    assert is_aligned(sx, sy, 32646, c)
    assert (c.x[0] - 5) % 10 == 0 and (c.y[0] - 5) % 10 == 0


def _src(n=40, res=10.0):
    x = 500005.0 + res * np.arange(n)
    y = 3000005.0 - res * np.arange(n)
    return x, y, np.add.outer(np.arange(n), 100 * np.arange(n)).astype(np.float32)


def test_aligned_copy_is_exact_and_fills_outside():
    x, y, a = _src()
    from satmaps.area import Canvas

    c = Canvas(32646, x[0] - 5 + 10 * 5, y[0] + 5 - 10 * 3, 10.0, 50, 50)  # starts at src col 5 / row 3, runs past the edge
    out = to_canvas(a, x, y, 32646, c)
    assert np.array_equal(out[:37, :35], a[3:40, 5:40])
    assert np.isnan(out[37:]).all() and np.isnan(out[:, 35:]).all()
    m = to_canvas((a > 100).astype(np.uint8), x, y, 32646, c, "nearest", fill=0)
    assert m.dtype == np.uint8 and m[0, 0] == int(a[3, 5] > 100) and m[-1, -1] == 0


def test_half_pixel_shift_is_bilinear():
    x, y, a = _src()
    from satmaps.area import Canvas

    c = Canvas(32646, x[0] - 5 + 5, y[0] + 5, 10.0, 20, 20)  # shifted half a pixel east
    out = to_canvas(a, x, y, 32646, c)
    assert out[5, 5] == pytest.approx((a[5, 5] + a[5, 6]) / 2)


def test_coarser_canvas_block_averages_linear_values():
    x, y, a = _src()
    from satmaps.area import Canvas

    c = Canvas(32646, x[0] - 5, y[0] + 5, 20.0, 20, 20)
    out = to_canvas(a, x, y, 32646, c)
    assert out[2, 3] == pytest.approx(a[4:6, 6:8].mean())


def test_overlap_share_detects_coverage_and_disjoint_rings():
    from satmaps.autoarea import overlap_share

    r1 = [(94.0, 27.0), (95.0, 27.0), (95.0, 28.0), (94.0, 28.0), (94.0, 27.0)]
    # identical ring -> 100% overlap
    assert overlap_share(r1, r1) == pytest.approx(1.0)
    # partially overlapping ring
    r2 = [(94.5, 27.0), (95.5, 27.0), (95.5, 28.0), (94.5, 28.0), (94.5, 27.0)]
    assert 0.4 < overlap_share(r1, r2) < 0.6
    # completely disjoint ring -> 0.0
    r3 = [(75.0, 12.0), (76.0, 12.0), (76.0, 13.0), (75.0, 13.0), (75.0, 12.0)]
    assert overlap_share(r1, r3) == 0.0
    # None handling
    assert overlap_share(r1, None) == 0.0
    assert overlap_share(None, None) == 0.0
