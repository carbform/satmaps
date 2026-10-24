# satviz

Social, publication and editorial infographics from satellite data, alone or side by side: **SAR** (NISAR, Sentinel-1, EOS-04) and **optical** (Sentinel-2, ResourceSat LISS-IV, including band-by-band multispectral views).
The worked scene is the Brahmaputra near Dibrugarh (Assam), seen by all five.

<p align="center">
  <img src="docs/img/social.jpg" alt="Social graphic: L-band and S-band split view of the Brahmaputra" width="38%">
  <img src="docs/img/theme_neoretro.jpg" alt="Radar next to optical over the Brahmaputra: Sentinel-1 and LISS-IV" width="38%">
</p>

The S-band product is still unfinished: calibration metadata is unpopulated, noise is not subtracted and a flag
(`inputDataExceptionMask` = 64) is undocumented. This code does not hide that. It screens each pixel against the
product's noise floor, draws noise-dominated pixels grey instead of as signal, and prints the caveats on every figure.
Read [docs/processing-notes.md](docs/processing-notes.md) before quoting any number.

## What it does

You describe a place, point at the data you have, and choose what the figure is about and how it looks. The tool finds the
product's files, reads only the part under your area, calibrates it from the product's own metadata, puts every input on one
pixel grid, and prints what the data cannot promise (calibration, noise, cloud, reflectance level, backscatter convention, time
between acquisitions) on the figure. Everything reads local files; nothing is downloaded.

Two kinds of data, five sensors, three templates:

| | Sensors (`sensor =`) | Reads | Layers |
|---|---|---|---|
| **SAR** | `nisar` | NISAR L2 GCOV `.h5` (L-band and S-band) | HH/HV, noise-screened, γ⁰ |
| | `sentinel1` | Sentinel-1 IW GRD, the unzipped `.SAFE` | VV/VH, σ⁰ with noise subtracted |
| | `eos04` | EOS-04 MRS Level-2B, the unzipped folder | HH/HV, γ⁰ (or `backscatter = "sigma0"`) |
| **Optical** | `sentinel2` | Sentinel-2 L2A, the unzipped `.SAFE` | all 12 bands, surface reflectance |
| | `liss4` | ResourceSat-2/2A LISS-IV, the unzipped folder | green, red, NIR at 5 m, top-of-atmosphere |

| You choose | Options |
|---|---|
| **Where** | a centre and size, or a box (`[area]`) |
| **What data** | one of the five sensors and a file or folder (`[[inputs]]`) |
| **What it is about** | `sar`, `optical` or `sar_optical` (`template`) |
| **How it looks** | `neo_retro`, `minimal`, `neo_brutal`, `newspaper`, `xkcd` (`theme`) |
| **What it says** | titles, notes, credits, in a wording file with `{placeholders}` filled from the data |

## Job files: fill in a config, run one command

```bash
satviz init                              # list the starters: sar, optical, sar-optical
satviz init sar -o job.toml              # write one
# edit the area, the data files and the wording
satviz run job.toml --out outputs/
```

A job file says where (`[area]`: `center` + `radius_km` or `size_km`, or a `bbox`), which data (`[[inputs]]`: an `id`, a
`sensor` and a `source` path or glob), and which figures (`[[figures]]`: a `template`, `inputs`, `theme` or a list of themes,
`text = { title = "...", subtitle = "..." }`, and optionally an `arrangement`). The area defines one pixel grid and every
input is read onto it, so the inputs always line up: grids that already match are copied, others are resampled, and a notice
says so. A `<job>.lock.json` next to the outputs records the grid and the input files. Sensors add their own attribution and
caveats (calibration state, noise screening), and these cannot be removed.

## Templates

A **template** says what a figure is about. It checks the inputs, picks a recipe for each, decides how they sit on the page
(the **arrangement**) and states how the products relate. A **theme** only styles the chrome around the data.

