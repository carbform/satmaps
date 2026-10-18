#!/usr/bin/env python3
"""
NISAR S-Band GCOV River Visualization Pipeline
Focus: Brahmaputra River (Dibrugarh Reach & Bogibeel Bridge)
Data: NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5

Preserves the zero-copy, memory-safe pipeline of explore_gcov_v3.py while
generating high-resolution scientific and thematic visualizations of the braided river system.
"""

import os
import warnings
from datetime import datetime
from collections import OrderedDict

import h5py
import numpy as np
from pyproj import Transformer
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import ultraplot as uplt

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ═══════════════════════════════════════════════════════════════
# Configuration & File Paths
# ═══════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(SCRIPT_DIR, "NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5")
GRIDS_PREFIX = "science/SSAR/GCOV/grids/frequencyA"

# Region of Interest: Brahmaputra River near Dibrugarh & Bogibeel Bridge
ROI = {
    "lat_min": 27.38,
    "lat_max": 27.72,
    "lon_min": 94.70,
    "lon_max": 95.18,
}
REGION_TITLE = "Brahmaputra River (Dibrugarh & Bogibeel Reach, Assam)"

# Key Geographic Landmarks for Annotation
LANDMARKS = [
    {"name": "Bogibeel Bridge", "lat": 27.400, "lon": 94.755, "xytext": (-60, -25)},
    {"name": "Dibrugarh", "lat": 27.472, "lon": 94.912, "xytext": (25, -25)},
    {"name": "Braided Chars (Sandbars)", "lat": 27.560, "lon": 94.880, "xytext": (-70, 30)},
]

# ═══════════════════════════════════════════════════════════════
# Core Pipeline Functions (from explore_gcov_v3.py)
# ═══════════════════════════════════════════════════════════════

def get_pol_config_from_h5(filepath):
    """Auto-detect polarisation configuration from GCOV HDF5."""
    with h5py.File(filepath, 'r') as f:
        grids = f[GRIDS_PREFIX]
        pols = [p.decode() for p in grids['listOfPolarizations'][()]]
        cov_terms = [c.decode() for c in grids['listOfCovarianceTerms'][()]]

    pol_set = set(pols)
    if pol_set & {'RH', 'RV'}:
        cfg = dict(pol_type='hybrid', co_term='RHRH', cross_term='RVRV',
                   offdiag_term='RHRV', pol1='RH', pol2='RV',
                   mode_label=f"Compact-pol ({'/'.join(pols)})")
    elif pol_set & {'HH', 'HV'}:
        cfg = dict(pol_type='dual', co_term='HHHH', cross_term='HVHV',
                   offdiag_term='HHHV', pol1='HH', pol2='HV',
                   mode_label=f"Dual-pol ({'/'.join(pols)})")
    elif pol_set & {'VV', 'VH'}:
        cfg = dict(pol_type='dual', co_term='VVVV', cross_term='VHVH',
                   offdiag_term='VVVH', pol1='VV', pol2='VH',
                   mode_label=f"Dual-pol ({'/'.join(pols)})")
    else:
        raise ValueError(f"Unknown polarisations: {pols}")

    cfg['polarisations'] = pols
    cfg['covariance_terms'] = cov_terms
    return cfg


def read_scene_info(filepath):
    """Read metadata without loading pixel layers."""
    info = OrderedDict()
    with h5py.File(filepath, 'r') as f:
        ident = f['science/SSAR/identification']
        grids = f[GRIDS_PREFIX]

        for field in ['granuleId', 'radarBand', 'orbitPassDirection', 'lookDirection',
                      'trackNumber', 'frameNumber', 'absoluteOrbitNumber',
                      'zeroDopplerStartTime', 'zeroDopplerEndTime',
                      'isDithered', 'isMixedMode', 'boundingPolygon']:
            val = ident[field][()]
            info[field] = val.decode() if isinstance(val, bytes) else val

        info['polarisations'] = [p.decode() for p in grids['listOfPolarizations'][()]]
        info['covariance_terms'] = [c.decode() for c in grids['listOfCovarianceTerms'][()]]
        info['epsg'] = int(grids['projection'][()])
        info['x_spacing_m'] = float(grids['xCoordinateSpacing'][()])
        info['y_spacing_m'] = float(grids['yCoordinateSpacing'][()])
        info['nrows'] = len(grids['yCoordinates'])
        info['ncols'] = len(grids['xCoordinates'])
        info['grid_shape'] = (info['nrows'], info['ncols'])

        params = f['science/SSAR/GCOV/metadata/processingInformation/parameters']
        info['rtc_applied'] = params['radiometricTerrainCorrectionApplied'][()].decode()
        info['noise_corrected'] = params['noiseCorrectionApplied'][()].decode()
        info['rfi_mitigated'] = params['rfiMitigationApplied'][()].decode()
    return info


