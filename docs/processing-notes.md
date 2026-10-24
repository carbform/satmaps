# Processing notes: NISAR L-band and S-band GCOV, Brahmaputra scene

What the products already contain, what they do not, and what this code does about it. Scene: track 112, frame 16,
ascending, 25 Sep 2026, S-SAR and L-SAR from the same pass.

## Sources

| Source | Used for |
|---|---|
| JPL D-102274 Rev E (L-SAR GCOV product specification) | Layout, γ⁰/σ⁰ convention, mask semantics, dB formula, flag meanings. L-band only. |
| ISRO-SAC-PR-NISAR-2024-051 v1.2.1 (L- and S-band format document) | Authoritative for S-SAR: posting (Table 7-1), units, RFI algorithm names, noise layer definition. |
| NISAR Science Users' Handbook v1 (2019) | S-SAR mode list, design noise floor, ionosphere sensitivity, S-band requirement status. |

The PDFs are third-party and are not stored in this repository.

## The granules

| | S-band (S-SAR) | L-band (L-SAR) |
|---|---|---|
| Centre frequency (from the file) | 3.2 GHz (≈9 cm) | 1.239 GHz (≈24 cm) |
| Mode | 37.5 MHz, HH/HV dual-pol | HH/HV dual-pol |
| Acquisition (from the file names) | 22:57:40 to 22:58:16 UTC | 22:57:40 to 22:58:15 UTC |
| Grid | 10 m, EPSG:32646 | 10 m, EPSG:32646 |
| Region of interest | rows 27800–30880, cols 11500–14400 | rows 28160–31240, cols 11572–14472 |
| Valid-sample mask in the ROI | 100 % | 99.96 % |
| Exception flags in the ROI | code 64 on 72 % | none |

Both ROIs have identical x/y coordinates (0 m offset), so the bands can be stacked pixel for pixel without resampling.
The ROI is 29 × 30.8 km of braided river, floodplain, a hill edge and the south bank. The figures say "22:57 UTC" (the
start of the data take, not the mid-time of about 22:58).
In local time the pass is 04:27 IST on 26 Sep.

## What the products already did

| | S-band | L-band |
|---|---|---|
| Radiometric terrain correction to γ⁰ (`rtcGammaToSigmaFactor` = η, σ⁰ = η·γ⁰) | applied | applied |
| Dry-troposphere geolocation correction | applied | applied |
| Ionospheric geolocation correction (range, azimuth) | not applied | applied |
| RFI mitigation | applied (FDNF; `rfiLikelihood` about 6.6 % HH, 10.5 % HV) | not applied |
| Polarimetric symmetrization | applied | not applied |
| Noise subtraction | not applied | not applied |
| Valid-sample sub-swath masking, shadow masking, wet-troposphere correction, speckle filtering | not applied | not applied |
| Calibration scale factors | **0.0 (unpopulated)** | populated (HH ≈ 27 030, HV ≈ 30 166) |
| Multilooking | adaptive, 16 looks; `numberOfLooks` is one constant, as documented for ISRO products | |

Unpopulated S-band metadata: `scaleFactor`, `scaleFactorSlope`, `differentialDelay`, `differentialPhase`, `commonDelay`
are 0.0, the crosstalk grids are NaN and the geometric-accuracy block is zeros. The ISRO document defines these as
corrections *applied*, so zeros mean unpopulated, not applied. **Treat S-band dB as relative.**

## What this code does about the gaps

| Gap | Handling | Why |
|---|---|---|
| Noise not subtracted | Subtract the noise floor; flag pixels with SNR < 3 dB and draw them grey instead of as signal | S-band HV median is −15 dB against a floor near −19 dB; water sits at or below it. |
| Noise layer is σ⁰-referenced | Floor in γ⁰ = NEBS / η | ISRO document §7.3.6.1 calls it noise-equivalent sigma0; the field description only says "linear (DN²)". |
| Valid-sample mask not applied | Use `1 ≤ mask ≤ 5`, finite, positive | Mask semantics from the spec. |
| No shadow/layover mask | None built. η over the ROI is 0.29–1.12 (1st–99th percentile): flat floodplain | Any mountain scene would need a mask. |
| Speckle | Social and clean figures: native 10 m, no filter. Publication figures: 3 × 3 block mean in linear power (30 m) | The product is already 16-look; block means avoid aliasing in small panels. Not an edge-preserving filter. |

## Numbers (ROI)