| `template` | Takes | `arrangement` | What the figure also says |
|---|---|---|---|
| `sar` | NISAR, Sentinel-1, EOS-04 | `single` (one input, the default), `compare` (every pair, split view; the default for two or more), `grid` (2 to 6 tiled) | with two or more: how they relate (below) |
| `optical` | Sentinel-2, LISS-IV | the same three, plus `bands`: one product band by band | reflectance level and days apart; the sensor's own notices |
| `sar_optical` | at least one of each | `compare` (each SAR against each optical, SAR left; default) or `grid` | days between the acquisitions |

`sar` with two or more inputs reads the relation from the products and prints it as the subtitle and one notice line: **same
sensor in two bands** (NISAR L and S), **same band from different sensors** (EOS-04 and Sentinel-1, both C-band), or **different
sensors and bands**; with the wavelengths, the time between acquisitions, and a warning when backscatter conventions differ
(σ⁰ ellipsoid against γ⁰ terrain-corrected: not directly comparable). Bands and wavelengths come from each file's own frequency,
never from a table. Optical pairs get the same treatment for reflectance level (Sentinel-2 L2A is surface reflectance, LISS-IV
top-of-atmosphere).

`optical` with `arrangement = "bands"` shows one product band by band (Sentinel-2's 12 bands, LISS-IV's 3), each panel in linear
grey on one shared stretch so brightness ratios between bands stay real (`stretch = "per-band"` gives each its own, with the limits on
its label), labelled with the band id, centre wavelength (or nominal range) and native pixel size. `composites = ["true_colour",
"nir_fcc"]` appends colour composites; they are off by default. It never compares.

If a figure names no recipe, SAR inputs get `sar_fcc`; optical inputs get `true_colour` when they have a blue band and `nir_fcc`
when they do not (LISS-IV), and several optical inputs on one figure share one recipe. Other recipes: `swir_fcc`, `ndvi`, `ndwi`;
`recipes = { E = "sar_fcc", L4 = "ndvi" }` sets one per input.

<p align="center">
  <img src="docs/img/sar_vs_optical.jpg" alt="EOS-04 radar next to Sentinel-2 over the Brahmaputra" width="30%">
  <img src="docs/img/grid_four_sensors.jpg" alt="Sentinel-1, EOS-04, Sentinel-2 and LISS-IV on one grid" width="30%">
  <img src="docs/img/scenario_sar_vs_sar.jpg" alt="SAR against SAR: Sentinel-1 and EOS-04, both C-band; the relation, the days between them and the backscatter conventions are stated" width="30%">
</p>

## Themes

Five looks. The data panels are identical in every theme (a test compares the pixels); only the chrome changes.

<p align="center">
  <img src="docs/img/theme_neoretro.jpg" alt="neo-retro" width="18%">
  <img src="docs/img/theme_minimal.jpg" alt="minimal" width="18%">
  <img src="docs/img/theme_neobrutal.jpg" alt="neo-brutal" width="18%">
  <img src="docs/img/theme_newspaper.jpg" alt="newspaper" width="18%">
  <img src="docs/img/theme_xkcd.jpg" alt="xkcd" width="18%">
</p>

`neo_retro`, `minimal`, `neo_brutal`, `newspaper` (kicker, headline and dek between rules, serif type, hairline column
rules; inspired by a printed page, no real masthead) and `xkcd` (hand-drawn chrome in a comic typeface; the sketch effect is
removed inside every data axes, so scale bars, zoom boxes and the split line stay exact). `theme = ["minimal", "xkcd"]` writes one
file per theme. A theme is a dozen tokens in `src/satviz/themes/` (copy `minimal.py`); one that needs another structure can
also supply `chrome` with its own `header` and `block`, as `newspaper.py` does. Text tokens must reach 4.5:1 contrast on their
backgrounds; a test enforces it.

## Install

Python 3.11 or newer.