def get_utm_coords(filepath):
    """Read 1-D UTM coordinate vectors."""
    with h5py.File(filepath, 'r') as f:
        grids = f[GRIDS_PREFIX]
        x = grids['xCoordinates'][:]
        y = grids['yCoordinates'][:]
        epsg = int(grids['projection'][()])
    return x, y, epsg


def utm_to_latlon_1d(x_utm, y_utm, epsg):
    """Convert 1-D UTM arrays to 1-D lat/lon along axis centers."""
    t = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    mid_x = len(x_utm) // 2
    mid_y = len(y_utm) // 2
    _, lat_1d = t.transform(np.full_like(y_utm, x_utm[mid_x]), y_utm)
    lon_1d, _ = t.transform(x_utm, np.full_like(x_utm, y_utm[mid_y]))
    return lon_1d, lat_1d


def compute_roi_indices(filepath, roi):
    """Convert lat/lon bounding box to pixel row/col index bounds."""
    x_utm, y_utm, epsg = get_utm_coords(filepath)
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    roi_x_min, roi_y_min = to_utm.transform(roi['lon_min'], roi['lat_min'])
    roi_x_max, roi_y_max = to_utm.transform(roi['lon_max'], roi['lat_max'])
    roi_x_min, roi_x_max = min(roi_x_min, roi_x_max), max(roi_x_min, roi_x_max)
    roi_y_min, roi_y_max = min(roi_y_min, roi_y_max), max(roi_y_min, roi_y_max)

    x_idx = np.where((x_utm >= roi_x_min) & (x_utm <= roi_x_max))[0]
    y_idx = np.where((y_utm >= roi_y_min) & (y_utm <= roi_y_max))[0]

    if len(x_idx) == 0 or len(y_idx) == 0:
        return None

    ix0, ix1 = int(x_idx[0]), int(x_idx[-1]) + 1
    iy0, iy1 = int(y_idx[0]), int(y_idx[-1]) + 1
    return iy0, iy1, ix0, ix1


def _roi_reservoir_percentiles(filepath, roi_idx, cfg, plow=2, phigh=98,
                               n_sample_rows=500, n_per_row=200, seed=42):
    """Reservoir-sample the ROI to compute robust percentile limits."""
    iy0, iy1, ix0, ix1 = roi_idx
    nrows = iy1 - iy0
    rng = np.random.RandomState(seed)

    n_sample_rows = min(nrows, n_sample_rows)
    row_offsets = np.sort(rng.choice(nrows, size=n_sample_rows, replace=False))

    co_samples, cross_samples, ratio_samples = [], [], []

    with h5py.File(filepath, 'r') as f:
        co_ds = f[f'{GRIDS_PREFIX}/{cfg["co_term"]}']
        cross_ds = f[f'{GRIDS_PREFIX}/{cfg["cross_term"]}']
        mask_ds = f[f'{GRIDS_PREFIX}/mask']

        for r_off in row_offsets:
            r = iy0 + int(r_off)
            co_row = co_ds[r, ix0:ix1].astype(np.float32)
            cross_row = cross_ds[r, ix0:ix1].astype(np.float32)
            mask_row = mask_ds[r, ix0:ix1]

            valid = mask_row == 1
            co_v = co_row[valid]
            cross_v = cross_row[valid]
            if co_v.size == 0:
                continue

            with np.errstate(divide='ignore', invalid='ignore'):
                co_db = 10.0 * np.log10(co_v)
                cross_db = 10.0 * np.log10(cross_v)
                ratio_db = co_db - cross_db

            for src, dst in [(co_db, co_samples), (cross_db, cross_samples),
                             (ratio_db, ratio_samples)]:
                fin = src[np.isfinite(src)]
                if fin.size == 0:
                    continue
                n_take = min(n_per_row, fin.size)
                if fin.size > n_take:
                    dst.append(fin[rng.choice(fin.size, size=n_take, replace=False)])
                else:
                    dst.append(fin)

    def _pct(samples_list):
        if not samples_list:
            return (-25.0, 5.0)
        arr = np.concatenate(samples_list)
        return tuple(np.percentile(arr, [plow, phigh]).tolist())

    return {
        'co': _pct(co_samples),
        'cross': _pct(cross_samples),
        'ratio': _pct(ratio_samples),
    }


