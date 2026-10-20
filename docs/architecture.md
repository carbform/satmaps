# Architecture: from one NISAR figure set to a multi-sensor infographic tool

Goal: quickly produce social, publication and newspaper-style infographics from NISAR, Sentinel-2, Landsat and
other well-known satellites, with titles, names and credits customisable, in a few visual aesthetics.

## Independent axes

Any combination should work. (Updated Oct 2026: templates are now content scenarios and the old page layouts are *arrangements*;
see [pipelines.md](pipelines.md).)

| Axis | Question it answers | Examples |
|---|---|---|
| **Sensor** (reader) | Where do the pixels and facts come from? | `nisar_gcov`, `eos04`, `sentinel1_grd`, `sentinel2_l2a`, `liss4` |
| **Recipe** | How do layers become an image, a legend and caveats? | `sar_fcc`, `true_colour`, `nir_fcc`, `ndvi`, `ndwi` |
| **Template** | What is the figure about, and how do its products relate? | `optical`, `sar`, `optical_sar`, `sar_vs_sar` |
| **Arrangement** | Where do the products sit on the page? | `single`, `compare`, `grid` |
| **Theme** | What does the chrome look like? | `minimal`, `neo_retro`, `neo_brutal`, `newspaper`, `xkcd` |

Rule carried over from `design-language.md`: **style the chrome, never the data.** Themes never touch data panels,
and no theme can hide the caveat strip.

```
 sensor reader ──► Product ──► recipe ──► Rendered(rgba, legend, caveats)
                      │                         │
                      └─ facts/placeholders     ▼
                                    template(theme, layout.toml, [Rendered…]) ──► PNG / PDF
```

## Core types (`satviz.core`)

- `Product`: named float layers, a georeference (`x`, `y`, `crs`), a `valid` mask, generic `meta`
  (platform, sensor, start, end, resolution_m, crs), `facts` (a sensor-specific namespace for placeholders) and
  `caveats` (list of strings the sensor itself insists on, e.g. "S-band calibration not populated", "cloud 38%").
- `Rendered`: `rgba`, `extent`, `legend` (list of colour/text items), `caveats`.
- Registries with decorators: `@sensor("nisar_gcov")`, `@recipe("sar_fcc")`, `@theme("neo_retro")`, `@template("compare")`.
  Third-party additions are one file each.

## Package layout (target)

```
src/satviz/
  core.py            Product, Rendered, registries
  sensors/           nisar_gcov.py (from io/metadata/processing)  sentinel2.py  landsat.py  (optional extra)
  recipes/           sar_fcc.py (from composite)  optical.py (true colour, NIR, NDVI, NDWI)
  themes/            minimal.py  neo_retro.py  neo_brutal.py  editorial.py   (tokens + chrome primitives)
  templates/         single.py  compare.py  clean.py  publication.py  newspaper.py
  layout.py          TOML wording, placeholders (generic keys + per-product namespaces)
  search/            stac.py (Earth Search: bbox + date -> items; optional extra)
  grid.py            common-grid resampling for cross-sensor comparison
  cli.py
layouts/             wording files; recipes and sensors supply defaults for legend and caveats
configs/             [[inputs]] sensor=…, path|stac=…, roi (lon/lat bbox, or rows/cols for NISAR)
```

Dependencies: core stays `numpy, matplotlib, h5py, pyproj, scipy`. Optical adds `rasterio` and `pystac-client`
under extras `[optical]` / `[stac]`, so installing for NISAR-only use needs no GDAL.

## Decisions taken

- **Rename** to `satviz`; `nisar-viz` console script, `python -m nisar_viz` and `NISAR_DATA_DIR` stay as aliases.
- **Optical input**: STAC search against Earth Search (public, no auth) from the start, with local files also accepted.
- **Aesthetics first**: `neo_retro` (existing), `minimal`, `neo_brutal`, `editorial` (newspaper structure).

## Constraints that shape the design

1. **No output change in Phase 1.** Golden renders of all six existing figures are diffed after the refactor.
2. **Honesty survives every theme.** Caveats come from the product/recipe, are mandatory on every template, and
   are drawn by a shared helper that themes only restyle.
