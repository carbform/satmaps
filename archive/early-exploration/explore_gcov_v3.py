#!/usr/bin/env python
# coding: utf-8

# # 🛰️ NISAR S-Band GCOV Data Playground
# 
# **Author:** [Carbform](https://carbform.github.io) 
# 
# **Version:** `v3.0` — *Beta Budapest* 🚀 
# 
#  Credits : I get by with a little help from Codex and Opus
# 
# > **Version History**  
# > | Version | Codename | Notes |
# > |---------|----------|-------|
# > | `v0.1` | *Alpha Amsterdam* | Initial single-file explorer |
# > | `v0.5` | *Alpha Antwerp* | Added FCC & ROI subset |
# > | `v1.0` | *Beta Bengaluru* | Xarray + Dask Testing ; Modular multi-file pipeline, auto-pol detection, RGBA FCC fix |
# > | `v2.0` | *Beta Budapest* |  **Memory-safe rewrite** — no dask/xarray, direct h5py block I/O |
# > | `v3.0` | *Gamma Godavari* | Planned Additional Visualisations |
# > | — | *Delta Darwin* | *(planned)* Multi-frequency L+S fusion |
# 
# ---
# 
# ### Design Principles (v3)
# 
# NISAR GCOV products are **massive** — a single scene can be 33 000 × 34 000 pixels
# (~1.1 billion pixels, 24+ GB of float32 data per file). The HDF5 datasets are
# stored **without internal chunking**, so lazy-loading via dask/xarray doesn't
# actually help — those libraries end up materialising the full array.
# 
# This notebook uses a **zero-copy-whole-scene** philosophy:
# 
# | Task | Strategy | Peak RAM |
# |------|----------|----------|
# | Overview / full-scene plots | **Strided read** `[::stride, ::stride]` from HDF5 | ~50–100 MB |
# | ROI plots | **Direct ROI slice** at full resolution | Bounded by ROI size |
# | Statistics | **Block-wise row-band iteration** | ~one block (~200 MB) |
# | Percentile stretch | **Reservoir sampling** from random blocks | ~10 MB |
# 

# In[1]:


# ═══════════════════════════════════════════════════════════════
#  Imports — lightweight, no dask/xarray needed
# ═══════════════════════════════════════════════════════════════
import h5py
import numpy as np
import os
from collections import OrderedDict
from pyproj import Transformer
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import matplotlib.patheffects as pe
import ultraplot as uplt
from scipy.ndimage import median_filter, gaussian_filter
from datetime import datetime
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
# print("Imports ready — h5py + numpy + matplotlib + ultraplot.")


# In[2]:


# ═══════════════════════════════════════════════════════════════
#  GCOV files to load — edit this dictionary to change inputs
#  Keys are short labels; values are file paths.
# ═══════════════════════════════════════════════════════════════
GCOV_FILES = {
    "DHNA_Brahmaputra": os.path.join(DATA_DIR,
        "NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5"),
}

# Verify and show sizes
for name, fpath in GCOV_FILES.items():
    if os.path.exists(fpath):
        size_gb = os.path.getsize(fpath) / 1e9
        print(f"{name}: {size_gb:.2f} GB  ✓")
    else:
        print(f"{name}: file not found at {fpath}")


# ## Memory-Safe Core Library
# 
# All functions read from HDF5 **on-the-fly** using `h5py` slicing.
# No function ever loads the full scene into memory.

# In[3]:


# ═══════════════════════════════════════════════════════════════
#  Core : Polarisation auto-detection
# ═══════════════════════════════════════════════════════════════

def get_pol_config_from_h5(filepath):
    """
    Auto-detect polarisation mode from a GCOV HDF5 file.

    Returns
    -------
    dict with keys:
        pol_type, co_term, cross_term, offdiag_term,
        pol1, pol2, mode_label, polarisations, covariance_terms
    """
    with h5py.File(filepath, 'r') as f:
        grids = f['science/SSAR/GCOV/grids/frequencyA']
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


# ═══════════════════════════════════════════════════════════════
#  Core : Scene metadata reader
# ═══════════════════════════════════════════════════════════════

def read_scene_info(filepath):
    """Read identification + grid metadata without loading pixel data."""
    info = OrderedDict()
    with h5py.File(filepath, 'r') as f:
        ident = f['science/SSAR/identification']
        grids = f['science/SSAR/GCOV/grids/frequencyA']

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
        info['x_range'] = (float(grids['xCoordinates'][0]), float(grids['xCoordinates'][-1]))
        info['y_range'] = (float(grids['yCoordinates'][0]), float(grids['yCoordinates'][-1]))

        params = f['science/SSAR/GCOV/metadata/processingInformation/parameters']
        info['rtc_applied'] = params['radiometricTerrainCorrectionApplied'][()].decode()
        info['noise_corrected'] = params['noiseCorrectionApplied'][()].decode()
        info['rfi_mitigated'] = params['rfiMitigationApplied'][()].decode()

        # Estimate memory
        total_pixels = info['nrows'] * info['ncols']
        n_float = sum(1 for t in info['covariance_terms']
                      if t in {'HHHH','HVHV','VVVV','VHVH','RHRH','RVRV'})
        n_complex = len(info['covariance_terms']) - n_float
        mem_gb = (n_float * 4 + n_complex * 8 + 1 + 4) * total_pixels / 1e9
        info['estimated_mem_gb'] = mem_gb

    return info


# ═══════════════════════════════════════════════════════════════
#  Core : Coordinate helpers
# ═══════════════════════════════════════════════════════════════