def _build_rgba(filepath, roi_idx, cfg, limits, block_rows=1024):
    """Build memory-safe uint8 RGBA array in row-bands."""
    iy0, iy1, ix0, ix1 = roi_idx
    nrows = iy1 - iy0
    ncols = ix1 - ix0

    co_vmin, co_vmax = limits['co']
    cross_vmin, cross_vmax = limits['cross']
    ratio_vmin, ratio_vmax = limits['ratio']

    rgba = np.zeros((nrows, ncols, 4), dtype=np.uint8)

    with h5py.File(filepath, 'r') as f:
        co_ds = f[f'{GRIDS_PREFIX}/{cfg["co_term"]}']
        cross_ds = f[f'{GRIDS_PREFIX}/{cfg["cross_term"]}']
        mask_ds = f[f'{GRIDS_PREFIX}/mask']

        for r0 in range(0, nrows, block_rows):
            r1 = min(r0 + block_rows, nrows)

            co_blk = co_ds[iy0+r0:iy0+r1, ix0:ix1].astype(np.float32)
            cross_blk = cross_ds[iy0+r0:iy0+r1, ix0:ix1].astype(np.float32)
            mask_blk = mask_ds[iy0+r0:iy0+r1, ix0:ix1]

            valid = mask_blk == 1

            with np.errstate(divide='ignore', invalid='ignore'):
                co_db = 10.0 * np.log10(co_blk)
                cross_db = 10.0 * np.log10(cross_blk)
                ratio_db = co_db - cross_db
            del co_blk, cross_blk

            r = np.clip((co_db - co_vmin) / (co_vmax - co_vmin + 1e-10), 0, 1)
            g = np.clip((cross_db - cross_vmin) / (cross_vmax - cross_vmin + 1e-10), 0, 1)
            b = np.clip((ratio_db - ratio_vmin) / (ratio_vmax - ratio_vmin + 1e-10), 0, 1)
            del co_db, cross_db, ratio_db

            r[~np.isfinite(r)] = 0
            g[~np.isfinite(g)] = 0
            b[~np.isfinite(b)] = 0

            alpha = valid.astype(np.float32)

            rgba[r0:r1, :, 0] = (r * 255).astype(np.uint8)
            rgba[r0:r1, :, 1] = (g * 255).astype(np.uint8)
            rgba[r0:r1, :, 2] = (b * 255).astype(np.uint8)
            rgba[r0:r1, :, 3] = (alpha * 255).astype(np.uint8)
            del r, g, b, alpha, valid, mask_blk

    return rgba


# ═══════════════════════════════════════════════════════════════
# Visualization 1: Publication-Grade Scientific FCC
# ═══════════════════════════════════════════════════════════════