3. **Cross-sensor comparison needs a common grid.** The current L/S alignment is a hand-measured pixel offset.
   `grid.py` resamples any two products onto one grid (bilinear for continuous, nearest for classes).
4. **Optical scaling comes from product metadata**, never hardcoded: Sentinel-2 L2A processing baseline ≥ 04.00
   has a BOA offset; Landsat C2 L2 has per-band scale and offset in MTL. Verify against real files when writing readers.
5. **Credits are sensor-supplied defaults**, user-overridable only by adding to them: Copernicus requires
   "Contains modified Copernicus Sentinel data [year]"; Landsat is "courtesy of the U.S. Geological Survey";
   NISAR keeps the current wording.
6. **Newspaper style is inspired by, not copied from**, real publications: kicker, headline, dek, byline, caption,
   source line, column rules. No real masthead, name or branding.

## Phases

| Phase | Content | Done when |
|---|---|---|
| 1 | Rename; `core.py`; NISAR becomes a sensor plugin; `composite` becomes recipe `sar_fcc`; theme registry with `neo_retro` as the only entry; templates take a list of products; context split into generic + per-product | golden diff of all 6 figures is empty, tests green, CLI names unchanged |
| 2 (done) | `minimal` and `neo_brutal` themes (done: one `Theme` token set drives shared chrome); `--theme`; `single` and `compare` templates are theme-agnostic; per-theme preview gallery | same figure renders in 3 themes without code edits |
| 3 | Sentinel-2 L2A + Landsat C2 L2 readers; STAC search; optical recipes; `grid.py`; SAR-vs-optical compare (NISAR 2026-09-25 vs nearest cloud-free S2 over Dibrugarh) | cross-sensor figure renders with correct credits and caveats |
| 4 | `editorial` theme and `newspaper` template; template research for structure | newspaper page renders from the same inputs |
| 5 | Other sensors (Sentinel-1 GRD, MODIS, …) as needed; docs; gallery; CI | one new sensor added by one file |

## Status after Phase 2

- `[[inputs]]` config (`[bands.X]` still parsed); `build_context_products` builds placeholders from products
  (generic facts, what sensors share, one namespace per input id).
- `single` and `compare` templates take products and a recipe by name; layouts may omit `how_to_read.items` and
  `notes.lines` to use the recipe's legend and the products' caveats (more than 3 caveats is an error, never truncated).
- Still NISAR-shaped, to be migrated when a second sensor needs them: `clean` and `publication` figures, `BandMeta`
  facts such as `{L.noisy_hv_pct}`, the "5 KM" scale bar, and lon/lat ROI (`rows`/`cols` only so far).
- `compare` requires both inputs on one grid; `grid.py` resampling arrives in Phase 3.

# Phase 3 design: one job file, an area that defines the canvas, any sensor pair

Requirement: the user fills in a config file, runs one command, and gets figures. Optical (Sentinel-2, Landsat,
ResourceSat, ...) and SAR (NISAR, Sentinel-1, ALOS PALSAR, ...) in any combination, for a place given as a bounding
box, a point plus radius, or (later) a place name.

## Principles

1. **One schema, many presets.** Separate schemas per kind would need to be merged the moment a figure mixes SAR and
   optical. Instead there is one "job" file, and `satviz init <preset>` writes a filled-in starter for each common case
   (`optical`, `sar`, `sar-vs-optical`, `before-after`, `multi-sensor-grid`).
2. **The area defines the canvas.** `[area]` fixes a CRS (the UTM zone of its centre), an extent and a pixel size.
   Every sensor reader returns its data already on that grid. So any two inputs can be compared, because they share a
   grid by construction, and the current hand-measured row/column offsets go away. Native ROI rows/cols stay as an
   escape hatch for NISAR.
3. **Recipes depend on a layer vocabulary, not on a sensor.** Readers normalise to a small shared vocabulary:
   - SAR: `co`, `cross` (linear power, gamma0), `noise_floor`, `valid`. NISAR HH/HV and Sentinel-1 VV/VH both map here.
   - Optical: `blue green red nir swir1 swir2` as surface reflectance 0..1, plus `cloud`/`valid`.

   A recipe declares the vocabulary it needs (`sar_fcc` needs SAR, `true_colour` needs optical). This is what removes
   the permutation problem: N sensors x M recipes x K templates x L themes is N+M+K+L pieces of code, not a product.
