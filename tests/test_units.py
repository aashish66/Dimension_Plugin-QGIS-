"""Plain pytest, no QGIS required -- units.py has no qgis import."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dimension_tool"))

from units import format_angle, format_length, meters_to_unit  # noqa: E402


def test_meters_to_unit_conversions():
    assert meters_to_unit(1000, "km") == 1.0
    assert math.isclose(meters_to_unit(1609.344, "mi"), 1.0)
    assert math.isclose(meters_to_unit(0.3048, "ft"), 1.0)
    assert math.isclose(meters_to_unit(1852, "nmi"), 1.0)


def test_us_survey_foot_is_slightly_different_from_international_foot():
    # The US survey foot (1200/3937 m) differs from the international foot
    # (0.3048 m exactly) in the 7th significant digit -- easy to get backwards.
    us_ft = meters_to_unit(1000, "us-ft")
    intl_ft = 1000 / 0.3048
    assert us_ft != intl_ft
    assert math.isclose(us_ft, intl_ft, rel_tol=1e-5)


def test_format_length_uses_requested_precision():
    assert format_length(1000, "m", 0) == "1000 m"
    assert format_length(1000, "km", 2) == "1.00 km"


def test_format_angle_uses_degree_symbol():
    assert format_angle(90) == "90.0°"
    assert format_angle(45.567, 2) == "45.57°"