def generate_scientific_fcc(filepath, roi_idx, cfg, region_title, save_path=None):
    """Generate publication-standard FCC with scale bar and annotations."""
    iy0, iy1, ix0, ix1 = roi_idx
    nrows, ncols = iy1 - iy0, ix1 - ix0
    print(f"Generating Scientific FCC for {region_title} ({nrows}x{ncols} pixels)...")

    # Reservoir percentiles & RGBA
    limits = _roi_reservoir_percentiles(filepath, roi_idx, cfg)
    print(f"  Stretch limits (dB): CO {limits['co']}, CROSS {limits['cross']}, RATIO {limits['ratio']}")
    rgba = _build_rgba(filepath, roi_idx, cfg, limits)

    # Coordinates
    x_utm, y_utm, epsg = get_utm_coords(filepath)
    x_roi = x_utm[ix0:ix1]
    y_roi = y_utm[iy0:iy1]
    lon_1d, lat_1d = utm_to_latlon_1d(x_roi, y_roi, epsg)

    extent = [
        float(lon_1d.min()), float(lon_1d.max()),
        float(lat_1d.min()), float(lat_1d.max())
    ]

    # Metadata
    info = read_scene_info(filepath)
    pol1, pol2 = cfg["pol1"], cfg["pol2"]
    orbit_dir = info["orbitPassDirection"]
    radar_band = info["radarBand"]
    spacing = abs(info["x_spacing_m"])
    mode_label = cfg["mode_label"]

    acq_time_str = info["zeroDopplerStartTime"]
    try:
        dt = datetime.fromisoformat(acq_time_str.replace("Z", "+00:00"))
        date_label = dt.strftime("%d %B %Y, %H:%M UTC")
    except Exception:
        date_label = acq_time_str[:19] if acq_time_str else "N/A"

    title_text = (
        f"NISAR {radar_band}-Band SAR — False Color Composite\n"
        f"{mode_label}  |  {orbit_dir.capitalize()} Pass  |  {spacing:.0f} m Spatial Resolution\n"
        f"{region_title}"
    )

    # Setup layout
    fig = plt.figure(figsize=(15, 10), facecolor="white")
    gs = fig.add_gridspec(
        nrows=2, ncols=2,
        height_ratios=[12, 1],
        width_ratios=[4.8, 1.8],
    )

    ax = fig.add_subplot(gs[0, 0])
    ax_info = fig.add_subplot(gs[0, 1])
    ax_credit = fig.add_subplot(gs[1, :])

    # Plot SAR Raster
    ax.imshow(
        rgba,
        extent=extent,
        origin="upper",
        interpolation="nearest",
        aspect="equal"
    )
    ax.set_facecolor("#111111")
    for s in ax.spines.values():
        s.set_linewidth(1.2)
        s.set_color("#2b2b2b")

    ax.set_title(title_text, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Longitude (°E)", fontsize=11)
    ax.set_ylabel("Latitude (°N)", fontsize=11)

    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°'))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°'))
    ax.grid(True, color="white", alpha=0.3, linestyle="--", linewidth=0.5)

    # Geographic Landmarks & Annotations
    for lm in LANDMARKS:
        if (extent[0] <= lm["lon"] <= extent[1]) and (extent[2] <= lm["lat"] <= extent[3]):
            ax.plot(lm["lon"], lm["lat"], marker="o", markersize=6,
                    color="#ffd166", markeredgecolor="black", markeredgewidth=1.2)
            ax.annotate(
                lm["name"],
                xy=(lm["lon"], lm["lat"]),
                xytext=lm["xytext"],
                textcoords="offset points",
                fontsize=9.5,
                fontweight="bold",
                color="white",
                bbox=dict(boxstyle="round,pad=0.25", fc="#222222", ec="#ffd166", lw=1.2, alpha=0.85),
                arrowprops=dict(arrowstyle="->", color="#ffd166", lw=1.2),
                path_effects=[pe.withStroke(linewidth=2, foreground="black")]
            )

    # Scale Bar (5 km)
    lat_center = (extent[2] + extent[3]) / 2
    km_per_deg_lon = 111.32 * np.cos(np.radians(lat_center))
    bar_km = 5.0
    bar_deg = bar_km / km_per_deg_lon

    bar_x0 = extent[0] + 0.04 * (extent[1] - extent[0])
    bar_y0 = extent[2] + 0.04 * (extent[3] - extent[2])

    ax.plot([bar_x0, bar_x0 + bar_deg], [bar_y0, bar_y0], color="white", lw=4, solid_capstyle='butt')
    ax.plot([bar_x0, bar_x0 + bar_deg], [bar_y0, bar_y0], color="black", lw=1.5, solid_capstyle='butt')
    ax.text(
        bar_x0 + bar_deg / 2,
        bar_y0 + 0.015 * (extent[3] - extent[2]),
        f"{int(bar_km)} km",
        ha="center", fontsize=9.5, weight="bold", color="white",
        path_effects=[pe.withStroke(linewidth=2, foreground="black")]
    )

    # Info Panel
    ax_info.axis("off")
    y = 0.98

    ax_info.text(0.02, y, "RGB CHANNEL ASSIGNMENT", fontsize=11, weight="bold")
    y -= 0.055

    rgb_items = [
        ("red", f"R : {pol1} backscatter (γ⁰, dB)"),
        ("green", f"G : {pol2} backscatter (γ⁰, dB)"),
        ("blue", f"B : {pol1}/{pol2} ratio (dB)"),
    ]
    for c, txt in rgb_items:
        rect = mpatches.FancyBboxPatch(
            (0.02, y - 0.02), 0.08, 0.035,
            boxstyle="round,pad=0.003", facecolor=c, edgecolor="black", linewidth=0.6,
            transform=ax_info.transAxes, clip_on=False
        )
        ax_info.add_patch(rect)
        ax_info.text(0.14, y, txt, fontsize=9.5, family="monospace")
        y -= 0.055

    ax_info.text(0.0, y, "INTERPRETATION GUIDE", fontsize=11, weight="bold")
    y -= 0.055

    interp_items = [
        ("Black / Dark", "Calm water, specular reflection"),
        ("Green", "Dense floodplain vegetation & tea gardens"),
        ("Red / Magenta", "Bare sandbars (chars) & exposed soil"),
        ("Cyan / Blue", "Mixed moisture & rough water channels"),
        ("Bright Yellow", "Double-bounce (Bogibeel Bridge, urban)"),
    ]
    for n, d in interp_items:
        ax_info.text(0.0, y, n, fontsize=9.5, weight="bold")
        ax_info.text(0.38, y, d, fontsize=9.0)
        y -= 0.048

    y -= 0.02
    ax_info.text(0.0, y, "ACQUISITION DETAILS", fontsize=11, weight="bold")
    y -= 0.055

    details = [
        ("Mission", "NASA-ISRO SAR (NISAR)"),
        ("Sensor", f"SSAR ({radar_band}-Band)"),
        ("Mode", mode_label),
        ("Pass", f"{orbit_dir.capitalize()} (Track {info['trackNumber']}, Frame {info['frameNumber']})"),
        ("Date", date_label),
        ("Resolution", f"{spacing:.0f} m"),
        ("Stretch", f"2–98 percentile"),
        ("EPSG", f"{info['epsg']} (UTM 46N)"),
    ]
    for k, v in details:
        ax_info.text(0.0, y, f"{k:11s}: {v}", fontsize=9.0, family="monospace")
        y -= 0.048

    # Credit Bar
    ax_credit.axis("off")
    ax_credit.text(
        0.5, 0.5,
        "Data: NASA–ISRO NISAR Mission  |  Product: L2 GCOV (Geocoded Covariance)  |  Visualisation: Sarat (NRSC/ISRO)",
        ha="center", va="center", fontsize=9.5, color="dimgray"
    )

    fig.subplots_adjust(left=0.07, right=0.98, top=0.92, bottom=0.02, wspace=0.04, hspace=0.05)

    if save_path:
        fig.savefig(save_path, dpi=300, facecolor="white", bbox_inches="tight")
        print(f"  ✓ Saved: {save_path}")

    plt.close(fig)
    return rgba