```bash
git clone <this repo> && cd satviz
python -m venv .venv && source .venv/bin/activate
pip install -e ".[rasters,dev]"
```

## Data

No data are stored here. Put the downloads in `data/` (ignored by git), unzipped: the Sentinel-1 and Sentinel-2 `.SAFE` folders,
the NRSC folders (EOS-04 `E04_…`, LISS-IV `R2F…`), and the NISAR `.h5` files as they are. Or point the tool elsewhere with
`--data-dir /path` or `export SATVIZ_DATA_DIR=/path`. Lookup order: `--data-dir`, `$SATVIZ_DATA_DIR`, `./data`, the current
directory. The Dibrugarh jobs in [jobs/](jobs/) expect:

```
NISAR_L2_PR_GCOV_031_112_A_016_4005_…h5     NISAR_S2_PR_GCOV_031_112_A_016_3700_…h5     (L-SAR and S-SAR, 25 Sep 2026)
S1D_IW_GRDH_1SDV_20260925T114837_….SAFE     E04_SAR_MRS_10SEP2026_….                    (Sentinel-1, EOS-04)
S2C_MSIL2A_20260929T041551_….SAFE           RAF19OCT2026051193011300052SSANSTUC00GTDA   (Sentinel-2C, LISS-IV)
```

NISAR needs only `pip install -e .`; the other four are GeoTIFF products and need `pip install -e ".[rasters]"` (rasterio). Reading
a slice of a multi-GB NISAR file can be slow, so it is cached as `.npz` in `cache/` (invalidated when the source changes;
`--no-cache` to disable). The handbooks the readers follow are listed in [docs/references/](docs/references/README.md).

## Usage

```bash
satviz init                                 # list the starter job files
satviz init sar -o job.toml                 # write one, then edit the area, the data and the wording
satviz run job.toml --out outputs/          # render every figure of the job
satviz placeholders job.toml                # the {placeholders} a wording file of this job can use, with their values
satviz list                                 # sensors, recipes, themes, templates
```

The worked jobs in [jobs/](jobs/) all extend [brahmaputra.toml](jobs/brahmaputra.toml), which holds the place and every local input;
each says only what to draw:

| Job | Draws |
|---|---|
| [sar.toml](jobs/sar.toml) | every pair of NISAR L, NISAR S, Sentinel-1 and EOS-04; all four on one page; a sigma0-only pair |
| [optical.toml](jobs/optical.toml) | Sentinel-2 and LISS-IV band by band, and side by side |
| [sar_optical.toml](jobs/sar_optical.toml) | each radar against each optical; all four tiled; the five themes |
| [social.toml](jobs/social.toml) | NISAR social posts with their own wording files from [jobs/layouts/](jobs/layouts/) and zoom windows |

## Wording files: change what the figure says without touching code

Every template has built-in wording, and the job's `text = { title = "...", subtitle = "..." }` overrides the header. For full control
point a figure at a wording file of your own: `layout = "layouts/my_figure.toml"` (relative to the job file). Two examples, with
the placeholders they use, are in [jobs/layouts/](jobs/layouts/): `ls_social.toml` (split view) and `sband_social.toml` (one input).

```toml
# jobs/layouts/ls_social.toml
[header]
title = "River Brahmaputra"
subtitle = "THE {name_upper} AS SEEN BY NISAR"
date = "{date_upper}"                      # <- from the file, not typed
info_line = "... TRACK {track} · FRAME {frame}"
[notes]
lines = [
  { if = "uncal_bands", text = "{uncal_bands_upper} CALIBRATION METADATA NOT YET POPULATED ..." },
  "{stretch_warning_upper} NOISE-SCREENED (SNR < 3 dB GREY), SPECKLE FILTER NOT APPLIED",
]
```

