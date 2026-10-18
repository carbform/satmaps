import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import os
import warnings
warnings.filterwarnings('ignore')

filename = 'NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5'
group = '/science/SSAR/GCOV/grids/frequencyA'

print("Opening datasets with dask...")
# Load datasets using xarray with dask chunking
ds = xr.open_dataset(filename, group=group, engine='h5netcdf', chunks={'yCoordinates': 2048, 'xCoordinates': 2048})

hhhh = ds['HHHH']
hvhv = ds['HVHV']

print("Original shape:", hhhh.shape)

# Let's coarsen to make it manageable for plotting
# Coarsening by factor of 10 in both dimensions
factor = 10
hhhh_coarse = hhhh.coarsen(yCoordinates=factor, xCoordinates=factor, boundary='trim').mean()
hvhv_coarse = hvhv.coarsen(yCoordinates=factor, xCoordinates=factor, boundary='trim').mean()

print("Coarse shape:", hhhh_coarse.shape)

print("Computing downsampled arrays... this might take a minute.")
hhhh_val = hhhh_coarse.compute().values
hvhv_val = hvhv_coarse.compute().values

print("Replacing NaNs and zeros...")
# Avoid division by zero and log of zero
hhhh_val = np.where(np.isnan(hhhh_val) | (hhhh_val <= 0), 1e-10, hhhh_val)
hvhv_val = np.where(np.isnan(hvhv_val) | (hvhv_val <= 0), 1e-10, hvhv_val)

print("Converting to dB...")
hhhh_db = 10 * np.log10(hhhh_val)
hvhv_db = 10 * np.log10(hvhv_val)

# Simple stretching
def stretch(band, p_low=2, p_high=98):
    p2, p98 = np.percentile(band, (p_low, p_high))
    stretched = (band - p2) / (p98 - p2)
    return np.clip(stretched, 0, 1)

print("Creating RGB composite...")
r = stretch(hhhh_db)
g = stretch(hvhv_db)
ratio = stretch(hhhh_db - hvhv_db) # Ratio in dB is subtraction
b = ratio

rgb = np.dstack((r, g, b))

print("Plotting...")
fig, ax = plt.subplots(figsize=(15, 15))
ax.imshow(rgb, aspect='equal')
ax.axis('off')

# Add a dark theme style to the figure
fig.patch.set_facecolor('#1e1e1e')
plt.title("NISAR GCOV S-Band\nRGB Composite (R: HHHH, G: HVHV, B: HHHH/HVHV)", fontsize=18, color='white', pad=20)

plt.tight_layout()
output_img = 'nisar_gcov_rgb.png'
plt.savefig(output_img, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
print(f"Saved visualization to {output_img}")
