# Architecture

Goal: social, publication and newspaper-style infographics from SAR and optical satellite data, with titles, names and credits
customisable, in a few visual aesthetics. Everything reads local files. (The phase-by-phase history of how this got here is in
git; the catalogue/STAC readers, Landsat, Sentinel-1 RTC and the generic GeoTIFF reader were removed in the Oct 2026
restructure.)

## Two kinds of data

| Kind | Sensors | Layer vocabulary the recipes use |
|---|---|---|
| **SAR** | `nisar` (L and S band), `sentinel1` (GRD), `eos04` (MRS L2B) | `co`, `cross` (linear power), plus NISAR's noise-screened terms |
| **Optical** | `sentinel2` (L2A, 12 bands), `liss4` (green, red, NIR) | `blue green red nir swir16 swir22` as reflectance 0..1, every band under its own id, `cloud` |

A product's `kind` (`"sar"` or `"optical"`) decides which template and recipe may take it.

## Independent axes

| Axis | Question it answers | Examples |
|---|---|---|
| **Sensor** (reader) | Where do the pixels and facts come from? | `nisar`, `sentinel1`, `eos04`, `sentinel2`, `liss4` |
| **Recipe** | How do layers become an image, a legend and caveats? | `sar_fcc`, `true_colour`, `nir_fcc`, `swir_fcc`, `ndvi`, `ndwi`, band panels |
| **Template** | What is the figure about, and how do its products relate? | `sar`, `optical`, `sar_optical` |
| **Arrangement** | Where do the products sit on the page? | `single`, `compare`, `grid`, `bands` |
| **Theme** | What does the chrome look like? | `minimal`, `neo_retro`, `neo_brutal`, `newspaper`, `xkcd` |

Rule: **style the chrome, never the data.** Themes never touch data panels, and no theme can hide the caveat strip.

```
 sensor reader ──► Product ──► recipe ──► Rendered(rgba, legend, caveats)
                      │                         │
                      └─ facts/placeholders     ▼
                          template (checks, recipes, arrangement, relation notes)
                                    └──► arrangement (page) styled by a theme ──► PNG
```

## Core types (`satviz.core`)

- `Product`: named float layers, a georeference (`x`, `y`, `epsg`), a `valid` mask, generic `meta` (platform, sensor, start, end,
  resolution_m, crs), `facts` (sensor-specific placeholders), `caveats` (what the sensor insists on printing), `kind`, and for
  optical products `bands` (`BandInfo`: id, wavelength, range, native resolution).
- `Rendered`: `rgba`, `extent`, `legend`, `caveats`.
- Registries with decorators: `@sensor("nisar")`, `@recipe("sar_fcc")`, `@theme("neo_retro")`, `@template("sar")`. A new sensor,
  recipe, theme or template is one module.

## Package layout

```
src/satviz/
  core.py            Product, BandInfo, Rendered, registries
  registry.py        loads the built-in plugins; `satviz list`
  sensors/sar/       nisar/ (io, canvas, metadata, processing, facts), sentinel1, eos04
  sensors/optical/   sentinel2, liss4
  sensors/nrsc.py    key=value metadata and times, shared by eos04 and liss4
  recipes/           sar_fcc, optical, bands
  templates/         base.py (Template, recipe defaults), scenarios.py (sar, optical, sar_optical)
  relations.py       how the products of a figure relate (band, sensor, time gap, backscatter convention, reflectance level)
  radar.py           radar band and wavelength from a centre frequency
  arrangements/      single, compare, grid, bands; `draw` runs one
  themes/            base (Theme tokens, chrome hooks, notice strip), neo_retro, minimal, neo_brutal, newspaper, xkcd
  area.py grid.py job.py run.py sources.py cog.py   area -> canvas, resampling, job file, runner, data paths, GeoTIFF windows
  config.py layout.py geo.py                        scene dataclasses, wording files and placeholders, projections
  presets/ layouts/                                 starter job files and built-in wording (shipped with the package)
  cli.py             `satviz run | init | list | placeholders`
jobs/                brahmaputra.toml (place + all local inputs) and sar, optical, sar_optical, social extending it
```

Dependencies: `numpy, scipy, matplotlib, h5py, pyproj` for NISAR; `rasterio` (extra `[rasters]`) for the four GeoTIFF products.

## From paths to a figure

`satviz quick` and `satviz.render` build the same tables a job file holds and hand them to `run_job`, so there is one pipeline:

```
paths ─ detect (sensor.sniff) ─ ids ─ template and arrangement from the kinds and the count ─┐
                                                                                             ├─ job tables ─ run_job ─ PNG (+ PDF)
 [area] absent ─ footprints (sensor.describe) ─ largest common rectangle ─ pixel size ───────┘
```

- **Footprints** are rings of where a product has data, from its metadata where that is truthful (NISAR `boundingPolygon`,
  Sentinel-2 `EXT_POS_LIST`) and from a coarse read of its valid pixels where the metadata is only a bounding quad (Sentinel-1's
  zero collars, EOS-04 and LISS-IV swaths). The overlap is intersected on a coarse grid; the largest axis-aligned rectangle
  inside it becomes the area, so no panel has a nodata wedge.
