# Pipelines: sensor -> recipe -> template -> theme

Every figure is four independent choices. A new sensor, recipe, template or theme is one module that registers itself.

```
sensor reader --> Product --> recipe --> Rendered --> arrangement (page) --> theme (chrome)
   (what)        layers,     (picture,    + legend      single|compare|grid|bands   colours, type,
                 meta,       legend)      + caveats     chosen by the template       rules, sketch
                 caveats
```

## SAR

| Sensor | Reads | Layers | Facts the figure states (all read from the files) |
|---|---|---|---|
| `nisar` | L2 GCOV HDF5 (L-SAR or S-SAR) | `hh hv` and noise-screened terms | band, frequency, track, frame, noise shares, calibration state |
| `sentinel1` | unzipped `.SAFE` (IW GRD) | `co cross` sigma0 | frequency, orbit, ellipsoid geolocation, noise dropped |
| `eos04` | Level-2B folder (MRS) | `co cross` gamma0, or sigma0 with `backscatter = "sigma0"` (document eq. 13-14) | band and frequency from `product.xml`, noise bias, RTC flag |

Recipe: `sar_fcc` for all (HH red, HV green, HH−HV blue; noise-dominated pixels grey).

## Optical

| Sensor | Reads | Layers | Facts the figure states |
|---|---|---|---|
| `sentinel2` | unzipped `.SAFE` (L2A) | all 12 bands `B01`..`B12` + `blue green red nir swir16 swir22` + `cloud` | surface reflectance, band wavelengths, native resolution, cloud share |
| `liss4` | NRSC folder (ResourceSat-2 and 2A) | `green red nir` (no blue) | top-of-atmosphere; which radiance constant was used |

Recipes: `true_colour` (needs blue), `nir_fcc` (the default without blue), `swir_fcc`, `ndvi`, `ndwi`, and the single-band grey
panels of the `bands` arrangement.

## Templates

| Template | Inputs | Arrangements | Relation stated |
|---|---|---|---|
| `sar` | SAR | `single` (one input), `compare` (default for 2+: every pair), `grid` | with 2+: same sensor/two bands, same band/two sensors, or both different; wavelengths; time gap; sigma0 vs gamma0 |
| `optical` | optical | `single`, `compare`, `grid`, `bands` | same sensor or different; time gap; reflectance level. `bands`: nothing (it does not compare) |
| `sar_optical` | SAR + optical | `compare` (SAR left), `grid` | days apart |

## What the local data shows (Dibrugarh)

| Combination | Job |
|---|---|
| SAR vs SAR: NISAR L + S; NISAR + Sentinel-1; EOS-04 + Sentinel-1 (both C, 15 days apart) | `jobs/sar.toml` |
| Four radars on one page | `jobs/sar.toml` (`tiles`) |
| optical vs optical: Sentinel-2C (29 Sep) + LISS-IV 2A (19 Oct), both NIR false colour | `jobs/optical.toml` |
| Multispectral: Sentinel-2C 12 bands, LISS-IV 3 bands | `jobs/optical.toml` (`bands`) |
| SAR + optical: Sentinel-1 / EOS-04 with Sentinel-2 / LISS-IV | `jobs/sar_optical.toml` |

## Adding one

- **Sensor**: `sensors/sar/<name>.py` or `sensors/optical/<name>.py` with `describe` and `open` registered by `@sensor`; list it in
  `registry.load_builtin`. Give every SAR product `radar_band`, `freq_ghz`, `wavelength_cm` (`satviz.radar.radar_facts`) and
  `backscatter`, and put its own caveats in `Product.caveats`.
- **Recipe**: `recipes/`, with the `needs` it requires.
- **Template**: subclass `Template` in `templates/scenarios.py`; `plan` returns the input tuples, `resolve` the arrangement,
  recipes and wording.
- **Theme**: `themes/<name>.py`, a `Theme` of tokens; add `chrome` only for another structure, `rc` and `sketch` for a hand-drawn look.
