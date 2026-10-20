# Reference documents

Third-party product documentation used to write the sensor readers. The PDFs stay on disk and are git-ignored (about
40 MB, not ours to redistribute); this list says what each one was used for.

| File | Used for |
|---|---|
| `NISAR_D-102274_RevE_NASA_SDS_Product_Specification_L2_GCOV_...pdf`, `NISAR_Data_Product_Format_Document_V1.2.1_...pdf`, `NISAR_FINAL_9-6-19.pdf` | `nisar_gcov`: GCOV layout, calibration, mission description |
| `EOS_04_Data_Products_Format_Document.pdf` | `eos04`: Level-2B gamma0 calibration (section 6.3, eq. 9-11), noise bias (section 3.0), mask values |
| `R2_data_user_handbook.pdf` | `liss4`: LISS-IV bands, 10-bit quantisation, nominal saturation radiance. It gives no ESUN values or DN-to-radiance formula |
| `UserGuide_SurfaceReflectance_RS2.pdf`, `User-Guide-Surface_reflectance_from_Resourcesat-2A.pdf` | ISRO's 6S surface-reflectance products for LISS-III and AWiFS; context only, they do not cover LISS-IV |
| `Sentinel-2-Products-Specification-Document.pdf` | `sentinel2_l2a`: L2A scaling and the BOA offset |

Open points the documents do not settle are in `architecture.md` (LISS-IV saturation radiance vs `Lmax`, EOS-04 Beta0 vs Gamma0 constant).
