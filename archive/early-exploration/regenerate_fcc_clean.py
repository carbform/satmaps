"""Rebuild the Bengaluru FCC in a clean white, map-first layout.

The map raster is taken from FCC_HH_HV_blr_template.png so its radar colors
and pixel values remain unchanged; only the surrounding infographic is rebuilt.
"""
from pathlib import Path
from PIL import Image
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FormatStrFormatter

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "FCC_HH_HV_blr_template.png"
OUTPUT = HERE / "FCC_HH_HV_blr_clean.png"

# Extent of the Bengaluru ROI used by explore_gcov_v3.ipynb.
LON_MIN, LON_MAX = 77.50, 77.70
LAT_MIN, LAT_MAX = 12.90, 13.10
with Image.open(TEMPLATE) as src:
    src = src.convert("RGB")
    w, h = src.size
    # Raster plot interior only; omit the original labels and side panel.
    map_image = src.crop((round(w * .087), round(h * .084),
                          round(w * .646), round(h * .898)))

ink, gray = "#1A1A1A", "#666666"
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Liberation Serif"],
    "font.size": 9,
    "text.color": ink,
    "axes.labelcolor": ink,
    "xtick.color": ink,
    "ytick.color": ink,
})
fig = plt.figure(figsize=(14, 14), facecolor="white")

# Original-style title hierarchy, with ample space for the map.
fig.text(.5, .972, "NISAR S-Band SAR — False Color Composite",
         ha="center", va="top", fontsize=18, weight="bold")
fig.text(.5, .944, "Dual-pol (HH/HV)  |  Ascending Pass  |  10 m Resolution",
         ha="center", va="top", fontsize=13, weight="bold")
fig.text(.5, .919, "Bengaluru", ha="center", va="top", fontsize=14, weight="bold")

# Large centered map with restrained coordinate axes and the original SAR colors.
ax = fig.add_axes([.16, .285, .68, .615])
ax.imshow(map_image, extent=[LON_MIN, LON_MAX, LAT_MIN, LAT_MAX],
          origin="upper", interpolation="nearest", aspect="equal")
ax.set_xlim(LON_MIN, LON_MAX)
ax.set_ylim(LAT_MIN, LAT_MAX)
ax.set_xlabel("Longitude (°E)", fontsize=11, labelpad=4)
ax.set_ylabel("Latitude (°N)", fontsize=11, labelpad=4)
ax.set_xticks([77.53, 77.55, 77.58, 77.60, 77.62, 77.65, 77.67])
ax.set_yticks([12.90, 12.93, 12.95, 12.97, 13.00, 13.03, 13.05, 13.07, 13.10])
ax.xaxis.set_major_formatter(FormatStrFormatter("%.2f°"))
ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f°"))
ax.tick_params(labelsize=9, length=3, width=.7, pad=3)
for spine in ax.spines.values():
    spine.set_linewidth(.9)
    spine.set_color(ink)

# Compact two-column legend and acquisition notes below the map.
fig.add_artist(plt.Line2D([.07, .93], [.245, .245], transform=fig.transFigure,
                          color="#B8B8B8", linewidth=.8))
fig.text(.075, .224, "RGB CHANNEL ASSIGNMENT", fontsize=10, weight="bold", va="center")
for x, color, label in [
    (.075, "#ff0000", "R  HH backscatter (γ⁰, dB)"),
    (.355, "#008000", "G  HV backscatter (γ⁰, dB)"),
    (.635, "#0000ff", "B  HH/HV ratio (dB)"),
]:
    fig.add_artist(Rectangle((x, .191), .014, .014, transform=fig.transFigure,
                             facecolor=color, edgecolor="#333333", linewidth=.6))
    fig.text(x + .021, .198, label, fontsize=8.2, va="center")
fig.text(.075, .173, "Red/magenta: urban, bare soil   ·   Green: vegetation, crops   ·   Dark: water   ·   Cyan/teal: mixed   ·   Yellow: double-bounce",
         fontsize=8, color=gray, va="center")

fig.text(.075, .135, "ACQUISITION DETAILS", fontsize=10, weight="bold", va="center")
fig.text(.075, .108, "NISAR S-Band SAR  ·  Dual-pol (HH/HV)  ·  Ascending pass  ·  03 February 2026, 00:24 UTC  ·  10 m  ·  2–98 percentile stretch",
         fontsize=8.5, va="center")
fig.text(.5, .055, "Data: NASA–ISRO NISAR Mission  |  Product: L2 GCOV  |  Visualisation: Sarat (NRSC/ISRO)",
         ha="center", va="center", fontsize=8, color=gray)

fig.savefig(OUTPUT, dpi=250, facecolor="white")
print(f"Saved {OUTPUT}")