# ═══════════════════════════════════════════════════════════════
# Visualization 2: Multi-Panel Polarimetric Science Explorer
# ═══════════════════════════════════════════════════════════════

def generate_polarimetric_multipanel(filepath, roi_idx, cfg, region_title, save_path=None, subsample=2):
    """
    Generate 4-panel polarimetric analysis:
    1. Co-pol HH (dB)
    2. Cross-pol HV (dB)
    3. Dual-pol Radar Vegetation Index (DpRVI)
    4. RGB Pauli / Surface-Volume Decomposition
    """
    iy0, iy1, ix0, ix1 = roi_idx
    print(f"Generating Polarimetric Multi-panel analysis (subsample={subsample})...")

    with h5py.File(filepath, 'r') as f:
        co = f[f'{GRIDS_PREFIX}/{cfg["co_term"]}'][iy0:iy1:subsample, ix0:ix1:subsample].astype(np.float32)
        cross = f[f'{GRIDS_PREFIX}/{cfg["cross_term"]}'][iy0:iy1:subsample, ix0:ix1:subsample].astype(np.float32)
        mask = f[f'{GRIDS_PREFIX}/mask'][iy0:iy1:subsample, ix0:ix1:subsample]

    valid = (mask == 1) & (co > 0) & (cross > 0)

    # Convert to dB
    co_db = np.where(valid, 10.0 * np.log10(co), np.nan)
    cross_db = np.where(valid, 10.0 * np.log10(cross), np.nan)

    # Dual-Pol Radar Vegetation Index (DpRVI): 4 * HV / (HH + HV)
    # Scaled 0 to 1 (0 = water / bare soil, 1 = dense forest canopy)
    dprvi = np.where(valid, (4.0 * cross) / (co + cross + 1e-10), np.nan)
    dprvi = np.clip(dprvi, 0, 1)

    # Dual-Pol Pauli Approximation
    # R: |HH - HV| / sqrt(2) -> double bounce / urban / bridge
    # G: 2 * HV -> volume scattering (vegetation)
    # B: |HH + HV| / sqrt(2) -> surface scattering (rough water / soil)
    co_amp = np.sqrt(np.maximum(co, 0))
    cross_amp = np.sqrt(np.maximum(cross, 0))
    
    pauli_r = np.abs(co_amp - cross_amp) / np.sqrt(2.0)
    pauli_g = 2.0 * cross_amp
    pauli_b = (co_amp + cross_amp) / np.sqrt(2.0)

    def norm_band(arr):
        v1, v2 = np.nanpercentile(arr[valid], [2, 98])
        return np.clip((arr - v1) / (v2 - v1 + 1e-10), 0, 1)

    pr_n = norm_band(pauli_r)
    pg_n = norm_band(pauli_g)
    pb_n = norm_band(pauli_b)
    pauli_rgb = np.dstack([pr_n, pg_n, pb_n])
    pauli_rgb[~valid] = 0

    # Coordinates
    x_utm, y_utm, epsg = get_utm_coords(filepath)
    x_roi = x_utm[ix0:ix1:subsample]
    y_roi = y_utm[iy0:iy1:subsample]
    lon_1d, lat_1d = utm_to_latlon_1d(x_roi, y_roi, epsg)
    extent = [float(lon_1d.min()), float(lon_1d.max()), float(lat_1d.min()), float(lat_1d.max())]

    # Setup 2x2 figure
    fig, axes = plt.subplots(2, 2, figsize=(16, 14), facecolor="white")
    axes = axes.ravel()

    # Panel 1: HH Backscatter
    co_fin = co_db[valid & np.isfinite(co_db)]
    cmin, cmax = np.percentile(co_fin, [2, 98])
    im1 = axes[0].imshow(co_db, extent=extent, cmap="gray", vmin=cmin, vmax=cmax, origin="upper", aspect="equal")
    axes[0].set_title("(a) Co-Pol Backscatter γ⁰_HH (dB) — Surface & Double Bounce", fontsize=12, weight="bold")
    axes[0].set_ylabel("Latitude (°N)")
    plt.colorbar(im1, ax=axes[0], label="γ⁰_HH (dB)", shrink=0.7)

    # Panel 2: HV Backscatter
    cr_fin = cross_db[valid & np.isfinite(cross_db)]
    crmin, crmax = np.percentile(cr_fin, [2, 98])
    im2 = axes[1].imshow(cross_db, extent=extent, cmap="viridis", vmin=crmin, vmax=crmax, origin="upper", aspect="equal")
    axes[1].set_title("(b) Cross-Pol Backscatter γ⁰_HV (dB) — Volume Scattering", fontsize=12, weight="bold")
    plt.colorbar(im2, ax=axes[1], label="γ⁰_HV (dB)", shrink=0.7)

    # Panel 3: DpRVI
    im3 = axes[2].imshow(dprvi, extent=extent, cmap="YlGn", vmin=0.0, vmax=0.8, origin="upper", aspect="equal")
    axes[2].set_title("(c) Dual-Pol Radar Vegetation Index (DpRVI) — Canopy & Wetlands", fontsize=12, weight="bold")
    axes[2].set_xlabel("Longitude (°E)")
    axes[2].set_ylabel("Latitude (°N)")
    plt.colorbar(im3, ax=axes[2], label="DpRVI (0 to 1)", shrink=0.7)

    # Panel 4: Pauli RGB Decomposition
    axes[3].imshow(pauli_rgb, extent=extent, origin="upper", aspect="equal")
    axes[3].set_title("(d) Dual-Pol Pauli RGB [R: |HH-HV|, G: 2·HV, B: |HH+HV|]", fontsize=12, weight="bold")
    axes[3].set_xlabel("Longitude (°E)")

    for ax in axes:
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°'))
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°'))
        ax.grid(True, color="white", alpha=0.25, linestyle=":", linewidth=0.5)

    plt.suptitle(f"NISAR S-Band Polarimetric Analysis — {region_title}\nAcquired 25-Sep-2026 (Post-Monsoon Peak Flow) | 10 m Resolution",
                 fontsize=14, weight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.02, 1, 0.95])

    if save_path:
        fig.savefig(save_path, dpi=300, facecolor="white", bbox_inches="tight")
        print(f"  ✓ Saved: {save_path}")

    plt.close(fig)


