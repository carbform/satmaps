# Design language: neo-retro

The social graphic is "neo-retro": the structural honesty of neo-brutalism (outlined boxes, small hard shadows,
monospace labels, a bento grid) with a quiet 70s tone in type and colour. It replaced two louder explorations
(dark, then "retro-brutal telemetry" with stripes, starfield and a mission patch; see `archive/design-explorations/`).

## One rule above the rest

**Style the chrome, never the data.** Panels, zooms and the split view are never filtered, glowed, textured or
recoloured. Nothing in the style may hide the provisional-calibration notice.

## Tokens (`nisar_viz.themes.NeoRetro`)

| Role | Value |
|---|---|
| Paper | `#ece4d3` |
| Card | `#f7f2e7` |
| Ink | `#23211f` |
| Muted ink | `#6b655b` |
| Title offset | `#c4673a` |
| L-band chip | `#e0b872` |
| S-band chip | `#8fbfb7` |
| Notice strip | `#f0dfb0` |
| Noise grey (also in the data) | `#3a3a40` |

Fonts: Gillius ADF Bold for the title, IBM Plex Mono for labels. Both are optional; matplotlib falls back to DejaVu.

## Structure

- Outlines 1.5 px in ink; hard shadow (no blur) offset a few pixels.
- Bento layout: header, one hero, supporting zoom panels, legend, notice, credits.
- One soft offset behind the title, nothing else decorative.

## Do / don't

- Do keep every claim on the graphic traceable (noise share, wavelengths from the file centre frequencies).
- Do say when colours are not comparable (per-band stretch) and when dB are provisional.
- Don't add scanlines, glow, stripes, logos or gradients; don't use neon.

The `ls-clean` and `*-publication` figures use a plain white style on purpose.
