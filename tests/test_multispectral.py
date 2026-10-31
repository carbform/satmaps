"""The optical template's bands arrangement: one optical product band by band, no comparison."""
from types import SimpleNamespace

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from satviz.arrangements import bands as bands_arr  # noqa: E402
from satviz.config import InputSpec  # noqa: E402
from satviz.core import THEMES, BandInfo, Product  # noqa: E402
from satviz.job import FigureSpec, load_job  # noqa: E402
from satviz.layout import LayoutError, default_layout  # noqa: E402
from satviz.recipes import bands as rb  # noqa: E402
from satviz.registry import load_builtin  # noqa: E402
from satviz.run import run_job  # noqa: E402
from satviz.templates import TemplateError  # noqa: E402
from tests.rasters import needs_rasterio  # noqa: E402

load_builtin()
from satviz.core import TEMPLATES  # noqa: E402
from tests.test_sentinel2 import safe_folder  # noqa: E402

N = 24


def product(with_table=True, layers=("B02", "B03", "B04", "B08", "B12")):
    """A small optical product: a gradient per band, brighter at longer wavelengths, one invalid corner."""
    ramp = np.linspace(0.0, 1.0, N * N, dtype=np.float32).reshape(N, N)
    arrays = {k: ramp * (0.1 + 0.07 * i) for i, k in enumerate(layers)}
    roles = {"blue": "B02", "green": "B03", "red": "B04", "nir": "B08", "swir22": "B12"}
    arrays |= {r: arrays[c] for r, c in roles.items() if c in arrays}
    valid = np.ones((N, N), bool)
    valid[:3, :3] = False
    infos = (BandInfo("B02", "B02", "blue", 489.1, (454.0, 525.0), 10.0), BandInfo("B03", "B03", "green", 560.6, (541.0, 581.0), 10.0),
             BandInfo("B04", "B04", "red", 666.5, (648.0, 686.0), 10.0), BandInfo("B08", "B08", "nir", 834.6, (776.0, 908.0), 10.0),
             BandInfo("B12", "B12", "swir 2", 2191.3, (2066.0, 2312.0), 20.0))
    return Product(key="S2", layers=arrays, x=500000 + 10 * np.arange(N) + 5.0, y=3000000 - 10 * np.arange(N) - 5.0, epsg=32646,
                   valid=valid, kind="optical", bands=infos if with_table else (),
                   meta=dict(platform="Sentinel-2C", label="L2A", sensor="MSI", start=__import__("datetime").datetime(2026, 9, 29, 4, 15),
                             end=__import__("datetime").datetime(2026, 9, 29, 4, 15), resolution_m=10.0, crs="UTM 46N",
                             attribution="Copernicus Sentinel", credit="Contains modified Copernicus Sentinel data 2026", time_known=True),
                   facts=SimpleNamespace(date="29 Sep 2026"), caveats=["Sentinel-2C, 29 Sep 2026: 3% cloud in view."])


def test_bands_come_from_the_table_in_wavelength_order_or_fall_back_to_roles_without_inventing_wavelengths():
    assert [b.id for b in rb.bands_of(product())] == ["B02", "B03", "B04", "B08", "B12"]
    fallback = rb.bands_of(product(with_table=False))
    assert [b.layer for b in fallback] == ["blue", "green", "red", "nir", "swir22"]
    assert all(b.wavelength_nm is None and b.range_nm is None and b.resolution_m is None for b in fallback)


def test_label_states_id_wavelength_native_size_and_per_band_limits():
    b4 = BandInfo("B04", "B04", "red", 666.5, (648.0, 686.0), 10.0)
    assert rb.label_lines(b4) == "B04 · RED\n666 NM · 10 M"  # 666.5 rounds half to even
    assert rb.label_lines(b4, (0.0149, 0.3071)) == "B04 · RED\n666 NM · 10 M\n0.01–0.31"
    liss = BandInfo("B3", "red", "red", None, (620.0, 680.0), 5.0)  # only a nominal range: shown as a range, not a centre
    assert rb.label_lines(liss) == "B3 · RED\n620–680 NM · 5 M"
    assert rb.label_lines(BandInfo("RED", "red", "red")) == "RED"  # no table, nothing invented