# ═══════════════════════════════════════════════════════════════
# Visualization 3: Ultra-Zoom on Bogibeel Bridge & Braided River
# ═══════════════════════════════════════════════════════════════

def generate_bogibeel_zoom(filepath, save_path=None):
    """Generate full 10 m resolution inset on Bogibeel Bridge crossing."""
    # Bogibeel Bridge bounding box
    roi_bridge = {
        "lat_min": 27.375,
        "lat_max": 27.425,
        "lon_min": 94.730,
        "lon_max": 94.780,
    }
    roi_idx = compute_roi_indices(filepath, roi_bridge)
    if roi_idx is None:
        print("  Could not find bridge ROI indices!")
        return

    iy0, iy1, ix0, ix1 = roi_idx
    print(f"Generating Bogibeel Bridge Ultra-Zoom (full 10m res, {iy1-iy0}x{ix1-ix0} px)...")

    cfg = get_pol_config_from_h5(filepath)
    limits = _roi_reservoir_percentiles(filepath, roi_idx, cfg)
    rgba = _build_rgba(filepath, roi_idx, cfg, limits)

    x_utm, y_utm, epsg = get_utm_coords(filepath)
    x_roi = x_utm[ix0:ix1]
    y_roi = y_utm[iy0:iy1]
    lon_1d, lat_1d = utm_to_latlon_1d(x_roi, y_roi, epsg)
    extent = [float(lon_1d.min()), float(lon_1d.max()), float(lat_1d.min()), float(lat_1d.max())]

    fig, ax = plt.subplots(figsize=(10, 10), facecolor="black")
    ax.imshow(rgba, extent=extent, origin="upper", aspect="equal")
    ax.set_facecolor("black")

    # Annotate Bogibeel Bridge
    ax.annotate(
        "Bogibeel Bridge (4.94 km)\nRail & Road Steel Truss",
        xy=(94.755, 27.400),
        xytext=(94.740, 27.418),
        fontsize=11, fontweight="bold", color="yellow",
        bbox=dict(boxstyle="round,pad=0.4", fc="#111111", ec="yellow", lw=1.5, alpha=0.9),
        arrowprops=dict(arrowstyle="->", color="yellow", lw=2),
        path_effects=[pe.withStroke(linewidth=2, foreground="black")]
    )

    # Scale Bar (1 km)
    lat_center = (extent[2] + extent[3]) / 2
    km_per_deg_lon = 111.32 * np.cos(np.radians(lat_center))
    bar_km = 1.0
    bar_deg = bar_km / km_per_deg_lon

    bar_x0 = extent[0] + 0.05 * (extent[1] - extent[0])
    bar_y0 = extent[2] + 0.05 * (extent[3] - extent[2])

    ax.plot([bar_x0, bar_x0 + bar_deg], [bar_y0, bar_y0], color="white", lw=4, solid_capstyle='butt')
    ax.plot([bar_x0, bar_x0 + bar_deg], [bar_y0, bar_y0], color="black", lw=1.5, solid_capstyle='butt')
    ax.text(
        bar_x0 + bar_deg / 2, bar_y0 + 0.015 * (extent[3] - extent[2]),
        "1 km", ha="center", fontsize=10, weight="bold", color="white",
        path_effects=[pe.withStroke(linewidth=2, foreground="black")]
    )

    ax.set_title("NISAR S-Band SAR (10 m Native Resolution)\nBogibeel Bridge across the Brahmaputra River",
                 fontsize=13, weight="bold", color="white", pad=12)
    ax.set_xlabel("Longitude (°E)", color="white", fontsize=10)
    ax.set_ylabel("Latitude (°N)", color="white", fontsize=10)
    ax.tick_params(colors="white")
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°'))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°'))
    for s in ax.spines.values():
        s.set_color("#555555")

    if save_path:
        fig.savefig(save_path, dpi=300, facecolor="black", bbox_inches="tight")
        print(f"  ✓ Saved: {save_path}")

    plt.close(fig)


