import xarray as xr
import rioxarray
from dask.diagnostics import ProgressBar
import threading

filename = 'NISAR_S2_PR_GCOV_031_112_A_016_3700_DHNA_A_20260925T225740_20260925T225816_P00500_M_F_I_001.h5'
group = '/science/SSAR/GCOV/grids/frequencyA'

print("Opening dataset...")
ds = xr.open_dataset(filename, group=group, engine='h5netcdf', chunks={'yCoordinates': 4096, 'xCoordinates': 4096})
epsg = ds['projection'].attrs['epsg_code']

hhhh = ds['HHHH']
hvhv = ds['HVHV']

hhhh = hhhh.rename({'xCoordinates': 'x', 'yCoordinates': 'y'})
hvhv = hvhv.rename({'xCoordinates': 'x', 'yCoordinates': 'y'})

print("Stacking bands...")
da = xr.concat([hhhh, hvhv], dim='band')
da = da.assign_coords(band=[1, 2])

da.rio.write_crs(f"EPSG:{epsg}", inplace=True)
da.rio.set_spatial_dims(x_dim="x", y_dim="y", inplace=True)

out_file = "nisar_full.tif"
print(f"Writing full resolution tile to {out_file}...")
print("This may take several minutes as the uncompressed size is ~9.4 GB.")

with ProgressBar():
    da.rio.to_raster(
        out_file, 
        driver='GTiff', 
        compress='lzw', 
        tiled=True,
        blockxsize=1024,
        blockysize=1024,
        windowed=True,
        lock=threading.Lock()
    )

print("Done!")
