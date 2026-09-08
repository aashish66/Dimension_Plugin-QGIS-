"""Pure 2D vector/arc math shared by every dimension tool.

Deliberately has no `qgis`/`PyQt` import so it can be unit-tested with plain
pytest, outside QGIS's own Python. It also has no opinion about *which* space
its (x, y) tuples live in: the map tools call it twice with different spaces
for the same reason GeoLibre's plugin does -- an offset defined in *map*
(ground) units would look enormous at low zoom and invisible at high zoom, so
offsets are computed in *canvas pixel* space (via QgsMapCanvas.mapToPixel /
toMapCoordinates) and only the final, offset points are converted back to map
coordinates for the stored geometry. Everything in this module is agnostic to
that distinction; it only ever adds/subtracts coordinates.
"""

from __future__ import annotations

import math

Point = tuple[float, float]


def distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def perpendicular_unit(a: Point, b: Point) -> Point:
    """Unit vector perpendicular to a->b (rotated 90° counter-clockwise)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    return (-dy / length, dx / length)


def offset_point(point: Point, direction: Point, distance_: float) -> Point:
    return (point[0] + direction[0] * distance_, point[1] + direction[1] * distance_)


def signed_perpendicular_offset(a: Point, b: Point, point: Point) -> float:
    """How far `point` sits to the (signed) perpendicular side of the line a->b."""
    px, py = perpendicular_unit(a, b)
    return (point[0] - a[0]) * px + (point[1] - a[1]) * py


def midpoint(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def normalize_angle_delta(delta: float) -> float:
    """Normalize a radian angle difference into (-pi, pi]."""
    while delta <= -math.pi:
        delta += 2 * math.pi
    while delta > math.pi:
        delta -= 2 * math.pi
    return delta


def angle_at_vertex_degrees(vertex: Point, p1: Point, p2: Point) -> float:
    """Absolute angle in degrees at `vertex` between rays toward p1 and p2."""
    a1 = math.atan2(p1[1] - vertex[1], p1[0] - vertex[0])
    a2 = math.atan2(p2[1] - vertex[1], p2[0] - vertex[0])
    return abs(math.degrees(normalize_angle_delta(a2 - a1)))


def arc_points(
    center: Point, radius: float, start_angle: float, sweep: float, segments: int = 48
) -> list[Point]:
    """Sample `segments` + 1 points along an arc, `sweep` radians from `start_angle`."""
    points = []
    for i in range(segments + 1):
        t = start_angle + sweep * (i / segments)
        points.append((center[0] + radius * math.cos(t), center[1] + radius * math.sin(t)))
    return points


def signed_sweep(vertex: Point, p1: Point, p2: Point) -> tuple[float, float]:
    """The angle at `vertex` from p1 toward p2, as (start_angle, signed_sweep) in radians."""
    a1 = math.atan2(p1[1] - vertex[1], p1[0] - vertex[0])
    a2 = math.atan2(p2[1] - vertex[1], p2[0] - vertex[0])
    return a1, normalize_angle_delta(a2 - a1)