def get_utm_coords(filepath):
    """Read 1-D UTM coordinate arrays and EPSG (no pixel data)."""
    with h5py.File(filepath, 'r') as f:
        grids = f['science/SSAR/GCOV/grids/frequencyA']
        x = grids['xCoordinates'][:]
        y = grids['yCoordinates'][:]
        epsg = int(grids['projection'][()])
    return x, y, epsg


def utm_to_latlon_1d(x_utm, y_utm, epsg):
    """Convert 1-D UTM arrays to approximate 1-D lat/lon (through scene centre)."""
    t = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    mid_x = len(x_utm) // 2
    mid_y = len(y_utm) // 2
    _, lat_1d = t.transform(np.full_like(y_utm, x_utm[mid_x]), y_utm)
    lon_1d, _ = t.transform(x_utm, np.full_like(x_utm, y_utm[mid_y]))
    return lon_1d, lat_1d


def utm_to_latlon_2d(x_utm, y_utm, epsg):
    """Convert 1-D UTM arrays to full 2-D lat/lon grids."""
    t = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    xx, yy = np.meshgrid(x_utm, y_utm)
    lon_2d, lat_2d = t.transform(xx, yy)
    return lon_2d.astype(np.float32), lat_2d.astype(np.float32)


print("Core library loaded.")


# In[4]:


# ═══════════════════════════════════════════════════════════════
#  Core : Memory-safe I/O helpers
# ═══════════════════════════════════════════════════════════════

def read_strided(filepath, dataset_path, stride):
    """
    Read a 2-D HDF5 dataset with spatial stride.

    For a 33000×34000 scene with stride=10, this reads ~3300×3400 pixels
    (~45 MB for float32) instead of the full 4.5 GB.

    Parameters
    ----------
    filepath : str
    dataset_path : str   e.g. 'science/SSAR/GCOV/grids/frequencyA/HHHH'
    stride : int          spatial downsample factor

    Returns
    -------
    np.ndarray (float32) of shape (nrows//stride, ncols//stride)
    """
    with h5py.File(filepath, 'r') as f:
        ds = f[dataset_path]
        arr = ds[::stride, ::stride]
    if np.iscomplexobj(arr):
        return arr  # keep complex
    return arr.astype(np.float32)


def read_roi(filepath, dataset_path, iy0, iy1, ix0, ix1, subsample=1):
    """
    Read a spatial ROI from an HDF5 dataset.

    Parameters
    ----------
    iy0, iy1, ix0, ix1 : int
        Row/col index bounds (exclusive end).
    subsample : int
        Additional subsample within the ROI.

    Returns
    -------
    np.ndarray
    """
    with h5py.File(filepath, 'r') as f:
        arr = f[dataset_path][iy0:iy1:subsample, ix0:ix1:subsample]
    if np.iscomplexobj(arr):
        return arr
    return arr.astype(np.float32)


def compute_roi_indices(filepath, roi):
    """
    Convert a lat/lon ROI bounding box to pixel row/col indices.

    Parameters
    ----------
    filepath : str
    roi : dict with lat_min, lat_max, lon_min, lon_max

    Returns
    -------
    (iy0, iy1, ix0, ix1) or None if no overlap
    """
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


print("Memory-safe I/O helpers loaded.")


# In[5]:


# ═══════════════════════════════════════════════════════════════
#  Core : Block-wise statistics (never loads full scene)
# ═══════════════════════════════════════════════════════════════

def blockwise_stats(filepath, dataset_path, mask_path=None,
                    block_rows=2048):
    """
    Compute statistics by iterating over row-bands.

    Welford's online algorithm for mean/variance — numerically stable,
    single-pass, constant memory.

    Parameters
    ----------
    filepath : str
    dataset_path : str   HDF5 path to 2-D dataset
    mask_path : str      optional path to mask dataset (1=valid)
    block_rows : int     rows per block (~80 MB per block for float32 × 34k cols)

    Returns
    -------
    dict with min, max, mean, std, valid_count, nan_count, total_count
    """
    with h5py.File(filepath, 'r') as f:
        ds = f[dataset_path]
        nrows, ncols = ds.shape

        if mask_path is not None:
            mask_ds = f[mask_path]
        else:
            mask_ds = None

        count = 0
        running_mean = 0.0
        running_m2 = 0.0
        global_min = np.inf
        global_max = -np.inf
        nan_count = 0
        total_count = 0

        for r0 in range(0, nrows, block_rows):
            r1 = min(r0 + block_rows, nrows)
            block = ds[r0:r1, :].astype(np.float64)
            total_count += block.size

            if mask_ds is not None:
                mask_block = mask_ds[r0:r1, :]
                block = np.where(mask_block == 1, block, np.nan)

            finite = block[np.isfinite(block)]
            nan_count += block.size - finite.size

            if finite.size == 0:
                continue

            block_min = finite.min()
            block_max = finite.max()
            global_min = min(global_min, block_min)
            global_max = max(global_max, block_max)

            # Welford update (batch)
            for val in [finite]:  # vectorised batch update
                n = val.size
                new_count = count + n
                delta = val.mean() - running_mean
                running_mean += delta * n / new_count
                running_m2 += val.var() * n + delta**2 * count * n / new_count
                count = new_count

    if count == 0:
        return dict(min=np.nan, max=np.nan, mean=np.nan, std=np.nan,
                    valid_count=0, nan_count=nan_count, total_count=total_count)

    variance = running_m2 / count
    return dict(
        min=float(global_min), max=float(global_max),
        mean=float(running_mean), std=float(np.sqrt(variance)),
        valid_count=int(count), nan_count=int(nan_count),
        total_count=int(total_count),
    )


