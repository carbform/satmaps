# Design language: neo-retro

The social graphic is "neo-retro": the structural honesty of neo-brutalism (outlined boxes, small hard shadows,
monospace labels, a bento grid) with a quiet 70s tone in type and colour. It replaced two louder explorations
(dark, then "retro-brutal telemetry" with stripes, starfield and a mission patch). Those explorations were removed from the repository; they are in the git history before the cleanup of Oct 2026.

## One rule above the rest

**Style the chrome, never the data.** Panels, zooms and the split view are never filtered, glowed, textured or
recoloured. Nothing in the style may hide the provisional-calibration notice.

## Tokens (`satviz.themes.neo_retro.NeoRetro`)

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

## Wording

All text on the figures is in `layouts/*.toml`; facts (date, wavelengths, noise shares) are filled in from the data files.
See the README section "Layout files".

## Do / don't

- Do keep every claim on the graphic traceable (noise share, wavelengths from the file centre frequencies).
- Do say when colours are not comparable (per-band stretch) and when dB are provisional.
- Don't add scanlines, glow, stripes, logos or gradients; don't use neon.


## Other themes

All five themes obey the one rule above and share the page geometry; a test compares the data pixels across them.

- **minimal**: white page, hairline rules, no shadow.
- **neo_brutal**: thick outlines, big offset shadow, flat saturated colour.
- **newspaper**: kicker, headline and dek between rules; serif type (Source Serif Pro, PT Serif, DejaVu Serif); hairline rules in place of boxes; the notice strip is a tinted band. Inspired by a printed page's structure; it has no masthead, name or branding.
- **xkcd**: hand-drawn lines and a comic typeface for the chrome. `Theme.finish` takes the sketch off every artist inside a data axes, label boxes included, so scale bars, zoom boxes and the split line are drawn exactly.

Contrast: ink, muted text and chip text must reach 4.5:1 (WCAG 2.2, normal text) on their backgrounds in every theme.