Facts are **never typed in a wording file**. Placeholders such as `{date}`, `{time_utc}`, `{crs}`, `{posting_m}`, and per input
`{S1.date}`, `{L.wavelength_cm:.0f}`, `{S.freq_ghz:g}`, `{S.noisy_hv_pct:.0f}` are read from the products. `{x_upper}` is the
upper-case form of `{x}`, and `{x!u}` upper-cases any value. `satviz placeholders job.toml` lists every one the job's products
provide, with its value.

Two safeguards: a line written as `{ if = "uncal_bands", text = "..." }` shows only while a band's calibration scale factors are
zero in the file, so the provisional-calibration warning disappears by itself when ISRO populates them; and NISAR inputs from
different tracks, frames or passes are refused unless the figure sets `allow_different_passes = true`. Unknown placeholders and
over-long lists fail with the file name and the valid choices. What a sensor insists on (attribution, calibration and quality
caveats) is added to every figure and cannot be removed by a wording file's header.

## Layout

```
src/satviz/
  core.py         Product, Rendered, registries for sensors, recipes, templates, themes
  registry.py     loads the built-in plugins; `satviz list`
  sensors/
    sar/          nisar/ (L2 GCOV), sentinel1 (GRD), eos04 (MRS L2B)
    optical/      sentinel2 (L2A, 12 bands), liss4
    nrsc.py       metadata parser shared by the NRSC/ISRO readers (eos04, liss4)
  recipes/        sar_fcc (SAR false colour), optical (true colour, NIR/SWIR false colour, NDVI, NDWI), bands (single-band grey panels)
  templates/      sar, optical, sar_optical (scenarios.py); base.py holds what they share
  relations.py    how the products of a figure relate (band, sensor, time gap, backscatter convention, reflectance level)
  radar.py        radar band and wavelength from a centre frequency
  arrangements/   single, compare, grid, bands: where products sit on the page; `draw` runs one
  themes/         base.py (Theme tokens + chrome), neo_retro, minimal, neo_brutal, newspaper, xkcd
  area.py, grid.py, job.py, run.py, sources.py   area -> canvas grid, resampling, job file, runner, data paths
  config.py, layout.py, geo.py, cog.py            scene dataclasses, wording files + placeholders, projections, GeoTIFF windows
  presets/, layouts/    starter job files (sar, optical, sar-optical) and built-in wording (shipped with the package)
  cli.py          `satviz run | init | list | placeholders`
jobs/             brahmaputra.toml (place + inputs) and the four jobs that extend it; layouts/ has two wording-file examples
docs/             architecture, pipelines, processing notes, design language; references/ lists the (git-ignored) PDFs
tests/            synthetic-data tests (no granules needed)
```

## Fonts

Figures use IBM Plex Sans / Mono and Gillius ADF (neo-retro), Source Serif Pro (newspaper) and Humor Sans or Comic Neue (xkcd) if installed, and fall back to DejaVu otherwise; the layout
holds either way, but renders are only pixel-identical on a machine with the same fonts.

## Development

```bash
pytest -q          # synthetic granules, runs in seconds
ruff check .
```

CI runs both on Python 3.11 and 3.12.

## Caveats in one place

- S-band calibration scale factors are zero in the product: S-band dB is relative, and the L−S offset is provisional.
- 39 % (S) and 36 % (L) of 10 m HV pixels are below the noise threshold, mostly open water. The figure shows them grey.
- The noise layer is documented as σ⁰-referenced, so the γ⁰ floor is NEBS / η. If it were γ⁰-referenced the fractions would be 23 % and 25 %.
- L-band RFI mitigation was not applied; S-band ionospheric geolocation correction was not applied.
- The S-band exception code 64 (72 % of the ROI) is undocumented; no radiometric step was found, geolocation not tested.

Details and the open questions for the data provider are in [docs/processing-notes.md](docs/processing-notes.md).

## Licence

Code: MIT, see [LICENSE](LICENSE). NISAR data and the source documents belong to their providers (NASA/JPL and
ISRO); figures derived from them should credit "NASA-ISRO NISAR".