4. **Unknown satellites need no code.** A `geotiff` sensor takes a band map in the config
   (`bands = {red = 3, green = 2, blue = 1, nir = 4}`, `scale`, `offset`, `kind = "optical"`). ResourceSat LISS-III/IV,
   PlanetScope or ALOS RTC GeoTIFFs work this way. A named plugin is only written when a product needs real logic
   (metadata, quality masks, noise floors): `nisar_gcov`, `sentinel2_l2a`, `landsat_c2l2`, `sentinel1_rtc`.
5. **Data sources are separate from sensors.** `source = { path = "..." }` (a file or glob) or
   `source = { stac = "earth-search", collection = "sentinel-2-l2a", date = "2026-09-25", window_days = 5,
   max_cloud = 20, pick = "closest" }`. NISAR is local files first (the archive needs an Earthdata login).
   STAC picks are written to a `<job>.lock.json` next to the outputs (item ids, dates, cloud), so a figure can be
   reproduced exactly and credits can be generated from what was actually used.
6. **Honesty and credits are sensor-supplied.** Calibration state, noise screening, cloud fraction, L1C vs L2A, and
   the required attributions (Copernicus, USGS, NISAR) come from the reader and recipe. The config can add to them,
   not remove them.

## Job file (target)

```toml
extends = "defaults.toml"           # optional: author, website, default theme shared by many jobs

[scene]
name = "Brahmaputra"
region = "Dibrugarh, Assam"

[area]                              # exactly one of:
center = [27.57, 94.90]             #   point + radius (square of side 2 x radius)
radius_km = 12
# bbox = [94.7, 27.4, 95.1, 27.7]   #   west, south, east, north (WGS84)
# place = "Dibrugarh"               #   geocoded (optional network call), with radius_km
resolution_m = 10                   # canvas pixel size; default: the finest input

[[inputs]]
id = "sar"
sensor = "nisar_gcov"
source = { path = "data/NISAR_L2_*_GCOV_*.h5" }

[[inputs]]
id = "opt"
sensor = "sentinel2_l2a"
source = { stac = "earth-search", date = "2026-09-25", window_days = 5, max_cloud = 20 }

[[figures]]
template = "compare"               # single | compare | grid | publication | newspaper
inputs = ["sar", "opt"]            # or inputs = ["a","b","c"], pairs = "all" for every unordered pair
recipes = { sar = "sar_fcc", opt = "true_colour" }
theme = ["neo_retro", "minimal"]
text = { title = "River Brahmaputra", subtitle = "SAR and optical, same day" }   # overrides the template's wording
```

## CLI

```
satviz init sar-vs-optical -o job.toml     write a starter job file for a preset
satviz search job.toml                     list matching scenes (id, date, cloud %) without downloading
satviz run job.toml                        resolve inputs, read onto the canvas, render every [[figures]] entry
satviz list                                sensors, recipes, themes, templates
satviz render ...                          the current NISAR-only command, kept as is
```

## Phase 3 split

| Step | Content | Done when |
|---|---|---|
| 3a | `[area]` (bbox, point+radius), canvas grid + resampling (`grid.py`), job file loader with `extends`, `satviz run` and `init`; NISAR read by bbox instead of rows/cols; recipes declare vocabularies; layouts ship inside the package | NISAR L-vs-S job file reproduces today's figures with bbox in place of row/col ROIs (equal within resampling tolerance, with a documented difference) |
| 3b | `geotiff` sensor with band maps; `sentinel2_l2a` via Earth Search STAC; optical recipes (true colour, NIR false colour, NDVI, NDWI); lock file | real S2 scene over Dibrugarh renders on the same canvas as NISAR |
| 3c | `landsat_c2l2`; `sentinel1_rtc` and ALOS via `geotiff` with `kind = "sar"`; `pairs = "all"`; `grid` template (N inputs) | SAR-vs-optical for several sensor pairs from one job file |
| 4 | editorial theme and newspaper template | |

## To verify against real services before coding each reader