def reservoir_percentile(filepath, dataset_path, percentiles,
                         mask_path=None, reservoir_size=500_000,
                         block_rows=2048, seed=42):
    """
    Approximate percentiles via reservoir sampling — O(reservoir_size) memory.

    Reads the dataset in row-band blocks, randomly sampling into a fixed
    reservoir. Accuracy is excellent for reservoir_size ≥ 500k.

    Parameters
    ----------
    percentiles : list of float   e.g. [2, 98]
    reservoir_size : int          samples to keep
    """
    rng = np.random.RandomState(seed)

    with h5py.File(filepath, 'r') as f:
        ds = f[dataset_path]
        nrows, ncols = ds.shape
        mask_ds = f[mask_path] if mask_path else None

        reservoir = np.empty(reservoir_size, dtype=np.float32)
        filled = 0
        seen = 0

        for r0 in range(0, nrows, block_rows):
            r1 = min(r0 + block_rows, nrows)
            block = ds[r0:r1, :].astype(np.float32).ravel()

            if mask_ds is not None:
                mask_block = mask_ds[r0:r1, :].ravel()
                block = block[mask_block == 1]

            block = block[np.isfinite(block)]
            if block.size == 0:
                continue

            for val in block:
                if filled < reservoir_size:
                    reservoir[filled] = val
                    filled += 1
                else:
                    j = rng.randint(0, seen + 1)
                    if j < reservoir_size:
                        reservoir[j] = val
                seen += 1

    if filled == 0:
        return np.array([np.nan] * len(percentiles))

    reservoir = reservoir[:filled]
    return np.percentile(reservoir, percentiles)