def test_grey_is_linear_between_the_printed_limits_and_invalid_pixels_are_the_no_data_colour():
    arr = np.array([[0.0, 0.1, 0.2, 0.3], [0.5, np.nan, 0.15, 0.25]], np.float32)
    valid = np.ones_like(arr, bool)
    valid[0, 0] = False
    rgba = rb.grey_rgba(arr, valid, 0.1, 0.3)
    assert tuple(rgba[0, 0, :3]) == rb.OUTSIDE_RGB and tuple(rgba[1, 1, :3]) == rb.OUTSIDE_RGB  # invalid, and NaN
    assert rgba[0, 1, 0] == 0 and rgba[0, 3, 0] == 255 and rgba[1, 0, 0] == 255  # at the limits, and clipped above
    assert rgba[0, 2, 0] == 127 and rgba[1, 2, 0] == 63 and rgba[1, 3, 0] == 191  # linear: no gamma
    ok = valid & np.isfinite(arr)
    assert (rgba[ok][:, 0] == rgba[ok][:, 1]).all() and (rgba[ok][:, 1] == rgba[ok][:, 2]).all()  # grey: no colour added to data
    assert (rgba[..., 3] == 255).all()


def test_limits_pool_all_bands_unless_asked_per_band():
    p = product()
    arrays = [p.layers[b.layer] for b in rb.bands_of(p)]
    lo, hi = rb.limits(arrays, p.valid)
    own = [rb.limits([a], p.valid) for a in arrays]
    assert own[0][1] < hi <= own[-1][1] + 1e-9  # the pool's top lies between the dimmest and the brightest band's own top
    assert len({round(o[1], 6) for o in own}) == len(own)  # per-band limits differ band to band, which is what `per-band` is for


JOB = SimpleNamespace(inputs={"S2": InputSpec("S2", "sentinel2", "", {}), "L4": InputSpec("L4", "liss4", "", {}),
                              "E": InputSpec("E", "eos04", "", {})}, path="job.toml")


def test_the_template_gives_every_input_its_own_figure_and_refuses_what_it_cannot_show():
    t = TEMPLATES["optical"]
    assert t.plan(FigureSpec("optical", ("S2", "L4"), arrangement="bands"), JOB) == [("S2",), ("L4",)]
    with pytest.raises(TemplateError, match="no spectral bands; use template 'sar'"):
        t.plan(FigureSpec("optical", ("S2", "E"), arrangement="bands"), JOB)
    with pytest.raises(TemplateError, match="arrangement must be one of single, compare, grid"):
        TEMPLATES["sar"].plan(FigureSpec("sar", ("E",), arrangement="bands"), JOB)  # bands belongs to the optical template only


def test_resolve_says_the_bands_and_nothing_about_comparison():
    r = TEMPLATES["optical"].resolve(FigureSpec("optical", ("S2",), arrangement="bands", composites=("true_colour",)), ("S2",), {"S2": product()},
                                           SimpleNamespace(name="Dibrugarh", region="Dibrugarh, Assam"))
    assert r.arrangement == "bands" and r.recipes == {} and r.caveats == ()  # no relation notes, no recipes per input
    assert r.text["subtitle"] == "SENTINEL-2C L2A · 5 BANDS  ·  DIBRUGARH, ASSAM" and r.options["composites"] == ("true_colour",)


@pytest.mark.parametrize("theme", sorted(THEMES))
def test_every_theme_renders_the_bands_page(theme, scene, tmp_path):
    out = bands_arr.render(scene, {"S2": product()}, tmp_path, default_layout("bands"), input="S2", theme=theme)[0]
    assert out.exists() and out.stat().st_size > 5000 and THEMES[theme].tag in out.name and "_Bands_" in out.name


