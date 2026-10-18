import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import os
import warnings
warnings.filterwarnings('ignore')

filename = 'NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5'
group = '/science/SSAR/GCOV/grids/frequencyA'

print("Opening datasets with dask...")
ds = xr.open_dataset(filename, group=group, engine='h5netcdf', chunks={'yCoordinates': 2048, 'xCoordinates': 2048})

hhhh = ds['HHHH']
hvhv = ds['HVHV']

print("Original shape:", hhhh.shape)

# Define slice range (e.g. 4000x4000 area)
# Original is roughly 33840 x 34848
y_start, y_end = 16000, 20000
x_start, x_end = 16000, 20000

print(f"Zooming into full resolution subset: Y[{y_start}:{y_end}], X[{x_start}:{x_end}]")

hhhh_zoom = hhhh.isel(yCoordinates=slice(y_start, y_end), xCoordinates=slice(x_start, x_end))
hvhv_zoom = hvhv.isel(yCoordinates=slice(y_start, y_end), xCoordinates=slice(x_start, x_end))

print("Zoomed shape:", hhhh_zoom.shape)

print("Computing subset arrays...")
hhhh_val = hhhh_zoom.compute().values
hvhv_val = hvhv_zoom.compute().values

print("Replacing NaNs and zeros...")
# Avoid division by zero and log of zero
hhhh_val = np.where(np.isnan(hhhh_val) | (hhhh_val <= 0), 1e-10, hhhh_val)
hvhv_val = np.where(np.isnan(hvhv_val) | (hvhv_val <= 0), 1e-10, hvhv_val)

print("Converting to dB...")
hhhh_db = 10 * np.log10(hhhh_val)
hvhv_db = 10 * np.log10(hvhv_val)

# SAR data stretching - standard deviation stretch or min/max
# We will use percentile based stretching (e.g., 2% to 98%) to discard extreme speckle outliers
def stretch(band, p_low=2, p_high=98):
    p_min, p_max = np.percentile(band, (p_low, p_high))
    stretched = (band - p_min) / (p_max - p_min)
    return np.clip(stretched, 0, 1)

print("Creating standard SAR RGB composite...")
# Red: Co-pol (HH)
r = stretch(hhhh_db)
# Green: Cross-pol (HV)
g = stretch(hvhv_db)
# Blue: Difference in dB (HH - HV)
b = stretch(hhhh_db - hvhv_db)

rgb = np.dstack((r, g, b))

print("Plotting...")
fig, ax = plt.subplots(figsize=(12, 12))
ax.imshow(rgb, aspect='equal')
ax.axis('off')

# Add a dark theme style to the figure
fig.patch.set_facecolor('#1e1e1e')
plt.title(f"NISAR GCOV Zoomed In (4000x4000 px)\nRGB Composite (R: HHHH, G: HVHV, B: HHHH - HVHV)", fontsize=16, color='white', pad=20)

plt.tight_layout()
output_img = 'nisar_gcov_rgb_zoom.png'
plt.savefig(output_img, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
print(f"Saved visualization to {output_img}")
