#!/usr/bin/env python3
"""
Social Media Edition: The Mighty Brahmaputra Braided Maze
Zoomed in on the braided river channels with 100% valid data coverage (Zero No-Data).
Features:
- Exact Simen River tributary confluence: (27.591°N, 94.8725°E)
- Sand Bars callout at (27.565°N, 94.905°E)
- Horizontal radar color legend placed neatly below the map panel
- Preserving all user modifications and attribution
"""

import os
import warnings

import h5py
import numpy as np
from pyproj import Transformer
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe

warnings.filterwarnings("ignore", category=RuntimeWarning)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(SCRIPT_DIR, "NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5")
GRIDS_PREFIX = "science/SSAR/GCOV/grids/frequencyA"

# Optimized slice for 100% valid SAR data covering Simen River, Braided Chars, and Dibrugarh
ROW_START, ROW_END = 27800, 30880  # 3,080 pixels = 30.8 km
COL_START, COL_END = 11500, 14400  # 2,900 pixels = 29.0 km

def render_river_zoom():
    print(f"Loading 100% valid river slice: Rows [{ROW_START}:{ROW_END}], Cols [{COL_START}:{COL_END}]...")
    with h5py.File(FILE_PATH, 'r') as f:
        grids = f[GRIDS_PREFIX]
        x_utm = grids['xCoordinates'][:]
        y_utm = grids['yCoordinates'][:]
        epsg = int(grids['projection'][()])

    nrows = ROW_END - ROW_START
    ncols = COL_END - COL_START
    print(f"Array size: {nrows} x {ncols} = {nrows*ncols/1e6:.2f} Mpx (Full 10 m resolution)")

    # Sample percentiles from the slice
    with h5py.File(FILE_PATH, 'r') as f:
        co_samp = f[f'{GRIDS_PREFIX}/HHHH'][ROW_START:ROW_END:6, COL_START:COL_END:6].astype(np.float32)
        cr_samp = f[f'{GRIDS_PREFIX}/HVHV'][ROW_START:ROW_END:6, COL_START:COL_END:6].astype(np.float32)
        m_samp = f[f'{GRIDS_PREFIX}/mask'][ROW_START:ROW_END:6, COL_START:COL_END:6]

    valid_samp = (m_samp == 1) & (co_samp > 0) & (cr_samp > 0)
    co_db_samp = 10.0 * np.log10(co_samp[valid_samp])
    cr_db_samp = 10.0 * np.log10(cr_samp[valid_samp])
    rt_db_samp = co_db_samp - cr_db_samp

    co_min, co_max = np.percentile(co_db_samp, [2, 98.5])
    cr_min, cr_max = np.percentile(cr_db_samp, [2, 98.5])
    rt_min, rt_max = np.percentile(rt_db_samp, [2, 98.5])
    del co_samp, cr_samp, m_samp, valid_samp, co_db_samp, cr_db_samp, rt_db_samp

    print(f"Stretches (dB): HH [{co_min:.1f}, {co_max:.1f}], HV [{cr_min:.1f}, {cr_max:.1f}], Ratio [{rt_min:.1f}, {rt_max:.1f}]")

    # Stream into RGBA
    rgba = np.zeros((nrows, ncols, 4), dtype=np.uint8)
    block_rows = 1024
    with h5py.File(FILE_PATH, 'r') as f:
        co_ds = f[f'{GRIDS_PREFIX}/HHHH']
        cr_ds = f[f'{GRIDS_PREFIX}/HVHV']
        m_ds = f[f'{GRIDS_PREFIX}/mask']

        for r0 in range(0, nrows, block_rows):
            r1 = min(r0 + block_rows, nrows)
            co_blk = co_ds[ROW_START+r0:ROW_START+r1, COL_START:COL_END].astype(np.float32)
            cr_blk = cr_ds[ROW_START+r0:ROW_START+r1, COL_START:COL_END].astype(np.float32)
            m_blk = m_ds[ROW_START+r0:ROW_START+r1, COL_START:COL_END]

            valid = (m_blk == 1) & (co_blk > 0) & (cr_blk > 0)

            with np.errstate(divide='ignore', invalid='ignore'):
                co_db = 10.0 * np.log10(co_blk)
                cr_db = 10.0 * np.log10(cr_blk)
                rt_db = co_db - cr_db

            r = np.clip((co_db - co_min) / (co_max - co_min + 1e-6), 0, 1)
            g = np.clip((cr_db - cr_min) / (cr_max - cr_min + 1e-6), 0, 1)
            b = np.clip((rt_db - rt_min) / (rt_max - rt_min + 1e-6), 0, 1)

            # Punchy vibrant stretch
            r = np.power(r, 0.94)
            g = np.power(g, 0.94)
            b = np.power(b, 1.05)

            r[~valid] = 0
            g[~valid] = 0
            b[~valid] = 0

            rgba[r0:r1, :, 0] = (r * 255).astype(np.uint8)
            rgba[r0:r1, :, 1] = (g * 255).astype(np.uint8)
            rgba[r0:r1, :, 2] = (b * 255).astype(np.uint8)
            rgba[r0:r1, :, 3] = 255  # 100% valid data!

    # Geographic coordinates
    t = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    x_roi = x_utm[COL_START:COL_END]
    y_roi = y_utm[ROW_START:ROW_END]
    mid_x = len(x_roi) // 2
    mid_y = len(y_roi) // 2
    _, lat_1d = t.transform(np.full_like(y_roi, x_roi[mid_x]), y_roi)
    lon_1d, _ = t.transform(x_roi, np.full_like(x_roi, y_roi[mid_y]))
    extent = [float(lon_1d.min()), float(lon_1d.max()), float(lat_1d.min()), float(lat_1d.max())]

    print("Composing high-impact social media layout...")
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Liberation Sans", "Helvetica", "Arial"]

    fig = plt.figure(figsize=(16, 12.0), facecolor="#07090e")
    # Tightly framed to save space: panel spans 0.04 to 0.96
    ax = fig.add_axes([0.04, 0.085, 0.92, 0.88])

    # Show 100% full-bleed SAR Raster
    ax.imshow(rgba, extent=extent, origin="upper", aspect="equal", interpolation="bilinear")
    ax.set_facecolor("#07090e")

    for spine in ax.spines.values():
        spine.set_color("#222f46")
        spine.set_linewidth(1.8)

    ax.tick_params(colors="#64748b", labelsize=9.5, length=4, width=1.0)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°E'))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°N'))
    ax.grid(True, color="#ffffff", alpha=0.15, linestyle=":", linewidth=0.5)

    # ─────────────────────────────────────────────────────────────
    # 1. SLEEK TITLE BADGE (Top-Left) - Preserving User Changes
    # ─────────────────────────────────────────────────────────────
    title_box = dict(boxstyle="square,pad=0.7", facecolor="#06090e", edgecolor="#3b82f6", linewidth=1.8, alpha=0.94)
    ax.text(
        0.025, 0.965,
        "THE BRAHMAPUTRA",
        transform=ax.transAxes,
        ha="left", va="top",
        fontsize=16,
        fontweight="bold",
        color="#ffffff",
        linespacing=1.3,
        bbox=title_box,
        zorder=10
    )

    ax.text(
        0.025, 0.882,
        " S-Band SAR (HH/HV)  |  10 m Resolution  | ",
        transform=ax.transAxes,
        ha="left", va="top",
        fontsize=9.5,
        fontweight="bold",
        color="#93c5fd",
        bbox=dict(boxstyle="square,pad=0.4", facecolor="#0b1329", edgecolor="#1d4ed8", linewidth=1.0, alpha=0.92),
        zorder=10
    )

    # ─────────────────────────────────────────────────────────────
    # 2. GEOGRAPHIC CALLOUTS - Preserving User Changes
    # ─────────────────────────────────────────────────────────────

    # A) Simen River Confluence: (27.591°N, 94.8725°E)
    sim_lat, sim_lon = 27.591, 94.8725
    ax.plot(sim_lon, sim_lat, marker="o", markersize=6.5, color="#38bdf8",
            markeredgecolor="#ffffff", markeredgewidth=1.4, zorder=12)
    ax.annotate(
        "SIMEN RIVER\nTributary joining the Brahmaputra",
        xy=(sim_lon, sim_lat),
        xytext=(-50, 35),
        textcoords="offset points",
        fontsize=9.5,
        fontweight="bold",
        color="#ffffff",
        bbox=dict(boxstyle="round,pad=0.45", fc="#0f172a", ec="#38bdf8", lw=1.5, alpha=0.92),
        arrowprops=dict(arrowstyle="->", color="#38bdf8", lw=1.8, connectionstyle="arc3,rad=-0.15"),
        path_effects=[pe.withStroke(linewidth=2, foreground="#000000")],
        zorder=12
    )

    # B) Sand Bars: (27.565°N, 94.905°E) - User's coordinates & label
    char_lat, char_lon = 27.565, 94.905
    ax.plot(char_lon, char_lat, marker="o", markersize=6.5, color="#f43f5e",
            markeredgecolor="#ffffff", markeredgewidth=1.4, zorder=12)
    ax.annotate(
        "SAND BARS\n",
        xy=(char_lon, char_lat),
        xytext=(-55, -45),
        textcoords="offset points",
        fontsize=9.5,
        fontweight="bold",
        color="#ffffff",
        bbox=dict(boxstyle="round,pad=0.45", fc="#0f172a", ec="#f43f5e", lw=1.5, alpha=0.92),
        arrowprops=dict(arrowstyle="->", color="#f43f5e", lw=1.8, connectionstyle="arc3,rad=0.15"),
        path_effects=[pe.withStroke(linewidth=2, foreground="#000000")],
        zorder=12
    )

    # ─────────────────────────────────────────────────────────────
    # 3. SCALE BAR (Bottom-Left)
    # ─────────────────────────────────────────────────────────────
    lat_center = (extent[2] + extent[3]) / 2
    km_per_deg_lon = 111.32 * np.cos(np.radians(lat_center))
    bar_km = 5.0
    bar_deg = bar_km / km_per_deg_lon

    bar_x0 = extent[0] + 0.035 * (extent[1] - extent[0])
    bar_y0 = extent[2] + 0.045 * (extent[3] - extent[2])

    ax.plot([bar_x0, bar_x0 + bar_deg], [bar_y0, bar_y0], color="#ffffff", lw=4.5, solid_capstyle='butt', zorder=15)
    ax.plot([bar_x0, bar_x0 + bar_deg], [bar_y0, bar_y0], color="#000000", lw=1.8, solid_capstyle='butt', zorder=16)
    ax.text(
        bar_x0 + bar_deg / 2, bar_y0 + 0.012 * (extent[3] - extent[2]),
        f"{int(bar_km)} km", ha="center", fontsize=10, weight="bold", color="#ffffff",
        path_effects=[pe.withStroke(linewidth=2.5, foreground="#000000")],
        zorder=17
    )

    # ─────────────────────────────────────────────────────────────
    # 4. HORIZONTAL RADAR INTERPRETATION (Flush with Map Panel)
    # ─────────────────────────────────────────────────────────────
    legend_y = 0.050
    guide_items = [
        ("#140a32", "Deep Water Channels"),
        ("#addb4c", "Floodplain Vegetation & Forests"),
        ("#b548d3", "Bare Soil, Farmland & Sandbars"),
        ("#c69d9f", "Settlements & Built Structures"),
    ]

    # Exactly flush with panel edges: starts at 0.040, ends at ~0.955
    x_positions = [0.040, 0.275, 0.525, 0.770]
    for x_pos, (hex_col, desc) in zip(x_positions, guide_items):
        # Draw small color swatch
        fig.add_artist(mpatches.FancyBboxPatch(
            (x_pos, legend_y - 0.010), 0.011, 0.020,
            boxstyle="round,pad=0.002", facecolor=hex_col, edgecolor="#ffffff",
            linewidth=0.8, transform=fig.transFigure
        ))
        # Text label
        fig.text(x_pos + 0.015, legend_y, desc,
                 fontsize=8.3, fontweight="semibold", color="#e2e8f0", va="center")

    # ─────────────────────────────────────────────────────────────
    # 5. STREAMLINED FOOTER (Flush with Map Panel at 0.04 and 0.96)
    # ─────────────────────────────────────────────────────────────
    footer_y = 0.018
    fig.text(
        0.04, footer_y,
        "DATA: NASA-ISRO Synthetic Aperture Radar (NISAR)  |  L2 GCOV (Geocoded Covariance)  |  Acquired: 25 Sep 2026",
        fontsize=9, color="#94a3b8", weight="bold"
    )
    fig.text(
        0.96, footer_y,
        "VISUALIZATION: Sarat (NRSC / ISRO) | carbform.github.io ",
        ha="right", fontsize=9, color="#cbd5e1", weight="bold"
    )

    pub_path = os.path.join(SCRIPT_DIR, "NISAR_Brahmaputra_River_FCC_Publication.png")
    social_path = os.path.join(SCRIPT_DIR, "NISAR_Brahmaputra_River_FCC_Social.png")

    fig.savefig(pub_path, dpi=300, facecolor="#07090e", bbox_inches="tight")
    fig.savefig(social_path, dpi=300, facecolor="#07090e", bbox_inches="tight")

    print(f"✓ Saved updated publication image to: {pub_path}")
    print(f"✓ Saved copy to: {social_path}")
    plt.close(fig)

if __name__ == "__main__":
    render_river_zoom()
