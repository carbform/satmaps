from satviz.sensors.nisar_gcov.io import load_roi
from satviz.sensors.nisar_gcov.metadata import read_band_metadata


def test_metadata_is_read_from_the_file(scene):
    s = read_band_metadata(scene.band_path("S"), scene.bands["S"])
    l_ = read_band_metadata(scene.band_path("L"), scene.bands["L"])
    assert (s.track, s.frame, s.pass_direction, s.look_direction) == (112, 16, "ascending", "left")
    assert (s.start.year, s.start.month, s.start.day, s.start.hour, s.start.minute) == (2026, 9, 25, 22, 57)
    assert abs(s.freq_ghz - 3.2) < 1e-9 and round(s.wavelength_cm) == 9
    assert abs(l_.freq_ghz - 1.239) < 1e-9 and round(l_.wavelength_cm) == 24
    assert s.crs == "UTM 46N" and s.posting_m == 10 and s.polarisations == "HH/HV"


def test_processing_flags(scene):
    s = read_band_metadata(scene.band_path("S"), scene.bands["S"])
    l_ = read_band_metadata(scene.band_path("L"), scene.bands["L"])
    assert not s.calibrated and l_.calibrated  # zero scale factors mean unpopulated
    assert s.rfi == "FDNF" and s.rfi_applied and l_.rfi == "not applied" and not l_.rfi_applied
    assert s.looks == 16.0 and l_.looks is None  # L-band numberOfLooks is NaN


def test_load_roi_attaches_metadata(scene):
    assert load_roi(scene, "L")["meta"].crid == "P05023"