def test_composites_are_opt_in_and_a_missing_band_is_refused(scene, tmp_path):
    for sub in ("plain", "with"):
        (tmp_path / sub).mkdir()
    plain = bands_arr.render(scene, {"S2": product()}, tmp_path / "plain", default_layout("bands"), input="S2")[0]
    extra = bands_arr.render(scene, {"S2": product()}, tmp_path / "with", default_layout("bands"), input="S2",
                             composites=("true_colour", "nir_fcc"))[0]
    assert plain.exists() and extra.exists() and plain.read_bytes() != extra.read_bytes()  # two more panels were drawn
    no_blue = product(layers=("B03", "B04", "B08", "B12"))
    with pytest.raises(LayoutError, match="blue"):  # true colour needs a blue band this product does not have
        bands_arr.render(scene, {"S2": no_blue}, tmp_path, default_layout("bands"), input="S2", composites=("true_colour",))


def test_a_sar_product_and_a_bad_stretch_are_refused(scene, tmp_path):
    sar = product()
    sar.kind = "sar"
    with pytest.raises(LayoutError, match="shows spectral bands"):
        bands_arr.render(scene, {"S2": sar}, tmp_path, default_layout("bands"), input="S2")
    with pytest.raises(LayoutError, match="stretch must be"):
        bands_arr.render(scene, {"S2": product()}, tmp_path, default_layout("bands"), input="S2", stretch="auto")


def test_a_product_without_a_band_table_still_renders_from_its_roles(scene, tmp_path):
    out = bands_arr.render(scene, {"S2": product(with_table=False)}, tmp_path, default_layout("bands"), input="S2", stretch="per-band")[0]
    assert out.exists()


@needs_rasterio
def test_job_runs_the_bands_arrangement_on_a_local_sentinel_2_product(tmp_path):
    from pyproj import Transformer

    from tests.rasters import EPSG, X0, Y0

    safe_folder(tmp_path)
    lon, lat = Transformer.from_crs(f"EPSG:{EPSG}", "EPSG:4326", always_xy=True).transform(X0 + 500, Y0 - 500)
    job = tmp_path / "job.toml"
    job.write_text(f'''
[scene]
name = "Test"
region = "Nowhere"
[area]
center = [{lat}, {lon}]
size_km = [0.6, 0.6]
resolution_m = 10
[[inputs]]
id = "S2"
sensor = "sentinel2"
source = {{ path = "S2C_MSIL2A_test.SAFE" }}
[[figures]]
name = "bands"
template = "optical"
arrangement = "bands"
inputs = ["S2"]
composites = ["true_colour"]
stretch = "per-band"
theme = ["minimal", "xkcd"]
''')
    paths = run_job(load_job(job, tmp_path), tmp_path / "out")
    assert [p.name for p in paths] == ["bands_Minimal.png", "bands_Xkcd.png"] and all(p.stat().st_size > 10_000 for p in paths)


def test_any_three_bands_make_a_false_colour_composite_each_stretched_on_its_own():
    from satviz.core import RECIPES

    p = product()
    r = RECIPES.get_or_raise("fcc:B12,B08,B03").render(p)
    assert r.title == "FCC  ·  B12 / B08 / B03" and set(r.lims) == {"R", "G", "B"}
    assert [i.text for i in r.legend[:3]] == ["RED = B12 SWIR 2", "GREEN = B08 NIR", "BLUE = B03 GREEN"]
    lo, hi = r.lims["R"]
    assert lo < hi and r.rgba.shape == p.valid.shape + (4,) and (r.rgba[3:, 3:, 0] > 0).any()
    assert RECIPES.get_or_raise("fcc:B12,B08,B03").needs == ("B12", "B08", "B03")


def test_the_familiar_composites_keep_their_own_recipe_and_a_bad_spec_is_refused():
    from satviz.core import RECIPES

    assert RECIPES.get_or_raise("fcc:red,green,blue") is RECIPES["true_colour"]
    assert RECIPES.get_or_raise("fcc:nir,red,green") is RECIPES["nir_fcc"]
    with pytest.raises(KeyError, match="three band names"):
        RECIPES.get_or_raise("fcc:red,green")
