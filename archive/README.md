# Archive

History only. Nothing here is maintained, linted or tested, and none of it is imported by `nisar_viz`.
Each script expects the granules (and in some cases GeoTIFFs) next to it, with the filenames hard-coded inside.

- `early-exploration/`: first scripts from the Bengaluru and early Brahmaputra work (HDF5 exploration, GeoTIFF export,
  first false-colour and social graphics). `h5_struct.txt` is a dump of an S-band granule's group/dataset layout.
- `design-explorations/`: the S-band-only social graphics and the design iterations that led to the current
  "neo-retro" style (dark, neo-brutal, retro-brutal, retro-space). They import the two older modules
  `nisar_brahmaputra_pipeline.py` and `nisar_brahmaputra_figures.py`, which are copied alongside so they stay
  self-consistent. Run them from this folder with the `.h5` files placed next to the scripts.

The maintained equivalents are in `src/nisar_viz/`. The first processing assessment (`docs/first-assessment.md`)
is also superseded; see `docs/processing-notes.md` for the corrected statements.