def fast_reservoir_percentile(filepath, dataset_path, percentiles,
                              mask_path=None, n_samples=500_000,
                              block_rows=4096, seed=42):
    """
    Fast approximate percentiles using stratified random row sampling.

    Instead of scanning every pixel, this selects random row indices,
    reads only those rows, and samples from valid pixels. Much faster
    than full reservoir scan for very large scenes.

    Parameters
    ----------
    percentiles : list of float
    n_samples : int   target number of samples to collect
    """
    rng = np.random.RandomState(seed)

    with h5py.File(filepath, 'r') as f:
        ds = f[dataset_path]
        nrows, ncols = ds.shape
        mask_ds = f[mask_path] if mask_path else None

        # Sample ~sqrt(n_samples) random rows, then ~sqrt(n_samples) pixels per row
        n_row_samples = min(nrows, max(200, int(np.sqrt(n_samples))))
        row_indices = np.sort(rng.choice(nrows, size=n_row_samples, replace=False))

        samples = []
        for r in row_indices:
            row = ds[r, :].astype(np.float32)
            if mask_ds is not None:
                m = mask_ds[r, :]
                row = row[m == 1]
            row = row[np.isfinite(row)]
            if row.size == 0:
                continue

            # Take a subset of pixels from this row
            n_take = min(row.size, max(100, n_samples // n_row_samples))
            if row.size > n_take:
                idx = rng.choice(row.size, size=n_take, replace=False)
                samples.append(row[idx])
            else:
                samples.append(row)

        if not samples:
            return np.array([np.nan] * len(percentiles))

        all_samples = np.concatenate(samples)
        return np.percentile(all_samples, percentiles)


print("Block-wise statistics and reservoir percentile loaded.")


# ## 1. Inspect HDF5 Structure
# 
# NISAR GCOV products follow the hierarchy:  
# `science/SSAR/GCOV/grids/frequencyA/` — covariance data, coordinates, mask  
# `science/SSAR/identification/` — orbit, track, frame, time metadata  
# `science/SSAR/GCOV/metadata/` — calibration, processing info, radar grid geometry

# In[6]:


def explore_h5(filepath, max_depth=4):
    """Print the HDF5 group/dataset tree up to max_depth."""
    def _walk(group, prefix="", depth=0):
        if depth >= max_depth:
            return
        for key in sorted(group.keys()):
            item = group[key]
            if isinstance(item, h5py.Group):
                print(f"{prefix}📁 {key}/")
                _walk(item, prefix + "   ", depth + 1)
            elif isinstance(item, h5py.Dataset):
                shape_str = f"shape={item.shape}" if item.shape else "scalar"
                size_mb = item.dtype.itemsize * np.prod(item.shape) / 1e6 if item.shape else 0
                chunk_str = f"chunks={item.chunks}" if item.chunks else "unchunked"
                print(f"{prefix}📊 {key}  [{item.dtype}]  {shape_str}  ({size_mb:.1f} MB, {chunk_str})")

    with h5py.File(filepath, 'r') as f:
        fname = os.path.basename(filepath)
        print(f"\n{'='*70}")
        print(f"FILE: {fname}")
        print(f"{'='*70}")
        _walk(f)

for name, fpath in GCOV_FILES.items():
    explore_h5(fpath, max_depth=4)


# ## 2. Extract Identification Metadata
# 
# Pull key metadata fields from each GCOV file to understand acquisition parameters.

# In[7]:


for name, fpath in GCOV_FILES.items():
    info = read_scene_info(fpath)
    cfg = get_pol_config_from_h5(fpath)
    print(f"\n{'='*60}")
    print(f"  {name}  [{cfg['mode_label']}]")
    print(f"{'='*60}")
    for k, v in info.items():
        print(f"  {k:40s}: {v}")
    print(f"\n  ⚠ Full-scene memory footprint: {info['estimated_mem_gb']:.1f} GB")
    print(f"    → This notebook NEVER loads the full scene.")


# ## 3. Data Quality & Statistics (block-wise — constant memory)
# 
# Computes min/max/mean/std by iterating in row-bands (~80 MB each).
# The full 24 GB scene is **never** loaded into memory.

# In[8]:


GRIDS_PREFIX = 'science/SSAR/GCOV/grids/frequencyA'

for label, fpath in GCOV_FILES.items():
    cfg = get_pol_config_from_h5(fpath)
    info = read_scene_info(fpath)
    print(f"\n{'='*60}")
    print(f"  Statistics: {label} ({cfg['mode_label']})")
    print(f"  Grid: {info['grid_shape']} = {info['nrows']*info['ncols']:,} pixels")
    print(f"{'='*60}")

    mask_path = f'{GRIDS_PREFIX}/mask'

    # Mask coverage (block-wise)
    with h5py.File(fpath, 'r') as f:
        mask_ds = f[mask_path]
        nrows = mask_ds.shape[0]
        valid_count = 0
        outside_count = 0
        total = 0
        for r0 in range(0, nrows, 4096):
            r1 = min(r0 + 4096, nrows)
            block = mask_ds[r0:r1, :]
            valid_count += np.sum(block == 1)
            outside_count += np.sum(block == 255)
            total += block.size

    print(f"\n  Mask coverage:")
    print(f"    Valid (=1):          {valid_count/total*100:.1f}%")
    print(f"    Outside acq (=255): {outside_count/total*100:.1f}%")
    print(f"    Other:              {(total-valid_count-outside_count)/total*100:.1f}%")

    # Per-term statistics
    diag_terms = [t for t in cfg['covariance_terms']
                  if t in {'HHHH','HVHV','VVVV','VHVH','RHRH','RVRV'}]

    print(f"\n  {'Variable':<12s} {'Min':>12s} {'Max':>12s} {'Mean':>12s} {'Std':>12s}")
    print(f"  {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")

    for term in diag_terms:
        ds_path = f'{GRIDS_PREFIX}/{term}'
        s = blockwise_stats(fpath, ds_path, mask_path=mask_path, block_rows=4096)
        print(f"  {term:<12s} {s['min']:>12.6f} {s['max']:>12.6f} "
              f"{s['mean']:>12.6f} {s['std']:>12.6f}")

    # Number of looks stats
    s = blockwise_stats(fpath, f'{GRIDS_PREFIX}/numberOfLooks',
                        mask_path=mask_path, block_rows=4096)
    print(f"\n  Number of Looks: min={s['min']:.1f}, max={s['max']:.1f}, "
          f"mean={s['mean']:.1f}")


# ## 4. Overview Plots (downsampled ~ 10x)
# 
# Uses strided reads from HDF5: `dataset[::stride, ::stride]`.
# For stride=10, a 33k×34k scene becomes 3.3k×3.4k — about **45 MB** per layer.

# In[9]:


# ═══════════════════════════════════════════════════════════════
#  Overview stride — controls memory for full-scene plots
#  stride=10  → ~100 m effective resolution, ~45 MB per layer
#  stride=20  → ~200 m, ~12 MB per layer
# ═══════════════════════════════════════════════════════════════
OVERVIEW_STRIDE = 10

for label, fpath in GCOV_FILES.items():
    cfg = get_pol_config_from_h5(fpath)
    info = read_scene_info(fpath)
    reduced_shape = (info['nrows'] // OVERVIEW_STRIDE, info['ncols'] // OVERVIEW_STRIDE)
    mem_per_layer = reduced_shape[0] * reduced_shape[1] * 4 / 1e6
    print(f"{label}: {info['grid_shape']} → {reduced_shape} (stride={OVERVIEW_STRIDE})")
    print(f"  ~{mem_per_layer:.0f} MB per float32 layer")


# ### 4a. Mask & Number of Looks (overview)

# In[10]:


n_files = len(GCOV_FILES)
fig, axes = plt.subplots(2, max(n_files, 1), figsize=(7*n_files, 12), squeeze=False)

for col, (label, fpath) in enumerate(GCOV_FILES.items()):
    cfg = get_pol_config_from_h5(fpath)
    name = f"{label} ({cfg['mode_label']})"

    # Read strided data
    x_utm, y_utm, epsg = get_utm_coords(fpath)
    x_s = x_utm[::OVERVIEW_STRIDE]
    y_s = y_utm[::OVERVIEW_STRIDE]
    lon_1d, lat_1d = utm_to_latlon_1d(x_s, y_s, epsg)

    mask = read_strided(fpath, f'{GRIDS_PREFIX}/mask', OVERVIEW_STRIDE)
    nlooks = read_strided(fpath, f'{GRIDS_PREFIX}/numberOfLooks', OVERVIEW_STRIDE)

    # Mask plot
    ax = axes[0, col]
    mask_display = mask.astype(float)
    mask_display[mask_display == 255] = np.nan
    im = ax.pcolormesh(lon_1d, lat_1d, mask_display,
                       cmap='RdYlGn', shading='auto', rasterized=True)
    ax.set_title(f"{name} — Validity Mask")
    ax.set_xlabel('Longitude (°E)')
    ax.set_ylabel('Latitude (°N)')
    ax.set_aspect('equal')
    plt.colorbar(im, ax=ax, label='Subswath #')

    # Number of looks plot
    ax = axes[1, col]
    nlooks_display = nlooks.copy()
    nlooks_display[mask == 255] = np.nan
    im = ax.pcolormesh(lon_1d, lat_1d, nlooks_display,
                       cmap='viridis', shading='auto', rasterized=True)
    ax.set_title(f"{name} — Number of Looks")
    ax.set_xlabel('Longitude (°E)')
    ax.set_ylabel('Latitude (°N)')
    ax.set_aspect('equal')
    plt.colorbar(im, ax=ax, label='N looks')

    del mask, nlooks, mask_display, nlooks_display  # free memory

plt.tight_layout()
plt.show()


# ### 4b. Quick-Look Backscatter Overview (downsampled, dB)
# 
# Grayscale backscatter images at overview resolution.
# Percentile stretch from reservoir sampling — fast and memory-safe.

# In[11]:


def linear_to_db(arr):
    """Convert linear power to dB, masking non-positive values."""
    with np.errstate(divide='ignore', invalid='ignore'):
        db = 10.0 * np.log10(arr)
    db[~np.isfinite(db)] = np.nan
    return db.astype(np.float32)


for label, fpath in GCOV_FILES.items():
    cfg = get_pol_config_from_h5(fpath)
    x_utm, y_utm, epsg = get_utm_coords(fpath)
    x_s = x_utm[::OVERVIEW_STRIDE]
    y_s = y_utm[::OVERVIEW_STRIDE]
    lon_1d, lat_1d = utm_to_latlon_1d(x_s, y_s, epsg)

    diag_terms = [cfg['co_term'], cfg['cross_term']]
    n = len(diag_terms)
    fig, axes = plt.subplots(1, n, figsize=(7*n, 8), squeeze=False)
    axes = axes.flatten()

    for i, term in enumerate(diag_terms):
        ax = axes[i]
        arr = read_strided(fpath, f'{GRIDS_PREFIX}/{term}', OVERVIEW_STRIDE)
        db = linear_to_db(arr)

        # Percentile limits from reservoir sampling on the FULL scene
        q = fast_reservoir_percentile(fpath, f'{GRIDS_PREFIX}/{term}',
                                      [2, 98], mask_path=f'{GRIDS_PREFIX}/mask')
        vmin, vmax = 10*np.log10(max(q[0], 1e-12)), 10*np.log10(max(q[1], 1e-12))

        im = ax.pcolormesh(lon_1d, lat_1d, db,
                           vmin=vmin, vmax=vmax, cmap='gray',
                           shading='auto', rasterized=True)
        ax.set_title(f"{label} {cfg['pol1'] if i==0 else cfg['pol2']} (dB)")
        ax.set_xlabel('Longitude (°E)')
        ax.set_ylabel('Latitude (°N)')
        ax.set_aspect('equal')
        plt.colorbar(im, ax=ax, label='γ⁰ (dB)', shrink=0.7)

        del arr, db  # free immediately

    plt.suptitle(f"{label} — {cfg['mode_label']} Overview (stride={OVERVIEW_STRIDE})",
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.show()


# ## 5. Summary of Loaded Files

# In[12]:


print("\n" + "="*70)
print("SUMMARY: GCOV Files")
print("="*70)

for label, fpath in GCOV_FILES.items():
    cfg = get_pol_config_from_h5(fpath)
    info = read_scene_info(fpath)
    print(f"\n📦 {label}  [{cfg['pol_type']}]")
    print(f"   Mode: {cfg['mode_label']}")
    print(f"   Orbit: {info['orbitPassDirection']}, Track {info['trackNumber']}, Frame {info['frameNumber']}")
    print(f"   Time: {info['zeroDopplerStartTime']}")
    print(f"   Native res: {abs(info['x_spacing_m']):.0f} m")
    print(f"   Grid: {info['grid_shape']} = {info['nrows']*info['ncols']:,} pixels")
    print(f"   Full-scene memory: {info['estimated_mem_gb']:.1f} GB (NEVER loaded)")
    print(f"   Overview stride: {OVERVIEW_STRIDE}x → ~{info['nrows']//OVERVIEW_STRIDE}×{info['ncols']//OVERVIEW_STRIDE}")

print("\n" + "="*70)
print("Design notes:")
print("  • Overview plots use strided HDF5 reads — ~45 MB per layer")
print("  • Statistics use block-wise row iteration — ~80 MB peak per variable")
print("  • ROI plots (below) load only the ROI subset at full resolution")
print("="*70)


# ---
# 
# ## 6. ROI Subset — Full Resolution
# 
# Define a region of interest (ROI) and load **only that subset at full resolution**.
# Edit `ROI` and `region_title` below to change the target area.
# 
# Memory is bounded by the ROI size. For example:
# - 1° × 1° at 10 m = ~11k × 11k pixels ≈ **0.5 GB per layer** (manageable)
# - 0.5° × 0.5° = ~5.5k × 5.5k ≈ **120 MB per layer** (very comfortable)

# In[36]:


# ═══════════════════════════════════════════════════════════════
#  ROI configuration — Brahmaputra River (Dibrugarh & Bogibeel)
# ═══════════════════════════════════════════════════════════════
ROI = {"lat_min": 27.38, "lat_max": 27.72, "lon_min": 94.70, "lon_max": 95.18}
region_title = "Brahmaputra River (Dibrugarh)"

print(f"ROI: {region_title}")
print(f"  Lat: {ROI['lat_min']}° to {ROI['lat_max']}°")
print(f"  Lon: {ROI['lon_min']}° to {ROI['lon_max']}°")

# Pre-compute ROI indices for each file
roi_indices = {}
for label, fpath in GCOV_FILES.items():
    idx = compute_roi_indices(fpath, ROI)
    if idx is None:
        print(f"  ⚠ {label}: ROI does not overlap this scene — skipping")
        continue
    iy0, iy1, ix0, ix1 = idx
    n_rows = iy1 - iy0
    n_cols = ix1 - ix0
    mem_per_layer = n_rows * n_cols * 4 / 1e6
    print(f"  {label}: rows [{iy0}:{iy1}] ({n_rows}), cols [{ix0}:{ix1}] ({n_cols})")
    print(f"    → {n_rows}×{n_cols} = {n_rows*n_cols:,} pixels, ~{mem_per_layer:.0f} MB/layer")
    roi_indices[label] = idx


# ### 6a. Individual Channel Plots — Downsampled ROI
# 
# Grayscale backscatter images for each polarisation channel at **downsampled resolution**.
# Uses `ROI_STRIDE` to reduce memory — e.g. stride=4 → ~40 m effective resolution.
# Only the ROI pixels are loaded from disk, then subsampled.

# In[37]:


# ═══════════════════════════════════════════════════════════════
#  ROI_STRIDE — controls downsampling for individual channel plots
#  stride=1  → full 10 m resolution (large memory)
#  stride=4  → ~40 m effective resolution (~16× less memory)
#  stride=8  → ~80 m effective resolution (~64× less memory)
# ═══════════════════════════════════════════════════════════════
ROI_STRIDE = 4


def plot_individual_channels_roi(filepath, roi_idx, cfg, label="",
                                 region_title="", plow=2, phigh=98,
                                 subsample=ROI_STRIDE):
    """
    Plot co-pol, cross-pol, and ratio channels at downsampled ROI resolution.

    Parameters
    ----------
    filepath : str
    roi_idx : tuple (iy0, iy1, ix0, ix1)
    cfg : dict from get_pol_config_from_h5
    subsample : int
        Spatial downsample factor within the ROI (default: ROI_STRIDE).
    """
    iy0, iy1, ix0, ix1 = roi_idx
    eff_res = abs(10 * subsample)  # approximate effective resolution (m)

    # Read subsampled ROI — much less memory
    co = read_roi(filepath, f'{GRIDS_PREFIX}/{cfg["co_term"]}',
                  iy0, iy1, ix0, ix1, subsample=subsample)
    cross = read_roi(filepath, f'{GRIDS_PREFIX}/{cfg["cross_term"]}',
                     iy0, iy1, ix0, ix1, subsample=subsample)
    mask = read_roi(filepath, f'{GRIDS_PREFIX}/mask',
                    iy0, iy1, ix0, ix1, subsample=subsample)

    co_db = linear_to_db(co)
    cross_db = linear_to_db(cross)
    ratio_db = co_db - cross_db
    del co, cross  # free linear arrays

    # Coordinates (subsampled)
    x_utm, y_utm, epsg = get_utm_coords(filepath)
    x_roi = x_utm[ix0:ix1:subsample]
    y_roi = y_utm[iy0:iy1:subsample]
    lon_1d, lat_1d = utm_to_latlon_1d(x_roi, y_roi, epsg)

    # Percentile limits (from loaded arrays — they're already in memory)
    valid = mask == 1
    panels = [
        (co_db, f"{cfg['pol1']} (dB)"),
        (cross_db, f"{cfg['pol2']} (dB)"),
        (ratio_db, f"{cfg['pol1']}/{cfg['pol2']} ratio (dB)"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(21, 8))
    for ax, (data, title_suffix) in zip(axes, panels):
        finite = data[valid & np.isfinite(data)]
        if finite.size > 0:
            vmin, vmax = np.percentile(finite, [plow, phigh])
        else:
            vmin, vmax = -25, 5

        im = ax.pcolormesh(lon_1d, lat_1d, data,
                           vmin=vmin, vmax=vmax, cmap='gray',
                           shading='auto', rasterized=True)
        ax.set_title(f"{label} — {title_suffix}", fontsize=12)
        ax.set_xlabel('Longitude (°E)')
        ax.set_ylabel('Latitude (°N)')
        ax.set_aspect('equal')
        plt.colorbar(im, ax=ax, label='γ⁰ (dB)', shrink=0.6)

    mem_mb = co_db.nbytes * 3 / 1e6  # approximate 3 layers
    plt.suptitle(f"{region_title} — ~{eff_res:.0f} m Resolution (stride={subsample})",
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.show()

    del co_db, cross_db, ratio_db, mask


# ── Plot for each file that overlaps the ROI ──
for label, fpath in GCOV_FILES.items():
    if label not in roi_indices:
        continue
    cfg = get_pol_config_from_h5(fpath)
    iy0, iy1, ix0, ix1 = roi_indices[label]
    n_rows_ds = (iy1 - iy0) // ROI_STRIDE
    n_cols_ds = (ix1 - ix0) // ROI_STRIDE
    mem_est = n_rows_ds * n_cols_ds * 4 * 3 / 1e6
    print(f"Plotting {label} — {cfg['mode_label']} — {region_title}")
    print(f"  Downsampled: {n_rows_ds}×{n_cols_ds}, ~{mem_est:.0f} MB for 3 layers")
    plot_individual_channels_roi(fpath, roi_indices[label], cfg,
                                 label=cfg['mode_label'],
                                 region_title=region_title)


# ### 6b. False Color Composite — Full Resolution ROI (Memory-Safe)
# 
# Publication-quality FCC at **full 10 m resolution** using block-wise I/O:
# - **Pass 1**: Reservoir-sample the ROI to compute percentile stretch limits (~10 MB)
# - **Pass 2**: Build RGBA uint8 image in row-bands (~80 MB per band, never 3× float32)
# - Peak RAM = RGBA output (4 bytes/pixel) + one row-band block
# 
# | Component | Encoding |
# |-----------|----------|
# | **R** | co-pol backscatter (γ⁰ dB) |
# | **G** | cross-pol backscatter (γ⁰ dB) |
# | **B** | co/cross ratio (dB) |
# | **Alpha** | 0 for invalid/missing pixels (transparent) |
# 
# Two versions are generated:
# 1. **Scientific FCC** — Publication-quality with lat/lon axes, info panel, scale bar (ultraplot)
# 2. **Dissemination FCC** — Visually polished with contrast enhancement, light filtering, and clean aesthetic for reports/social media

# In[38]:


def _roi_reservoir_percentiles(filepath, roi_idx, cfg, plow=2, phigh=98,
                               n_sample_rows=500, n_per_row=200, seed=42):
    """
    Reservoir-sample the ROI to get percentile stretch limits for co, cross, ratio (dB).

    Returns
    -------
    dict with keys 'co', 'cross', 'ratio', each a (vmin, vmax) tuple in dB.
    Peak memory: ~10 MB (sample arrays only).
    """
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

    return {'co': _pct(co_samples), 'cross': _pct(cross_samples),
            'ratio': _pct(ratio_samples)}


def _build_rgba(filepath, roi_idx, cfg, limits, block_rows=1024):
    """
    Build RGBA uint8 array from HDF5 in memory-safe row-bands.
    Shared between scientific and dissemination plot functions.

    Returns
    -------
    rgba : np.ndarray (uint8, shape nrows×ncols×4)
    """
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


# In[39]:


# ═══════════════════════════════════════════════════════════════
#  UltraPlot premium styling (clean + professional)
# ═══════════════════════════════════════════════════════════════
uplt.rc.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "axes.edgecolor": "#2b2b2b",
})


# In[40]:


# ═══════════════════════════════════════════════════════════════
#  Scientific FCC — Matplotlib Compact Publication Layout (NEW)
# ═══════════════════════════════════════════════════════════════
def make_publication_fcc(filepath, roi_idx, cfg, region_title="",
                         plow=2, phigh=98, save_path=None,
                         block_rows=1024):

    iy0, iy1, ix0, ix1 = roi_idx
    nrows = iy1 - iy0
    ncols = ix1 - ix0

    print(f"  ROI: {nrows}x{ncols} = {nrows*ncols:,} pixels")

    # ── Percentiles & RGBA ──
    limits = _roi_reservoir_percentiles(filepath, roi_idx, cfg, plow, phigh)
    rgba = _build_rgba(filepath, roi_idx, cfg, limits, block_rows)

    # ── Coordinates ──
    x_utm, y_utm, epsg = get_utm_coords(filepath)
    x_roi = x_utm[ix0:ix1]
    y_roi = y_utm[iy0:iy1]
    lon_1d, lat_1d = utm_to_latlon_1d(x_roi, y_roi, epsg)

    extent = [
        float(lon_1d.min()), float(lon_1d.max()),
        float(lat_1d.min()), float(lat_1d.max())
    ]

    # ── Metadata ──
    info = read_scene_info(filepath)
    pol1, pol2 = cfg["pol1"], cfg["pol2"]
    orbit_dir = info["orbitPassDirection"]
    radar_band = info["radarBand"]
    spacing = abs(info["x_spacing_m"])
    mode_label = cfg["mode_label"]

    acq_time_str = info["zeroDopplerStartTime"]
    try:
        dt = datetime.fromisoformat(acq_time_str.replace("Z","+00:00"))
        date_label = dt.strftime("%d %B %Y, %H:%M UTC")
    except Exception:
        date_label = acq_time_str[:19] if acq_time_str else "N/A"

    title_text = (
        f"NISAR {radar_band}-Band SAR - False Color Composite\n"
        f"{mode_label} | {orbit_dir.capitalize()} Pass | {spacing:.0f} m Resolution\n"
        f"{region_title}"
    )

    # ════════════════════════════════════════════════════════════
    #  COMPACT MAP-DOMINANT GRID
    # ════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(14,9))

    gs = fig.add_gridspec(
        nrows=2,
        ncols=2,
        height_ratios=[12,1],   # map dominates height
        width_ratios=[4.6,1.6], # narrow info column
    )

    ax = fig.add_subplot(gs[0,0])
    ax_info = fig.add_subplot(gs[0,1])
    ax_credit = fig.add_subplot(gs[1,:])

    # ───────────────── MAP ─────────────────
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

    ax.set_title(title_text, fontsize=13, fontweight="bold", pad=10)

    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")

    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°'))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°'))

    ax.grid(True, color="white", alpha=0.28, linestyle="--", linewidth=0.4)

    # ── Scale bar ──
    lat_center = (extent[2] + extent[3]) / 2
    km_per_deg_lon = 111.32 * np.cos(np.radians(lat_center))
    total_km_x = (extent[1] - extent[0]) * km_per_deg_lon
    bar_km = 5 if total_km_x > 25 else 1
    bar_deg = bar_km / km_per_deg_lon

    bar_x0 = extent[0] + 0.05*(extent[1]-extent[0])
    bar_y0 = extent[2] + 0.04*(extent[3]-extent[2])

    ax.plot([bar_x0, bar_x0+bar_deg],[bar_y0,bar_y0],color="white",lw=3)
    ax.plot([bar_x0, bar_x0+bar_deg],[bar_y0,bar_y0],color="black",lw=1.4)

    ax.text(
        bar_x0+bar_deg/2,
        bar_y0+0.012*(extent[3]-extent[2]),
        f"{bar_km} km",
        ha="center",
        fontsize=9,
        weight="bold",
        color="white",
        path_effects=[pe.withStroke(linewidth=2,foreground="black")]
    )

    # ───────────────── RIGHT INFO PANEL ─────────────────
    ax_info.axis("off")

    y = 0.98

    # RGB ASSIGNMENT
    ax_info.text(0.02, y, "RGB CHANNEL ASSIGNMENT",
                fontsize=11, weight="bold")
    y -= 0.06

    rgb_items = [
        ("red",   f"R : {pol1} backscatter (γ⁰, dB)"),
        ("green", f"G : {pol2} backscatter (γ⁰, dB)"),
        ("blue",  f"B : {pol1}/{pol2} ratio (dB)")
    ]

    for c, txt in rgb_items:
        rect = mpatches.FancyBboxPatch(
            (0.02, y-0.02),      # ⭐ shifted right from 0.0 → 0.02
            0.08, 0.035,
            boxstyle="round,pad=0.003",
            facecolor=c,
            edgecolor="black",
            linewidth=0.6,
            transform=ax_info.transAxes,
            clip_on=False        # ⭐ prevents clipping at axis edge
        )
        ax_info.add_patch(rect)

        ax_info.text(0.14, y, txt,
                    fontsize=10,
                    family="monospace")

        y -= 0.055

    # INTERPRETATION
    ax_info.text(0,y,"INTERPRETATION GUIDE",
                 fontsize=11,weight="bold")
    y -= 0.06

    interp_items=[
        ("Red / Magenta","Urban, bare soil"),
        ("Green","Vegetation, crops"),
        ("Dark / Black","Water, low return"),
        ("Cyan / Teal","Mixed scattering"),
        ("Yellow","Double-bounce targets"),
    ]

    for n,d in interp_items:
        ax_info.text(0.0,y,n,fontsize=10,weight="bold")
        ax_info.text(0.34,y,d,fontsize=10)
        y -= 0.05

    y -= 0.02

    # ACQUISITION DETAILS
    ax_info.text(0,y,"ACQUISITION DETAILS",
                 fontsize=11,weight="bold")
    y -= 0.06

    details=[
        ("Sensor",f"NISAR {radar_band}-Band SAR"),
        ("Mode",mode_label),
        ("Pass",orbit_dir.capitalize()),
        ("Date",date_label),
        ("Resolution",f"{spacing:.0f} m"),
        ("Stretch",f"{plow}–{phigh} percentile"),
    ]

    for k,v in details:
        ax_info.text(0,y,f"{k:10s}: {v}",
                     fontsize=10,family="monospace")
        y -= 0.055

    # ───────────────── CREDIT BAR ─────────────────
    ax_credit.axis("off")
    ax_credit.text(
        0.5,0.5,
        "Data: NASA–ISRO NISAR Mission  |  Product: L2 GCOV  |  Visualisation: Sarat (NRSC/ISRO)",
        ha="center",va="center",
        fontsize=10,color="dimgray"
    )

    fig.subplots_adjust(
        left=0.075,right=0.98,
        top=0.92,bottom=0.015,
        wspace=0.03,hspace=0.05
    )

    if save_path:
        fig.savefig(save_path,dpi=300,facecolor="white",bbox_inches="tight")
        print(f"  Saved: {save_path}")

    plt.show()
    del rgba


# In[ ]:


# ═══════════════════════════════════════════════════════════════
#   Generate Scientific FCC for each file overlapping the ROI
# ═══════════════════════════════════════════════════════════════
for label, fpath in GCOV_FILES.items():
    if label not in roi_indices:
        continue
    cfg = get_pol_config_from_h5(fpath)
    safe_label = label.replace(' ', '_')

    # --- Scientific version ---
    print("=" * 60)
    print(f"  Scientific FCC: {cfg['mode_label']} -- {region_title}")
    print("=" * 60)
    make_publication_fcc(
        fpath, roi_indices[label], cfg,
        region_title=region_title,
        save_path=os.path.join(DATA_DIR,
            f"FCC_{cfg['pol1']}_{cfg['pol2']}_{safe_label}.png"),
    )


# ---
# 
# ## you can play around with these based on available  RAM
# 
# | Operation | What's loaded | Peak RAM estimate |
# |-----------|---------------|-------------------|
# | `read_scene_info()` | 1-D coords + scalars | < 1 MB |
# | `blockwise_stats()` | One row-band at a time | ~80 MB |
# | `fast_reservoir_percentile()` | Random rows + reservoir | ~10 MB |
# | Overview plots (stride=10) | Strided 2-D arrays | ~50 MB / layer |
# | ROI individual channels (stride=4) | 3 subsampled layers + mask | ~30–120 MB (ROI-dependent) |
# | ROI FCC (full res, block-wise) | uint8 RGBA output + one row-band | RGBA (4 B/px) + ~80 MB block |
# 
# Full 33k × 34k scene (24+ GB).
# 
# For ROI memory tuning:
# - Individual channels: adjust `ROI_STRIDE` (default 4)
# - FCC: adjust `block_rows` parameter (default 1024)
# - Both: reduce the ROI bounding box
