# nisar-ls-viz

Noise-aware false-colour composites and figures from NISAR **L-band** and **S-band** L2 GCOV products.
The first scene is the Brahmaputra near Dibrugarh (Assam), seen by L-SAR and S-SAR on the same pass.

<p align="center">
  <img src="docs/img/social.jpg" alt="Social graphic: L-band and S-band split view of the Brahmaputra" width="46%">
  <img src="docs/img/publication.jpg" alt="Publication figure: L-band vs S-band composites, HH scatter and HV SNR" width="46%">
</p>

The S-band product is still unfinished: calibration metadata is unpopulated, noise is not subtracted and a flag
(`inputDataExceptionMask` = 64) is undocumented. This code does not hide that. It screens each pixel against the
product's noise floor, draws noise-dominated pixels grey instead of as signal, and prints the caveats on every figure.
Read [docs/processing-notes.md](docs/processing-notes.md) before quoting any number.

## What it does

- Reads an ROI from a GCOV HDF5 file (HH and HV covariance terms, mask, RTC factor, noise-equivalent backscatter).
- Refers the noise floor to γ⁰ (NEBS / η), flags pixels below SNR 3 dB and subtracts noise elsewhere.
- Builds a false-colour composite: R = HH, G = HV (noise-subtracted), B = HH−HV ratio, with per-band or pooled stretch.
- Renders six figures:

| `nisar-viz render …` | Output | Style |
|---|---|---|
| `sband-social` / `lband-social` | One band: full-width composite and the three bands it is built from, 4:5 | neo-retro |
| `ls-social` | L|S split view with three zoom pairs, 4:5 | neo-retro ([design notes](docs/design-language.md)) |
| `ls-clean` | Two large maps, compact header and footer | clean white, [preview](docs/img/clean.jpg) |
| `ls-publication` | Composites, HH L-vs-S density, HV SNR distributions; PNG + PDF | journal-style, one pooled stretch |
| `sband-publication` | S-band alone: HH, HV, composite, SNR; PNG + PDF | journal-style |

## Install

Python 3.11 or newer.

```bash
git clone <this repo> && cd nisar-ls-viz
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Data

No data are stored here. You need two NISAR GCOV granules from the same pass, obtained from the official NISAR
distribution channels (check the provider's terms of use). The Brahmaputra scene expects:

```
NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5   (S-SAR)
NISAR_L2_PR_GCOV_031_112_A_016_4005_DHDH_A_20260925T225740_20260925T225815_P05023_N_F_J_001.h5   (L-SAR)
```

Put them in `data/` (ignored by git), or point the tool elsewhere with `--data-dir /path/to/granules` or
`export NISAR_DATA_DIR=/path/to/granules`. Lookup order: `--data-dir`, `$NISAR_DATA_DIR`, `./data`, the current directory. Reading a slice from these multi-GB files can be slow, so ROIs are cached as `.npz`
in `cache/` (invalidated automatically if the source file changes; `--no-cache` to disable).

## Usage

Run from the repository root (the default `--config` is `configs/brahmaputra.toml`).

```bash
nisar-viz render all                                       # granules in ./data; writes to outputs/
nisar-viz render ls-social ls-clean --out figs/
nisar-viz render ls-social --pooled-stretch                # same colours in both bands (default: each band on its own)
nisar-viz stats --data-dir /path/to/granules               # noise fractions, backscatter percentiles per band
python -m nisar_viz render ls-publication                  # same as the console script
```

## Layout files: change the wording without touching code

What is written on each figure lives in `layouts/<figure>.toml` (`sband_social.toml` and `lband_social.toml` for the
single-band graphics, plus the four L-vs-S and publication files): main title, subtitle, info line, the how-to-read
legend, the bottom notes, the credits and the publication captions. Edit them freely.

```toml
# layouts/ls_social.toml
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

Facts are **never typed in a layout**. Placeholders such as `{date}`, `{time_utc}`, `{track}`, `{frame}`,
`{pass_direction}`, `{posting_m}`, `{crs}`, `{L.wavelength_cm:.0f}`, `{S.freq_ghz:g}`, `{S.crid}` and the noise
percentages `{S.noisy_hv_pct:.0f}` are read from the granule metadata and the data (the identification group,
swath, calibration and processing-parameter groups). `{x_upper}` is the upper-case form of `{x}`, and `{x!u}` upper-cases any value (e.g. `{L.rfi!u}`). The colour-stretch
limits of the single-band graphics are `{lim.HH_lo}`, `{lim.HH_hi}`, `{lim.HV_lo}` and so on. List all of them
with their values:

```bash
nisar-viz placeholders --data-dir /path/to/granules
```

Two safeguards: a line written as `{ if = "uncal_bands", text = "..." }` shows only while a band's calibration scale
factors are zero in the file, so the provisional-calibration warning disappears by itself when ISRO populates them; and
the tool refuses to build a figure from two granules that are not the same track, frame and pass direction. Unknown
placeholders and over-long lists fail with the file name and the valid choices. `nisar-viz render --layouts-dir DIR`
uses another set of layout files.

## Another scene

A scene is one TOML file ([configs/brahmaputra.toml](configs/brahmaputra.toml)): granule filenames, the ROI (rows and
columns) in each file's own grid, zoom windows, callouts and the place names (`name`, `reach`, `region`, author,
website). Date, pass and instrument facts are not in it; they come from the files. Copy it, edit it and pass
`--config`. The L-band and S-band ROIs must cover the same ground; check that the `x`/`y` coordinates match before
building a split view.

## Layout

```
src/nisar_viz/
  config.py       scene TOML -> dataclasses
  metadata.py     acquisition facts read from the granule (date, pass, frequency, flags)
  layout.py       layout TOML + placeholders filled from metadata and statistics
  io.py           HDF5 ROI reader, NEBS interpolation, cache
  processing.py   noise floor, SNR flags, block means, statistics
  composite.py    false-colour composite and pooled stretch
  geo.py          extent and projection helpers
  chrome.py       scale bar and neo-retro panels
  themes.py       design tokens
  figures/        one module per figure
  cli.py          nisar-viz entry point
configs/          scene definitions (granules, ROI, zooms, place names)
layouts/          figure wording: titles, how-to-read, notes, credits, captions
docs/             processing notes, design language, first assessment (superseded), preview images
tests/            synthetic-data tests (no granules needed)
archive/          earlier scripts and design explorations, unmaintained
```

## Fonts

Figures use IBM Plex Sans / Mono and Gillius ADF if installed, and fall back to DejaVu otherwise; the layout
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