Earth Search collection names and asset keys (`sentinel-2-l2a`, `landsat-c2-l2`), Sentinel-2 processing-baseline
reflectance offset, Landsat C2 scale/offset, whether a Sentinel-1 RTC source is freely readable without login, and ALOS
PALSAR RTC product conventions (amplitude vs power).

## Status after Phase 3a

Done: `[area]` (point + radius, size, bbox), `Canvas` with snapping to an input grid, `to_canvas` (exact copy when grids
align, otherwise bilinear or block-mean resampling), NISAR read by area, job loader with `extends`, `satviz run` and
`init`, `<job>.lock.json`, built-in layouts, per-input recipes in `compare`, kind check between recipe and product,
adaptive scale bar, sensor attributions that layouts cannot remove.
Verified: the job file for the Brahmaputra scene reproduces the L-vs-S and S-band graphics pixel for pixel.
Next: 3b (geotiff and Sentinel-2 readers, optical recipes, STAC search), then 3c.

## Status after Phase 3 (3a, 3b, 3c)

Done and checked against live data (Dibrugarh, 25 Sep 2026): NISAR L-band with Sentinel-2 (24 Sep, 7% cloud in the area),
Sentinel-1D RTC (same day) and Landsat 8 (same day, 0% cloud in the area), on one 10 m grid.

- Sources verified before coding: Earth Search serves Sentinel-2 L2A as public COGs with per-item scale/offset;
  Earth Search Landsat is requester-pays (HTTP 403), so Landsat and Sentinel-1 RTC come from the Planetary Computer with
  an anonymous token; Sentinel-1 RTC is linear power with nodata -32768.
- Readers: `nisar_gcov`, `sentinel2_l2a`, `landsat_c2l2`, `sentinel1_rtc`, `geotiff`. Recipes: `sar_fcc` (NISAR path with
  noise screening, generic path for co/cross SAR), `true_colour`, `nir_fcc`, `swir_fcc`, `ndvi`, `ndwi`.
- Templates: `single`, `compare`, `grid`; `pairs = "all"` for every pair.
- Not done: ALOS PALSAR needs a real file to check its conventions (use `geotiff` with `values = "amplitude"` meanwhile);
  `date = "same_as:<input>"` (pick optical on the NISAR date automatically); place-name lookup (deferred by choice);
  `before-after` preset; the editorial theme and newspaper template (Phase 4).

## Status: ISRO products and local Sentinel-1 (Oct 2026)

Added as one module each under `sensors/`, with no change to recipes, themes or templates:

| Sensor | Reads | Layers | Notes |
|---|---|---|---|
| `liss4` | ResourceSat-2 LISS-IV product folder | `green red nir` (TOA reflectance) | no blue band, so `nir_fcc`, `ndvi`, `ndwi` only; ESUN from the Disasters Charter LISS-4 page, not from `docs/` |
| `eos04` | EOS-04 MRS Level-2B folder | `co cross` (linear gamma0) | `gamma0 = (DN^2 - noise bias) / 10^(K/10)`, K = the Beta0 constant (format document eq. 10); valid = mask 128 |
| `sentinel1_grd` | unzipped `.SAFE` | `co cross` (linear sigma0) | image-space GCP warp; sigmaNought LUT and range/azimuth noise from the annotation |

Shared by the NRSC readers: `sensors/nrsc.py` (`key=value` metadata, times) and `cog.raster_epsg` (NRSC GeoTIFFs carry
UTM without an EPSG tag). One canvas per job is kept: a job names one place, so combinations are tried per region
(`jobs/brahmaputra_sar.toml`: NISAR L, NISAR S, Sentinel-1 GRD; `jobs/brahmaputra_all.toml` adds EOS-04; `jobs/brahmaputra_optical.toml` adds Sentinel-2 and LISS-IV).

Checks on real data: NISAR L vs Sentinel-1 GRD water-mask cross-correlation peaks at zero offset at 30 m; EOS-04 HH/HV
medians are -8.3 / -17.3 dB over the delta. Not settled by `docs/`: LISS-IV `SaturationRadiance` vs `Lmax` (about 9 %
in green) and the EOS-04 Beta0 vs Gamma0 constant (1.1 dB; the document says Beta0).
