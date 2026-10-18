import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import warnings
warnings.filterwarnings('ignore')

filename = 'NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5'
group = '/science/SSAR/GCOV/grids/frequencyA'

print("Opening dataset...")
ds = xr.open_dataset(filename, group=group, engine='h5netcdf', chunks={'yCoordinates': 2048, 'xCoordinates': 2048})

hhhh = ds['HHHH']
hvhv = ds['HVHV']

# Bottom edge slice (e.g. river usually found here based on full extent)
# Tile size is ~33840 x 34848. Bottom edge center:
y_start, y_end = 28000, 32000
x_start, x_end = 12000, 16000

print(f"Extracting slice Y[{y_start}:{y_end}] X[{x_start}:{x_end}]...")
hhhh_slice = hhhh.isel(yCoordinates=slice(y_start, y_end), xCoordinates=slice(x_start, x_end))
hvhv_slice = hvhv.isel(yCoordinates=slice(y_start, y_end), xCoordinates=slice(x_start, x_end))

hhhh_val = hhhh_slice.compute().values
hvhv_val = hvhv_slice.compute().values

# Clean NaNs
hhhh_val = np.where(np.isnan(hhhh_val) | (hhhh_val <= 0), 1e-10, hhhh_val)
hvhv_val = np.where(np.isnan(hvhv_val) | (hvhv_val <= 0), 1e-10, hvhv_val)

print("Converting to dB...")
hhhh_db = 10 * np.log10(hhhh_val)
hvhv_db = 10 * np.log10(hvhv_val)

def stretch(band, p_low=2, p_high=98):
    p_min, p_max = np.percentile(band, (p_low, p_high))
    stretched = (band - p_min) / (p_max - p_min)
    return np.clip(stretched, 0, 1)

print("Preparing combinations...")
# 1. Standard RGB
r = stretch(hhhh_db)
g = stretch(hvhv_db)
b = stretch(hhhh_db - hvhv_db)
rgb_std = np.dstack((r, g, b))

# 2. HHHH only (greyscale)
hhhh_stretch = stretch(hhhh_db)
grey_h = np.dstack((hhhh_stretch, hhhh_stretch, hhhh_stretch))

# 3. HVHV only (greyscale)
hvhv_stretch = stretch(hvhv_db)
grey_v = np.dstack((hvhv_stretch, hvhv_stretch, hvhv_stretch))

# 4. False Color (Water Focus) - mapping ratio to red, HV to blue
water_false = np.dstack((stretch(hvhv_db - hhhh_db), stretch(hhhh_db), stretch(hvhv_db)))

print("Plotting Neobrutalist Infographic...")

# Neobrutalism configuration
plt.rcParams['font.family'] = 'monospace'
plt.rcParams['font.weight'] = 'bold'
plt.rcParams['axes.linewidth'] = 4
plt.rcParams['axes.edgecolor'] = 'black'
bg_color = '#ffd166' # bold retro yellow

fig = plt.figure(figsize=(16, 16), facecolor=bg_color)

# Add a striking title
fig.suptitle('NISAR GCOV // S-BAND ANALYSIS', 
             fontsize=36, fontweight='black', x=0.05, y=0.96, ha='left',
             path_effects=[pe.withStroke(linewidth=8, foreground='black'), pe.Normal()],
             color='white')

# Subtitle
fig.text(0.05, 0.93, 'RIVER SYSTEM AT BOTTOM EDGE (Y:28k-32k, X:12k-16k)', 
         fontsize=18, fontweight='bold', color='black',
         bbox=dict(facecolor='#06d6a0', edgecolor='black', boxstyle='square,pad=0.5', lw=4))

# Function to add neobrutalist axis
def setup_neo_ax(ax, img, title):
    ax.imshow(img, aspect='auto')
    ax.set_xticks([])
    ax.set_yticks([])
    # Title box
    ax.set_title(title, fontsize=16, fontweight='bold', pad=15, 
                 bbox=dict(facecolor='#ef476f', edgecolor='black', lw=3, boxstyle='square,pad=0.4'))
    # Hard drop shadow effect using a background patch
    rect = plt.Rectangle((0.02, -0.02), 1, 1, transform=ax.transAxes, color='black', zorder=-1)
    ax.add_patch(rect)

# Grid layout
ax1 = plt.subplot(2, 2, 1)
setup_neo_ax(ax1, rgb_std, 'COMPOSITE_01: STANDARD RGB (HH/HV/RATIO)')

ax2 = plt.subplot(2, 2, 2)
setup_neo_ax(ax2, water_false, 'COMPOSITE_02: FALSE COLOR (RATIO/HH/HV)')

ax3 = plt.subplot(2, 2, 3)
setup_neo_ax(ax3, grey_h, 'BAND_01: HHHH CO-POL (SURFACE)')
ax3.title.set_bbox(dict(facecolor='#118ab2', edgecolor='black', lw=3, boxstyle='square,pad=0.4'))

ax4 = plt.subplot(2, 2, 4)
setup_neo_ax(ax4, grey_v, 'BAND_02: HVHV CROSS-POL (VOLUME)')
ax4.title.set_bbox(dict(facecolor='#118ab2', edgecolor='black', lw=3, boxstyle='square,pad=0.4'))

plt.subplots_adjust(wspace=0.15, hspace=0.15, left=0.05, right=0.95, top=0.88, bottom=0.05)

output_img = 'nisar_river_neobrutal.png'
plt.savefig(output_img, dpi=300, facecolor=bg_color, bbox_inches='tight')
print(f"Saved visualization to {output_img}")