- **Reads are decimated.** When the canvas is at least twice as coarse as a product, NISAR, Sentinel-1 and the GeoTIFF readers
  convert and block-average a strip of rows at a time, which gives what reading the whole window and resampling would, in bounded
  memory (a whole-frame quick figure of two radars: about 7 s and 1 GB, against 28 s and 4.7 GB before).
- **Stretch.** Optical colour and band stretches are the 2nd to 98th percentiles of the clear pixels: where a product maps cloud,
  cloud is left out of the limits (it is still drawn, saturated) and the notice strip says so when it is at least 1% of the view.
- **Titles and names.** A job with no `[scene] name` (every quick figure) gets a title from its products, and its files are named
  after the sensors and the profile; a job file keeps its own name and its file stem.
- **Large areas.** An automatic area above 15,000 km² is refused with a suggested `--bbox`; `--allow-large` lifts it.
- **The app** (`satviz.app`, Streamlit) only collects choices and calls `build_job` and `run_job`; `api.scan` lists a folder's products
  from their names and a few files, never their pixels. Renders run on a button press, one at a time (matplotlib is global state),
  and a `TooLarge` error carries the suggested box so the page can fill it in. `satviz app` serves on localhost, sets the folders by
  environment, and starts Streamlit through a line that turns off its PyPI version check (the one outbound call it makes; a test
  proves none is attempted).
- **Layout and preview.** The layouts offered depend on the kinds chosen (`api.layout_choices`); the Layout preview is
  `preview.render_example`: small stand-in products drawn through the real arrangements, themes and wording, so it cannot drift from
  a real figure. The Area tab is a Streamlit custom component (`app_component/index.html`, no build step, no network): it draws
  the products' footprints and returns the rectangle the mouse draws.
- **One wording, every sensor.** `api.details` turns the typed title, subtitle, place, author, website and extra credit into scene
  fields and figure text for any job; the extra credit is written onto the author's credit line (a page with many notices has no
  room for another line) and the sensors' DATA credit line is always appended. The same function feeds the preview, so the example
  page shows the wording as it will print.
- **The map** (`app_component/index.html`) is Web Mercator so OpenStreetMap tiles line up exactly; its only network use is the
  browser fetching those tiles, and only while the basemap is ticked (`tile_url` can point at a local server, which is how it is tested).
- **Map furniture** (`satviz.furniture`): `decorate` is the one call every arrangement makes per panel. The grid is meridians and
  parallels transformed into the panel's UTM zone and cut at its edge, each labelled where it meets the edge; the arrow is measured
  from the projection (true north, not grid north); the scale bar is the one that was always there. Defaults reproduce earlier
  figures pixel for pixel (checked on all 26 job-file figures).
- **`--save-job`** writes the resolved tables (sensors, absolute paths, centre and size, pixel size), so running the saved file gives
  the same figure; a test pins that.
- **Profiles** (`satviz.quality`): `quick` (800 px along the longer side, 100 dpi, PNG), `medium` (1400 px, 140 dpi, PNG) and
  `publication` (2000 px, 180 dpi, PNG and a PDF with TrueType text). A job file with its own pixel size keeps it.

## Principles

1. **One job file.** `[area]`, `[[inputs]]`, `[[figures]]`; `satviz init sar|optical|sar-optical` writes a starter. A job may
   `extends` a base file, which is how the Dibrugarh jobs share their place and inputs; inputs a job does not use are never read.
2. **The area defines the canvas.** `[area]` fixes a UTM CRS, an extent and a pixel size. Every reader returns its data already on
   that grid, so any two inputs can be compared. One canvas per job: a job names one place.
3. **Recipes depend on the layer vocabulary, not on the sensor.** N sensors + M recipes + K templates + L themes is that many
   pieces of code, not their product.
4. **Honesty and credits are sensor-supplied.** Calibration state, noise screening, cloud share, reflectance level, backscatter
   convention and the required attributions come from the reader and recipe. A job can add to them, not remove them.
5. **Optical scaling comes from product metadata**, never hardcoded: Sentinel-2 L2A (processing baseline ≥ 04.00) has a BOA
   offset per band; LISS-IV radiance constants come from the product's own `.meta`.
6. **Newspaper style is inspired by, not copied from**, real publications: kicker, headline, dek, byline, caption, source line,
   column rules. No real masthead, name or branding.
7. **Wording files beat template wording.** A figure with its own `layout` file keeps that file's text; the job's `text` still
   overrides it, and the sensors' notices are always added.

## Open points the documents in `docs/references/` do not settle

LISS-IV `SaturationRadiance` against `Lmax` (about 9 % in green) and the 2A solar irradiances; the EOS-04 Beta0 against Gamma0
constant (1.1 dB; the format document says Beta0). The figures state which was used.
