# Pipelines: sensor -> recipe -> template -> theme

Every figure is four independent choices. A new sensor, recipe, template or theme is one module that registers itself, and
any combination that makes sense works.

```
sensor reader --> Product --> recipe --> Rendered --> arrangement (page) --> theme (chrome)
   (what)        layers,     (picture,    + legend      single|compare|grid    colours, type,
                 meta,       legend)      + caveats     chosen by the          rules, sketch
                 caveats                                template
```

A **template** (`optical`, `sar`, `optical_sar`, `sar_vs_sar`) sits above this: it checks the inputs, picks the recipes and the
arrangement, and adds what must be said about the combination. A theme never touches the data.

## Sensors

| Sensor | Kind | Reads | Layers | Facts the figure states (all read from the files) |
|---|---|---|---|---|
| `nisar_gcov` | SAR, L or S band | L2 GCOV HDF5 (local) | `hh hv` and noise-screened terms | band, frequency, track, frame, noise shares, calibration state |
| `eos04` | SAR, C band | Level-2B folder (local) | `co cross` gamma0 | band and frequency from `product.xml`, noise bias, RTC flag |
| `sentinel1_grd` | SAR, C band | `.SAFE` folder (local) | `co cross` sigma0 | frequency, orbit, ellipsoid geolocation, noise dropped |
| `sentinel1_rtc` | SAR, C band | Planetary Computer STAC | `co cross` gamma0 | frequency from the catalogue |
| `sentinel2_l2a` | optical | Earth Search STAC | `blue green red nir swir16 swir22` | cloud share in the area |
| `landsat_c2l2` | optical | Planetary Computer STAC | same | cloud share |
| `liss4` | optical | NRSC folder (local) | `green red nir` (no blue) | TOA, no atmospheric correction |
| `geotiff` | either | any GeoTIFF | from the job's band map | credit and date from the job |

## Recipes

| Recipe | Needs | Default for |
|---|---|---|
| `sar_fcc` | SAR | every SAR input |
| `true_colour` | `red green blue` | optical with a blue band |
| `nir_fcc` | `nir red green` | optical without blue (LISS-IV) |
| `swir_fcc`, `ndvi`, `ndwi` | as named | on request |

## Templates and what they accept

| Template | Inputs | Page | Relation stated |
|---|---|---|---|
| `optical` | optical | one per input (or `compare`/`grid`) | optical: same sensor or different, time gap |
| `sar` | SAR | one per input (or `compare`/`grid`) | as `sar_vs_sar` when several |
| `optical_sar` | SAR + optical | split view, SAR left (or `grid`) | days apart |
| `sar_vs_sar` | SAR + SAR | split view per pair (or `grid`) | same sensor/two bands, same band/two sensors, or both different; wavelengths; time gap; sigma0 vs gamma0 |

## What the local data can and cannot show

| Combination | Where | Status |
|---|---|---|
| SAR + optical | Krishna delta: EOS-04 + LISS-IV | rendered from real data |
| SAR vs SAR, one sensor in two bands | Dibrugarh: NISAR L + S | rendered |
| SAR vs SAR, different sensors and bands | Dibrugarh: NISAR + Sentinel-1 GRD | rendered |
| SAR vs SAR, same band from different sensors | Dibrugarh: EOS-04 (10 Sep) + Sentinel-1 GRD (25 Sep), both C | rendered; the figure states the 15 days between them |
| Four radars on one page | Dibrugarh: NISAR L, NISAR S, Sentinel-1, EOS-04 | rendered (`jobs/brahmaputra_all.toml`) |
| optical vs optical | needs a second optical scene (Sentinel-2 is a network fetch) | tested with synthetic products only |

## Adding one

- **Sensor**: `sensors/<name>.py` with `describe` and `open` registered by `@sensor`; give every SAR product `radar_band`, `freq_ghz`,
  `wavelength_cm` (`satviz.radar.radar_facts`) and `backscatter`, and put its own caveats in `Product.caveats`.
- **Recipe**: `recipes/`, with the `needs` it requires.
- **Template**: subclass `Template` in `templates/scenarios.py`; `plan` returns the input tuples, `resolve` the arrangement, recipes and wording.
- **Theme**: `themes/<name>.py`, a `Theme` of tokens; add `chrome` only for another structure, `rc` and `sketch` for a hand-drawn look.
