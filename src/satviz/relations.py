"""How the products of one figure relate, stated from facts in their own files.

A SAR pair is one of: same sensor and band (two dates), same sensor with different bands (NISAR L and S), different sensors
in the same band (EOS-04 and Sentinel-1, both C), or different sensors and bands. Every multi-input figure also gets the time
between acquisitions and, for SAR, a note when the backscatter conventions differ (sigma0 against gamma0), because values of
different conventions are not comparable by eye. Nothing here is looked up: it is all read from the products.
"""
from __future__ import annotations

from dataclasses import dataclass

from satviz.core import Product
from satviz.radar import BANDS


@dataclass(frozen=True)
class Relation:
    kind: str  # machine name: same_sensor_same_band, same_sensor_different_bands, ... see `relate`
    label: str  # short upper-case phrase for a subtitle
    notes: tuple[str, ...] = ()  # one-line statements for the notice strip


def _mid(p: Product):
    return p.meta["start"] + (p.meta["end"] - p.meta["start"]) / 2


def time_gap(products: list[Product]) -> str:
    """'Acquired 12 h 9 min apart', 'Acquired 6 days apart', or '' for one product. Within 5 minutes counts as one pass."""
    if len(products) < 2:
        return ""
    if all(p.meta.get("time_known", True) for p in products):
        times = [_mid(p) for p in products]
        gap = max(times) - min(times)
        mins = round(gap.total_seconds() / 60)
        if mins < 5:
            return "Acquired in the same pass"
        if mins < 60 * 24:
            h, m = divmod(mins, 60)
            return f"Acquired {h} h {m} min apart" if h else f"Acquired {m} min apart"
        days = round(gap.total_seconds() / 86400)
    else:  # a date without a reliable time: compare days only
        days = (max(p.meta["start"].date() for p in products) - min(p.meta["start"].date() for p in products)).days
        if days == 0:
            return "Acquired on the same day"
    return f"Acquired {days} day{'s' if days != 1 else ''} apart"


def _bands(products: list[Product]) -> list[tuple[str, float]]:
    """(band letter, wavelength cm or 0 when only the letter is known) of each distinct SAR band, longest wavelength first."""
    seen = {p.meta["radar_band"]: p.meta.get("wavelength_cm", 0.0) for p in products}
    order = [b for b, _, _ in BANDS]
    return sorted(seen.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order))


def _backscatter(products: list[Product]) -> str:
    kinds = list(dict.fromkeys(p.meta["backscatter"] for p in products if p.meta.get("backscatter")))
    if len(kinds) < 2:
        return ""
    return "Backscatter differs (" + " vs ".join(k.split(",")[0] for k in kinds) + "): not directly comparable"


def relate(products: list[Product]) -> Relation:
    """Classify the products of one figure and say what a reader must keep in mind."""
    if len(products) < 2:
        return Relation("single", "")
    kinds = {p.kind for p in products}
    gap = time_gap(products)
    if kinds == {"sar", "optical"}:
        return Relation("sar_optical", "RADAR AND OPTICAL", (gap,) if gap else ())
    platforms = list(dict.fromkeys(p.meta["platform"] for p in products))
    same_platform = len(platforms) == 1
    if kinds == {"optical"}:
        if same_platform:
            return Relation("optical_same_sensor", f"{platforms[0].upper()} · {len(products)} SCENES", (gap,) if gap else ())
        return Relation("optical_different_sensors", "OPTICAL · DIFFERENT SENSORS", (gap,) if gap else ())
    if untagged := [p for p in products if not p.meta.get("radar_band")]:
        # a band claim needs every product to state its band; otherwise say so instead of guessing
        names = ", ".join(dict.fromkeys(p.meta.get("label") or p.meta["platform"] for p in untagged))
        label = "SAR · " + ("SAME SENSOR" if same_platform else "DIFFERENT SENSORS")
        notes = [gap, f"Radar band not stated by the {names} product", _backscatter(products)]
        return Relation("sar_band_unknown", label, tuple(n for n in notes if n))
    bands = _bands(products)
    letters = [b for b, _ in bands]
    wl = ", ".join(f"{b}-band {w:g} cm" if w else f"{b}-band" for b, w in bands)
    if same_platform and len(bands) == 1:
        kind, label = "same_sensor_same_band", f"SAME SENSOR · {letters[0]}-BAND"
        notes = [gap]
    elif same_platform:
        kind, label = "same_sensor_different_bands", f"SAME SENSOR · {' VS '.join(letters)} BAND"
        notes = [wl, gap]
    elif len(bands) == 1:
        kind, label = "same_band_different_sensors", f"SAME BAND ({letters[0]}) · DIFFERENT SENSORS"
        notes = [gap]
    else:
        kind, label = "different_sensors_different_bands", f"DIFFERENT SENSORS · {' VS '.join(letters)} BAND"
        notes = [wl, gap]
    notes.append(_backscatter(products))
    return Relation(kind, label, tuple(n for n in notes if n))
