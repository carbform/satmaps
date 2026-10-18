import h5py
import numpy as np
import matplotlib.pyplot as plt

def normalize(band, pmin=2, pmax=98):
    # Ignore NaN or zero values
    valid_mask = np.isfinite(band) & (band != 0)
    b_min, b_max = np.percentile(band[valid_mask], (pmin, pmax))
    band_norm = np.clip((band - b_min) / (b_max - b_min), 0, 1)
    band_norm[~valid_mask] = 0
    return band_norm

# Open the HDF5 file
file_path = "NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5"
print(f"Reading {file_path}...")

with h5py.File(file_path, 'r') as f:
    grid_path = 'science/SSAR/GCOV/grids/frequencyA'
    
    # Check what datasets are available
    print("Available datasets:", list(f[grid_path].keys()))
    
    # HHHH and HVHV are usually real numbers representing power (intensity)
    hh = f[f'{grid_path}/HHHH'][:]
    hv = f[f'{grid_path}/HVHV'][:]

    # Convert to float32
    hh = np.array(hh, dtype=np.float32)
    hv = np.array(hv, dtype=np.float32)

print("Data loaded. Computing composite...")

# Avoid log of zero/negative
hh[hh <= 0] = np.nan
hv[hv <= 0] = np.nan

# Convert to dB
hh_db = 10 * np.log10(hh)
hv_db = 10 * np.log10(hv)

# Create a ratio band (HH/HV). In linear scale, ratio is HH/HV. In dB it's HH_dB - HV_dB.
ratio_db = hh_db - hv_db

print("Normalizing channels...")
r = normalize(hh_db, 2, 98)
g = normalize(hv_db, 2, 98)
b = normalize(ratio_db, 2, 98)

# Stack to RGB
rgb = np.dstack((r, g, b))

print("Plotting...")
fig, ax = plt.subplots(figsize=(15, 15))
ax.imshow(rgb)
ax.axis('off')
ax.set_title("NISAR S-Band SAR (R: HH, G: HV, B: HH/HV)", fontsize=20, color='white')

# Set background to black
fig.patch.set_facecolor('black')

plt.tight_layout()
output_file = "nisar_composite.png"
plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='black')
print(f"Saved visualization to {output_file}")
