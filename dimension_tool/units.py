"""Length unit conversion, independent of QGIS/PyQt so it can be unit-tested
without a running QGIS process (`qgis.core` is only importable inside QGIS's
own Python)."""

from __future__ import annotations

from dataclasses import dataclass

# Meters is authoritative: QgsDistanceArea measures in meters (see
# QgsDistanceArea.setEllipsoid), so every other unit is a straight conversion
# from that.
LENGTH_UNITS: dict[str, "Unit"] = {}


@dataclass(frozen=True)
class Unit:
    key: str
    label: str
    to_meters: float
    symbol: str


def _register(key: str, label: str, to_meters: float, symbol: str) -> Unit:
    unit = Unit(key=key, label=label, to_meters=to_meters, symbol=symbol)
    LENGTH_UNITS[key] = unit
    return unit


_register("m", "Meters", 1.0, "m")
_register("km", "Kilometers", 1000.0, "km")
_register("ft", "Feet", 0.3048, "ft")
_register("us-ft", "US Survey Feet", 1200.0 / 3937.0, "us-ft")
_register("yd", "Yards", 0.9144, "yd")
_register("mi", "Miles", 1609.344, "mi")
_register("nmi", "Nautical Miles", 1852.0, "nmi")

LENGTH_UNIT_ORDER = list(LENGTH_UNITS.keys())
DEFAULT_LENGTH_UNIT = "m"


def meters_to_unit(meters: float, unit_key: str) -> float:
    return meters / LENGTH_UNITS[unit_key].to_meters


def format_length(meters: float, unit_key: str, precision: int = 2) -> str:
    value = meters_to_unit(meters, unit_key)
    return f"{value:.{precision}f} {LENGTH_UNITS[unit_key].symbol}"


def format_angle(degrees: float, precision: int = 1) -> str:
    return f"{degrees:.{precision}f}°"
