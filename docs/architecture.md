# Architecture: from one NISAR figure set to a multi-sensor infographic tool

Goal: quickly produce social, publication and newspaper-style infographics from NISAR, Sentinel-2, Landsat and
other well-known satellites, with titles, names and credits customisable, in a few visual aesthetics.

## Four independent axes

Today these are tangled (`figures/*` hardcode `bands["S"]`/`bands["L"]`, `chrome.py` is typed against one theme,
`layout.build_context` is NISAR-shaped). They separate as follows. Any combination should work.

| Axis | Question it answers | Examples |
|---|---|---|
| **Sensor** (reader) | Where do the pixels and facts come from? | `nisar_gcov`, `sentinel2_l2a`, `landsat_c2l2` |
| **Recipe** | How do layers become an image, a legend and caveats? | `sar_fcc`, `true_colour`, `nir_fcc`, `ndvi`, `ndwi` |
| **Theme** | What does the chrome look like? | `minimal`, `neo_retro`, `neo_brutal`, `editorial` |
| **Template** | How is the page arranged? | `single`, `compare`, `clean`, `publication`, `newspaper` |

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
| 2 | `minimal` and `neo_brutal` themes; `single` and `compare` templates are theme-agnostic; per-theme preview gallery | same figure renders in 3 themes without code edits |
| 3 | Sentinel-2 L2A + Landsat C2 L2 readers; STAC search; optical recipes; `grid.py`; SAR-vs-optical compare (NISAR 2026-09-25 vs nearest cloud-free S2 over Dibrugarh) | cross-sensor figure renders with correct credits and caveats |
| 4 | `editorial` theme and `newspaper` template; template research for structure | newspaper page renders from the same inputs |
| 5 | Other sensors (Sentinel-1 GRD, MODIS, …) as needed; docs; gallery; CI | one new sensor added by one file |
