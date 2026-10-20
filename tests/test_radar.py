import pytest

from satviz.radar import band_of, radar_facts


@pytest.mark.parametrize("ghz, band", [(1.257, "L"), (3.2, "S"), (5.405, "C"), (5.4, "C"), (9.6, "X"), (0.4, "")])
def test_band_of(ghz, band):
    assert band_of(ghz) == band


def test_radar_facts_wavelength_and_explicit_band():
    f = radar_facts(5.405)
    assert f == dict(radar_band="C", freq_ghz=5.405, wavelength_cm=5.55)
    assert radar_facts(1.2575)["wavelength_cm"] == pytest.approx(23.84, abs=0.01)
    assert radar_facts(3.2, "S")["radar_band"] == "S"  # a band stated by the product wins
