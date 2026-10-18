import xarray as xr
import rioxarray
import numpy as np

filename = 'NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5'
group = '/science/SSAR/GCOV/grids/frequencyA'

print("Opening dataset...")
ds = xr.open_dataset(filename, group=group, engine='h5netcdf', chunks={'yCoordinates': 2048, 'xCoordinates': 2048})

epsg = ds['projection'].attrs['epsg_code']

# Zoom slice
y_start, y_end = 16000, 20000
x_start, x_end = 16000, 20000

print("Extracting zoom slice...")
hhhh = ds['HHHH'].isel(yCoordinates=slice(y_start, y_end), xCoordinates=slice(x_start, x_end))
hvhv = ds['HVHV'].isel(yCoordinates=slice(y_start, y_end), xCoordinates=slice(x_start, x_end))

# Rename coords to x, y for rioxarray
hhhh = hhhh.rename({'xCoordinates': 'x', 'yCoordinates': 'y'})
hvhv = hvhv.rename({'xCoordinates': 'x', 'yCoordinates': 'y'})

# Combine into a DataArray with band dimension
print("Stacking bands...")
da = xr.concat([hhhh, hvhv], dim='band')
da = da.assign_coords(band=[1, 2])
da.attrs['long_name'] = ['HHHH', 'HVHV']

# Set spatial dimensions
da.rio.write_crs(f"EPSG:{epsg}", inplace=True)
da.rio.set_spatial_dims(x_dim="x", y_dim="y", inplace=True)

out_file = "nisar_zoom.tif"
print(f"Writing to {out_file}...")
da.rio.to_raster(out_file, driver='GTiff', compress='lzw')
print("Done!")