# ═══════════════════════════════════════════════════════════════
# Main Execution
# ═══════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("🛰️  NISAR S-Band River Visualization Engine")
    print(f"File: {os.path.basename(FILE_PATH)}")
    print("=" * 70)

    cfg = get_pol_config_from_h5(FILE_PATH)
    info = read_scene_info(FILE_PATH)
    print(f"Mode: {cfg['mode_label']} | Native Res: {abs(info['x_spacing_m']):.0f} m")
    print(f"Scene Dimensions: {info['nrows']} x {info['ncols']} pixels")

    roi_idx = compute_roi_indices(FILE_PATH, ROI)
    if roi_idx is None:
        raise ValueError(f"ROI {ROI} does not overlap file {FILE_PATH}!")

    iy0, iy1, ix0, ix1 = roi_idx
    print(f"River ROI Rows [{iy0}:{iy1}], Cols [{ix0}:{ix1}]")

    # Output 1: Publication FCC
    fcc_path = os.path.join(SCRIPT_DIR, "NISAR_Brahmaputra_River_FCC_Publication.png")
    generate_scientific_fcc(FILE_PATH, roi_idx, cfg, REGION_TITLE, save_path=fcc_path)

    # Output 2: Polarimetric Multi-panel Analysis
    multi_path = os.path.join(SCRIPT_DIR, "NISAR_Brahmaputra_River_Polarimetric_Analysis.png")
    generate_polarimetric_multipanel(FILE_PATH, roi_idx, cfg, REGION_TITLE, save_path=multi_path, subsample=2)

    # Output 3: Bogibeel Bridge Zoom
    bridge_path = os.path.join(SCRIPT_DIR, "NISAR_Bogibeel_Bridge_Zoom_10m.png")
    generate_bogibeel_zoom(FILE_PATH, save_path=bridge_path)

    print("\n" + "=" * 70)
    print("All river visualizations successfully generated!")
    print(f"1. {fcc_path}")
    print(f"2. {multi_path}")
    print(f"3. {bridge_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