| | S-band | L-band |
|---|---|---|
| HV below the 3 dB SNR threshold (NEBS/η floor) | **39 %** | **36 %** |
| Same, if the layer were already γ⁰-referenced | 23 % | 25 % |
| NEBS HV median (σ⁰-referenced) | −20.7 dB | −23.7 dB |
| γ⁰ floor median (NEBS/η) | −19.1 dB | −22.2 dB |
| HH γ⁰ p2 / p50 / p98 | −19.0 / −8.8 / −0.7 dB | −20.6 / −9.4 / −0.2 dB |
| HV γ⁰ p2 / p50 / p98 | −21.9 / −15.0 / −8.0 dB | −24.8 / −17.4 / −8.1 dB |

Pick one noise convention and say so; the code uses the documented one (NEBS/η) and reports both fractions. The handbook
design goal for S-band is "< −20 dB NES0 depending on mode", so the S-band layer is plausible.

## Why S-band looks flatter under one shared colour stretch

Both bands are γ⁰, so this is not a convention difference. Measured on land pixels that clear the HV noise threshold:

| Channel (5th–95th percentile) | L-band | S-band |
|---|---|---|
| HH | −14.0 to −1.2 dB (std 3.95) | −15.4 to −1.8 dB (std 4.15) |
| HV | −21.4 to −9.2 dB (std 3.79) | −18.6 to −9.3 dB (std 2.99) |
| HH−HV | 2.2 to 15.7 dB (median 8.3) | −0.5 to 13.3 dB (median 6.6) |

HH spread is the same. S-band HV is squeezed, probably because its higher noise floor removes the darkest pixels, and its
HH−HV ratio is lower. Together the channels sit closer, so colours turn pastel. Part of this is probably physical
(shorter wavelengths depolarise more) and part instrumental (noise floor, uncalibrated levels); the data here do not
separate the two. The social figure therefore stretches each band to its own percentiles by default and says so on the
graphic. `stretch = "pooled"` in a job uses one set of limits for both, so colours are comparable.

S-band water appears dark green rather than grey in the pooled figures: its HV clears the 3 dB threshold even though it
is dark. Unexplained (wind-roughened water, or a noise floor that is too low?). Do not caption it as a real signal.

## Caveats that must stay on the graphics

1. **S-band calibration metadata is empty.** dB values are relative; the L−S offset (median −1.1 dB in HH) is provisional.
2. **The geometric-accuracy block is zeros.** Not a measurement.
3. **No S-band science requirement.** The handbook says there are "no explicit requirements on science measurements at
   S-band". Do not quote L-band accuracy figures for these data.
4. **S-band sample-shift flag (`inputDataExceptionMask` = 64).** In the data, in neither document; meaning rests on the
   in-file description ("NISAR SSAR sample shift"). It covers 72 % of the ROI. Across the whole frame the median
   backscatter differs by about 0 dB between flagged and unflagged blocks (IQR ±0.6 dB, speckle level), so there is no
   radiometric step. **Geolocation effect not tested.**
5. **Plot grid.** Figures are in UTM 46N, not resampled to lat/lon. Grid north differs from true north by about 0.9° here.
   The Simen-confluence and sand-bar callout points come from earlier work and were not re-verified against a map.
6. **L-band RFI mitigation was not applied.** The L-band composite has not been inspected for RFI streaking.

## Corrections to the first assessment

(The first assessment was an early draft written from the JPL L-SAR specification alone. It was removed in the Oct 2026 cleanup, with the other early exploration material; it is in the git history. What it got wrong is listed here.)

| Earlier statement | Now |
|---|---|
| "RFI `FDNF` not defined" | An RFI-mitigation algorithm name (ISRO document). Mitigation was applied to S-band. |
| "`units = DN` vs spec `1`" | `DN` is correct for ISRO S-SAR products. |
| "Spacing for 25/37.5 MHz undefined" | Table 7-1: 25 MHz → 20 m, 37.5 MHz → 10 m. |
| "`numberOfLooks` quirk" | Documented: a single constant value for ISRO products. |
| NEBS compared directly to γ⁰ | NEBS is σ⁰-referenced, so divide by η. This raises the flagged S-band fraction from 23 % to 39 %. |
| "No data on S-band noise floor" | Handbook design goal < −20 dB; measured NEBS median −20.7 dB. |

## Open questions for ISRO / the data provider

- Meaning and geolocation impact of exception code 64.
- Whether and when S-band calibration scale factors and crosstalk will be populated, and whether the product has been reprocessed.
- Whether NEBS is σ⁰- or γ⁰-referenced in practice.
