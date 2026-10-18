> **Superseded.** This was the first assessment, written from the JPL L-SAR spec alone. Several statements were
> corrected after reading the ISRO format document and the Science Users' Handbook; see
> [processing-notes.md](processing-notes.md), section "Corrections to the first assessment".

# NISAR S-band GCOV: what is applied, what is missing, what we can correct

Spec: JPL D-102274 Rev E, v1.2.1 (L-SAR). Both granules report `productSpecificationVersion = 1.2.1`.
Probed on 2026-10-18 with strided reads (every 8th pixel), so percentiles are approximate.

## Scope caveat on the spec
The spec describes **L-SAR** (`/science/LSAR/...`). Our files are **S-SAR** (`/science/SSAR/...`, ISRO-processed).
- Table 2-3 (bandwidth → pixel spacing) covers 5/20/40/77 MHz only. Our S-band modes are 25 MHz (20 m) and 37 MHz (10 m).
- `inputDataExceptionMask` and its code 64 ("SSAR sample shift") are **not in the spec**.
- Faraday rotation is negligible at S-band, so it is not a needed correction.
- Layout, units, mask semantics, γ⁰→σ⁰ via `rtcGammaToSigmaFactor` and the dB formula do follow the spec.

## The two granules
| | BLR (Bengaluru) | ASM (Assam, Brahmaputra) |
|---|---|---|
| Mode / pol | 25 MHz, **CR = compact-pol RH/RV** | 37 MHz, **DH = HH/HV** |
| Terms | RHRH, RVRV, RHRV (complex) | HHHH, HVHV, HHHV (complex) |
| Pass / date | **Descending**, 2026-09-18 | Ascending, 2026-09-25 |
| Grid | 20 m, EPSG:32643 | 10 m, EPSG:32646 |
| Looks | 32 | 16 |

## What the product already applies
- RTC to γ⁰ (`radiometricTerrainCorrectionApplied = True`).
- Dry tropospheric geolocation correction.
- Adaptive multilooking.

## What it does not apply (all flags `False`)
- **Noise subtraction** (`noiseCorrectionApplied`).
- **Wet-troposphere and ionosphere (range/azimuth) geolocation corrections.**
- **Shadow/layover masking** (`shadowMaskingApplied`).
- **Valid-sample sub-swath masking** (`validSamplesSubSwathMaskingApplied`).
- **Post-filtering** (`postProcessingFilteringApplied`).
- RFI mitigation is `FDNF` (not defined in the spec). `rfiLikelihood` is 5–10 %, so it is small but non-zero.

## Findings, ranked by impact on the visuals

1. **Calibration metadata is empty, so absolute dB is provisional.**
   - `scaleFactor`, `scaleFactorSlope`, `differentialDelay`, `differentialPhase` and `commonDelay` are exactly 0.0 in both files.
   - All four `crosstalk` grids are NaN.
   - `geometricAccuracy` bias and std are exactly 0.0.
   - Data attributes say `units = DN`, but the spec says `1`.
   - **Consequence:** we can show relative contrast and colour structure. We should not quote absolute σ⁰/γ⁰ dB numbers as calibrated.

2. **Noise floor matters for cross-pol.**
   - NEBS median is about −19.7 dB. It is identical for both polarisations, so it looks like a single nominal number.
   - NEBS is described as "linear scale (units of DN²)". Its normalisation (β⁰/σ⁰/γ⁰) is not stated, so comparing it to γ⁰ terms is approximate.
   - ASM HVHV has p1 ≈ −25 dB and median ≈ −13.6 dB. The darkest 1 % (water, smooth surfaces) is below the stated floor.
   - **Fix:** mask or flag pixels with SNR < ~3 dB, instead of colouring them as real signal.

3. **`inputDataExceptionMask = 64` is a benign footnote, not a defect to mask.**
   - It covers 19 % of ASM and 6 % of BLR, as diagonal stripes following the swath geometry.
   - Radiometry is unaffected. Paired-block median difference across the flag is −0.03 dB (BLR) and about 0 dB (ASM). The IQR of ±0.6 dB is speckle-level.
   - Not tested: whether the sample shift moves geolocation. A check against the Bogibeel Bridge in the 10 m zoom would settle it.

4. **Terrain.**
   - ASM reaches roughly 4800 m in the Arunachal Himalaya.
   - `rtcGammaToSigmaFactor` ranges from p1 0.05 to p99 3.4, with a maximum of 486.
   - There is no shadow/layover mask. Build one (`incidenceAngle` cube plus DEM slope) or use a documented η threshold before showing mountain panels.

5. **Mask handling.**
   - BLR has 4 sub-swaths, but the mask holds only 0/1/255.
   - Use `1 ≤ mask ≤ 5`, not `== 1`, so other products do not break the code.

6. **Geolocation.**
   - Ionospheric corrections are off and the accuracy fields are placeholders.
   - Overlay OSM vectors on a known feature and quote the measured offset.

7. **Minor.**
   - `polarimetricSymmetrizationApplied = True` is meaningless for compact-pol.
   - `numberOfLooks` is constant (32 or 16) except at the edges.

## Problem in the earlier Bengaluru figure
`regenerate_fcc_clean.py` labels the figure "Dual-pol (HH/HV) · Ascending · 10 m · 03 February 2026".
The Bengaluru granule on disk is **compact-pol RH/RV, Descending, 20 m, 18 Sep 2026**.
Either the template came from a different granule, or the labels are wrong.
An HH/HV false-colour composite is not a valid visual for compact-pol data.

## Corrections we can do on top of the product
1. Noise-floor flag/mask (SNR from NEBS).
2. Valid-pixel mask: `mask ∈ [1,5]`, finite values, plus a shadow/layover mask.
3. γ⁰ vs σ⁰ choice via `rtcGammaToSigmaFactor`, with the conversion stated on the figure.
4. Speckle filtering for display, which is **not** the same as the product's multilooking.
5. Compact-pol products for BLR:
   - Stokes parameters from RHRH, RVRV and the complex RHRV. Average the Stokes parameters spatially before computing the degree of polarisation m, or m is biased.
   - m-χ / m-δ decomposition.
6. Geolocation offset check against a known feature.
7. Honest labelling: "relative backscatter, calibration metadata not populated".

## Decisions needed before design
- Which scene(s): Brahmaputra (ASM, HH/HV), Bengaluru (BLR, compact-pol), or both?
- Which Bengaluru granule did the earlier figure come from?
- Which output: social graphic, publication figure, or an explainer on the S-band processing state?
