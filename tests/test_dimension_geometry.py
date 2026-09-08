"""Plain pytest, no QGIS required -- dimension_geometry.py has no qgis import."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dimension_tool"))

from dimension_geometry import (  # noqa: E402
    angle_at_vertex_degrees,
    arc_points,
    distance,
    midpoint,
    offset_point,
    perpendicular_unit,
    signed_perpendicular_offset,
    signed_sweep,
)


def test_distance_3_4_5_triangle():
    assert distance((0, 0), (3, 4)) == 5.0


def test_perpendicular_unit_is_unit_length_and_orthogonal():
    a, b = (0, 0), (10, 0)
    px, py = perpendicular_unit(a, b)
    assert math.isclose(px * px + py * py, 1.0)
    # Perpendicular to a horizontal segment must be purely vertical.
    assert math.isclose(px, 0.0, abs_tol=1e-9)


def test_offset_point_moves_by_exact_distance_along_direction():
    result = offset_point((0, 0), (0, 1), 5)
    assert result == (0, 5)


def test_signed_perpendicular_offset_sign_flips_across_the_line():
    a, b = (0, 0), (10, 0)
    left = signed_perpendicular_offset(a, b, (5, 5))
    right = signed_perpendicular_offset(a, b, (5, -5))
    assert (left > 0) != (right > 0)
    assert math.isclose(abs(left), abs(right))


def test_midpoint():
    assert midpoint((0, 0), (10, 20)) == (5, 10)


def test_angle_at_vertex_degrees_right_angle():
    vertex = (0, 0)
    assert math.isclose(angle_at_vertex_degrees(vertex, (10, 0), (0, 10)), 90.0)


def test_angle_at_vertex_degrees_is_symmetric():
    vertex = (0, 0)
    assert math.isclose(
        angle_at_vertex_degrees(vertex, (10, 0), (0, 10)),
        angle_at_vertex_degrees(vertex, (0, 10), (10, 0)),
    )


def test_angle_at_vertex_degrees_straight_line_is_180():
    vertex = (0, 0)
    assert math.isclose(angle_at_vertex_degrees(vertex, (10, 0), (-10, 0)), 180.0)


def test_arc_points_start_and_end_land_on_the_circle():
    center = (0, 0)
    radius = 10
    points = arc_points(center, radius, start_angle=0, sweep=math.pi / 2, segments=8)
    assert len(points) == 9
    assert math.isclose(points[0][0], radius)
    assert math.isclose(points[0][1], 0, abs_tol=1e-9)
    assert math.isclose(points[-1][0], 0, abs_tol=1e-9)
    assert math.isclose(points[-1][1], radius)
    for x, y in points:
        assert math.isclose(math.hypot(x, y), radius)


def test_signed_sweep_picks_the_shorter_direction():
    vertex = (0, 0)
    # p1 at 0 degrees, p2 at 90 degrees -> the shorter sweep is +90 degrees,
    # not -270.
    start, sweep = signed_sweep(vertex, (10, 0), (0, 10))
    assert math.isclose(start, 0.0, abs_tol=1e-9)
    assert math.isclose(sweep, math.pi / 2)
