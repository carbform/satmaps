"""Acquisition metadata read from the GCOV file itself (identification group, swaths, calibration, processing flags).

Everything printed on a figure about *when*, *which pass*, *which band* and *what the processor did* comes from here,
not from the scene or layout configuration.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

from satviz.config import BandSpec

C_M_S = 299_792_458.0


@dataclass(frozen=True)
class BandMeta:
    key: str
    instrument: str  # LSAR / SSAR
    radar_band: str  # L / S
    granule_id: str
    crid: str  # compositeReleaseId
    product_version: str
    spec_version: str
    processing_center: str
    track: int
    frame: int
    pass_direction: str  # "ascending" / "descending"
    look_direction: str  # "left" / "right"
    start: datetime
    end: datetime
    freq_ghz: float
    wavelength_cm: float
    bandwidth_mhz: float | None
    posting_m: float
    epsg: int
    crs: str  # "UTM 46N"
    polarisations: str  # "HH/HV"
    looks: float | None
    calibrated: bool  # HH and HV scale factors are populated (non-zero, finite)
    rfi: str  # "not applied", "applied", or the algorithm name (e.g. FDNF)
    rfi_applied: bool
    noise_corrected: bool
    iono_geolocation: bool
    symmetrization: bool
    exception_flag: int  # identification/hasInputDataException


def _s(v) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)


def _parse_time(text: str) -> datetime:
    # the files carry 8-9 fractional digits; datetime keeps microseconds
    return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", text.strip()))


def _crs_label(epsg: int) -> str:
    if 32601 <= epsg <= 32660:
        return f"UTM {epsg - 32600}N"
    if 32701 <= epsg <= 32760:
        return f"UTM {epsg - 32700}S"
    return f"EPSG:{epsg}"


def _flag(v) -> bool:
    return _s(v).strip().lower() == "true"


def read_band_metadata(path: Path, spec: BandSpec) -> BandMeta:
    root = spec.group.rsplit("/", 1)[0]  # science/SSAR
    with h5py.File(path, "r") as f:
        ident = f[f"{root}/identification"]
        g = f[f"{spec.group}/grids/frequencyA"]
        meta = f[f"{spec.group}/metadata"]
        swath = meta["sourceData/swaths/frequencyA"]
        par = meta["processingInformation/parameters"]
        freq = float(swath["centerFrequency"][()])
        bw = float(swath["rangeBandwidth"][()]) / 1e6 if "rangeBandwidth" in swath else None
        epsg = int(g["projection"][()])
        pols = "/".join(_s(p) for p in g["listOfPolarizations"][()])
        rows, cols = spec.rows, spec.cols
        nl = g["numberOfLooks"][rows[0]:rows[1]:100, cols[0]:cols[1]:100].astype(float)
        looks = float(np.nanmedian(nl)) if np.isfinite(nl).any() else None
        cal = meta["calibrationInformation/frequencyA"]
        sf = [float(cal[p]["scaleFactor"][()]) for p in ("HH", "HV")]
        rfi_raw = _s(par["rfiMitigationApplied"][()]).strip()
        rfi_off = rfi_raw.lower() in ("false", "", "none")
        return BandMeta(
            key=spec.key, instrument=_s(ident["instrumentName"][()]), radar_band=_s(ident["radarBand"][()]),
            granule_id=_s(ident["granuleId"][()]), crid=_s(ident["compositeReleaseId"][()]),
            product_version=_s(ident["productVersion"][()]), spec_version=_s(ident["productSpecificationVersion"][()]),
            processing_center=_s(ident["processingCenter"][()]), track=int(ident["trackNumber"][()]),
            frame=int(ident["frameNumber"][()]), pass_direction=_s(ident["orbitPassDirection"][()]).lower(),
            look_direction=_s(ident["lookDirection"][()]).lower(),
            start=_parse_time(_s(ident["zeroDopplerStartTime"][()])), end=_parse_time(_s(ident["zeroDopplerEndTime"][()])),
            freq_ghz=freq / 1e9, wavelength_cm=C_M_S / freq * 100, bandwidth_mhz=bw,
            posting_m=float(abs(g["xCoordinateSpacing"][()])), epsg=epsg, crs=_crs_label(epsg), polarisations=pols, looks=looks,
            calibrated=all(np.isfinite(v) and v != 0 for v in sf),
            rfi="not applied" if rfi_off else ("applied" if rfi_raw.lower() == "true" else rfi_raw), rfi_applied=not rfi_off,
            noise_corrected=_flag(par["noiseCorrectionApplied"][()]),
            iono_geolocation=_flag(par["rangeIonosphericGeolocationCorrectionApplied"][()])
            and _flag(par["azimuthIonosphericGeolocationCorrectionApplied"][()]),
            symmetrization=_flag(par["polarimetricSymmetrizationApplied"][()]),
            exception_flag=int(ident["hasInputDataException"][()]) if "hasInputDataException" in ident else 0,
        )
