import numpy as np
import pytest

from satmaps.recipes.sar_fcc import NOISE_RGB, OUTSIDE_RGB, fcc_rgba, shared_lims
from satmaps.sensors.sar.nisar.io import assemble
from tests.conftest import make_raw


def test_noisy_pixels_are_grey_not_signal(ds):
    rgba, lims, ok = fcc_rgba(ds)
    noisy = ds["valid"] & ~ok
    assert noisy.any()
    assert (rgba[noisy][:, :3] == NOISE_RGB).all()
    assert rgba.dtype == np.uint8 and (rgba[..., 3] == 255).all()


def test_outside_mask_pixels_get_their_own_colour():
    raw = make_raw()
    raw["mask"][:5, :5] = 0
    d = assemble(raw, "S")
    rgba, _, _ = fcc_rgba(d)
    assert (rgba[:5, :5, :3] == OUTSIDE_RGB).all()


def test_limits_are_percentiles_of_clean_pixels(ds):
    _, lims, _ = fcc_rgba(ds)
    assert set(lims) == {"HH", "HV", "ratio"}
    assert all(lo < hi for lo, hi in lims.values())


def test_explicit_limits_override_percentiles(ds):
    fixed = {"HH": (-20.0, 0.0), "HV": (-30.0, -5.0), "ratio": (0.0, 20.0)}
    _, lims, _ = fcc_rgba(ds, lims_in=fixed)
    assert lims == fixed


def test_shared_limits_lie_between_the_individual_ones():
    a, b = assemble(make_raw(1), "S"), assemble(make_raw(2, shift_db=4.0), "L")
    la, lb, shared = fcc_rgba(a)[1], fcc_rgba(b)[1], shared_lims([a, b])
    for k in ("HH", "HV", "ratio"):
        lo, hi = shared[k]
        assert min(la[k][0], lb[k][0]) - 0.5 <= lo <= max(la[k][0], lb[k][0]) + 0.5
        assert min(la[k][1], lb[k][1]) - 0.5 <= hi <= max(la[k][1], lb[k][1]) + 0.5


def test_pooled_stretch_makes_same_input_same_colour(ds):
    lims = shared_lims([ds, ds])
    r1 = fcc_rgba(ds, lims_in=lims)[0]
    r2 = fcc_rgba(ds, lims_in=lims)[0]
    assert np.array_equal(r1, r2)


def test_the_channels_can_be_assigned_in_any_order(ds):
    default, lims, _ = fcc_rgba(ds)
    swapped, lims2, _ = fcc_rgba(ds, channels=("cross", "co", "ratio"))
    assert lims2 == lims  # the stretch belongs to the quantity, not to the colour it is drawn in
    ok = (default[..., :3] != NOISE_RGB).any(-1) & (default[..., :3] != OUTSIDE_RGB).any(-1)
    assert (swapped[..., 0][ok] == default[..., 1][ok]).all() and (swapped[..., 1][ok] == default[..., 0][ok]).all()
    assert (swapped[..., 2][ok] == default[..., 2][ok]).all()


def test_a_recipe_name_with_channels_gives_a_composite_that_says_what_is_where(scene):
    from satmaps.core import RECIPES, SENSORS
    from satmaps.registry import load_builtin

    load_builtin()
    p = SENSORS["nisar"].load(scene, "S")
    r = RECIPES.get_or_raise("sar_fcc:cross,co,cross").render(p)
    assert r.title == "FCC  ·  HV / HH / HV" and not r.components
    assert [i.text for i in r.legend[:3]] == ["RED = HV", "GREEN = HH", "BLUE = HV"]
    assert (RECIPES["sar_fcc"].render(p).rgba != r.rgba).any()
    with pytest.raises(KeyError, match="three of co, cross, ratio"):
        RECIPES.get_or_raise("sar_fcc:co,cross")


def test_sar_presets_explain_actual_image_colors(scene):
    from satmaps.core import RECIPES, SENSORS
    from satmaps.registry import load_builtin

    load_builtin()
    p = SENSORS["nisar"].load(scene, "S")

    # Vegetation preset
    r_veg = RECIPES.get_or_raise("sar_fcc:cross,co,ratio").render(p)
    texts_veg = [i.text for i in r_veg.legend]
    assert any("WARM / RED = DENSE VEGETATION" in t for t in texts_veg)
    assert any("YELLOW = BUILT-UP / ROUGH GROUND" in t for t in texts_veg)
    assert texts_veg[0] == "RED = HV  (CANOPY / VOLUME)"

    # Urban preset
    r_urb = RECIPES.get_or_raise("sar_fcc:co,ratio,cross").render(p)
    texts_urb = [i.text for i in r_urb.legend]
    assert any("YELLOW / ORANGE = BUILT-UP URBAN" in t for t in texts_urb)
    assert any("BLUE / CYAN = VEGETATION & CANOPY" in t for t in texts_urb)
    assert texts_urb[0] == "RED = HH  (STRUCTURE / DOUBLE-BOUNCE)"

    # Water preset
    r_wat = RECIPES.get_or_raise("sar_fcc:ratio,co,cross").render(p)
    texts_wat = [i.text for i in r_wat.legend]
    assert any("RED = ROUGH / TEXTURED TERRAIN" in t for t in texts_wat)
    assert any("CYAN = VEGETATED CANOPY" in t for t in texts_wat)
