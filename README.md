# satmaps

Print-ready figures from satellite data: one product, or two that overlap. **SAR** (NISAR, Sentinel-1, EOS-04) and **optical** (Sentinel-2, LISS-IV). Runs on your own machine; nothing is uploaded.

<p align="center">
  <img src="docs/img/layout_zooms.jpg" alt="NISAR L-band with three zoom panels" width="30%">
  <img src="docs/img/layout_sar_optical.jpg" alt="Sentinel-1 next to Sentinel-2" width="30%">
  <img src="docs/img/theme_newspaper.jpg" alt="NISAR L-band, newspaper theme" width="30%">
</p>

## Install

Python 3.11 or newer.

```bash
git clone https://github.com/carbform/satmaps && cd satmaps
pip install -e ".[rasters,app]"
```

## Use

Unzip your products into `data/` (or set `SATMAPS_DATA_DIR`, or pass `--data-dir`). Then either open the app:

```bash
satmaps app                                 # http://localhost:8501
```

or make a figure from the command line:

```bash
satmaps quick a.h5 b.SAFE                   # a small PNG of the area the two products share
satmaps quick a.h5 b.SAFE --quality publication --theme newspaper
satmaps quick a.h5 --sar-fcc cross,co,ratio # false colour composite: which channel goes on R, G, B
satmaps quick b.SAFE --optical-fcc nir,red,green
satmaps quick a.h5 --zoom "27.5,94.1,6=Hill edge" --zoom 27.6,94.3,6   # zoom side panels for one product: LAT,LON,KM[=NAME]
satmaps quick a.h5 b.SAFE --save-job fig.toml   # also save the job file; edit it, then `satmaps run fig.toml`
```

```python
import satmaps
satmaps.render(["a.h5", "b.SAFE"], theme="newspaper", quality="publication", title="Two radars")
```

`satmaps --help` lists the other commands (`inspect`, `run`, `init`, `list`). Job files and the wording files that change what a figure says are in [jobs/](jobs/).

## Gallery

The Brahmaputra near Dibrugarh, Assam, seen by all five sensors. Every figure carries a small "made with satmaps" banner in its top right corner.

**Themes**

<table>
  <tr>
    <td align="center" width="20%"><img src="docs/img/theme_neo_retro.jpg" alt="neo_retro"><br><sub>neo_retro</sub></td>
    <td align="center" width="20%"><img src="docs/img/theme_minimal.jpg" alt="minimal"><br><sub>minimal</sub></td>
    <td align="center" width="20%"><img src="docs/img/theme_neo_brutal.jpg" alt="neo_brutal"><br><sub>neo_brutal</sub></td>
    <td align="center" width="20%"><img src="docs/img/theme_newspaper.jpg" alt="newspaper"><br><sub>newspaper</sub></td>
    <td align="center" width="20%"><img src="docs/img/theme_xkcd.jpg" alt="xkcd"><br><sub>xkcd</sub></td>
  </tr>
</table>

**Layouts**

<table>
  <tr>
    <td align="center" width="33%"><img src="docs/img/layout_zooms.jpg" alt="One product with zoom panels"><br><sub>One product with zoom panels</sub></td>
    <td align="center" width="33%"><img src="docs/img/layout_side_by_side.jpg" alt="Two products side by side"><br><sub>Two products side by side</sub></td>
    <td align="center" width="33%"><img src="docs/img/layout_sar_optical.jpg" alt="Radar next to optical"><br><sub>Radar next to optical</sub></td>
  </tr>
  <tr>
    <td align="center" width="33%"><img src="docs/img/layout_bands.jpg" alt="Optical, band by band"><br><sub>Optical, band by band</sub></td>
    <td align="center" width="33%"><img src="docs/img/layout_optical_fcc.jpg" alt="Optical false colour (NIR, red, green)"><br><sub>Optical false colour (NIR, red, green)</sub></td>
    <td align="center" width="33%"><img src="docs/img/layout_tiles.jpg" alt="Four products tiled (job file)"><br><sub>Four products tiled (job file)</sub></td>
  </tr>
</table>

Regenerate them with `python docs/gallery.py` (needs the products in `data/`).

## Caveats

The NISAR S-band product is still unfinished: its calibration is unpopulated and noise is not subtracted. Noise-dominated pixels are drawn grey and every figure prints the caveats. Read [docs/processing-notes.md](docs/processing-notes.md) before quoting a number.

More: [architecture](docs/architecture.md) · [pipelines](docs/pipelines.md) · [design language](docs/design-language.md)

## Licence

Code: MIT, see [LICENSE](LICENSE). Data and source documents belong to their providers; figures made from NISAR data should credit "NASA-ISRO NISAR".
