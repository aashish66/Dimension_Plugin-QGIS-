"""Builds the QgsFeature list for one dimension (linear, aligned, angular,
radius, diameter, or leader), given the points the map tool collected.

Kept apart from the interactive QgsMapTool subclasses (dimension_tools.py) so
the feature-building logic -- the part with actual measurement/formatting
correctness at stake -- can be exercised without a live canvas or mouse
events, the same separation GeoLibre's plugin uses between its
build*DimensionFeatures() functions and its click handlers.

All points are (map-space) QgsPointXY in the *layer's* CRS. Where a function
takes a `map_to_pixel` (a `QgsMapToPixel`, a lightweight value object -- not
a live canvas -- so this module stays headlessly testable), the *offset*
distance is applied in canvas-pixel space and converted back, exactly like
GeoLibre's plugin does with `map.project()`/`map.unproject()`: a dimension
line's offset needs to look the same number of pixels away regardless of
zoom, which a map-unit offset can't give you, and it must be computed in
pixel space specifically (not just scaled) because pixel-Y increases
downward while map-Y increases upward -- doing the offset math in map space
would silently mirror which side of the line it lands on relative to where
the user actually clicked.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from qgis.core import QgsFeature, QgsFields, QgsGeometry, QgsMapToPixel, QgsPointXY

from . import dimension_geometry as geom
from .dimension_layer import PART_DIM_DOUBLE, PART_DIM_SINGLE, PART_EXTENSION, PART_RAY
from .measurement import Measurer
from .units import format_angle, format_length

ARC_SEGMENTS = 64


def new_dim_id() -> str:
    return uuid.uuid4().hex[:12]


def _point(p: QgsPointXY) -> tuple[float, float]:
    return (p.x(), p.y())


def _qpoint(p: tuple[float, float]) -> QgsPointXY:
    return QgsPointXY(p[0], p[1])


def _to_pixel(map_to_pixel: QgsMapToPixel, p: QgsPointXY) -> tuple[float, float]:
    px = map_to_pixel.transform(p)
    return (px.x(), px.y())


def _to_map(map_to_pixel: QgsMapToPixel, xy: tuple[float, float]) -> QgsPointXY:
    return map_to_pixel.toMapCoordinatesF(xy[0], xy[1])


def _make_feature(
    fields: QgsFields,
    geometry: QgsGeometry,
    dim_id: str,
    dim_type: str,
    part: str,
    value: float | None,
    unit: str,
    precision: int,
    label_text: str | None,
    color: str | None,
    note: str | None = None,
) -> QgsFeature:
    feature = QgsFeature(fields)
    feature.setGeometry(geometry)
    feature.setAttribute("dim_id", dim_id)
    feature.setAttribute("dim_type", dim_type)
    feature.setAttribute("part", part)
    feature.setAttribute("value", value)
    feature.setAttribute("unit", unit)
    feature.setAttribute("precision", precision)
    feature.setAttribute("label_text", label_text)
    feature.setAttribute("color", color)
    feature.setAttribute("note", note)
    return feature


def _line(points: list[tuple[float, float]]) -> QgsGeometry:
    return QgsGeometry.fromPolylineXY([_qpoint(p) for p in points])


@dataclass
class LinearResult:
    features: list[QgsFeature]
    value_meters: float


def build_aligned_features(
    fields: QgsFields,
    measurer: Measurer,
    map_to_pixel: QgsMapToPixel,
    p1: QgsPointXY,
    p2: QgsPointXY,
    offset_px: float,  # signed perpendicular offset, in canvas pixels
    unit: str,
    precision: int,
    color: str,
    dim_id: str | None = None,
) -> LinearResult:
    """The true straight-line distance between p1 and p2, with the dimension
    line parallel to that segment -- an "Aligned" dimension in CAD terms.
    See build_linear_features for "Linear" (axis-locked horizontal/vertical)."""
    a_px, b_px = _to_pixel(map_to_pixel, p1), _to_pixel(map_to_pixel, p2)
    perp = geom.perpendicular_unit(a_px, b_px)
    o1 = _to_map(map_to_pixel, geom.offset_point(a_px, perp, offset_px))
    o2 = _to_map(map_to_pixel, geom.offset_point(b_px, perp, offset_px))

    value_meters = measurer.length_meters(p1, p2)
    label = format_length(value_meters, unit, precision)
    dim_id = dim_id or new_dim_id()

    features = [
        _make_feature(
            fields, _line([_point(p1), _point(o1)]), dim_id, "aligned", PART_EXTENSION, None, unit, precision, None, color
        ),
        _make_feature(
            fields, _line([_point(p2), _point(o2)]), dim_id, "aligned", PART_EXTENSION, None, unit, precision, None, color
        ),
        _make_feature(
            fields, _line([_point(o1), _point(o2)]), dim_id, "aligned", PART_DIM_DOUBLE, value_meters, unit, precision, label, color
        ),
    ]
    return LinearResult(features=features, value_meters=value_meters)


def build_linear_features(
    fields: QgsFields,
    measurer: Measurer,
    map_to_pixel: QgsMapToPixel,
    p1: QgsPointXY,
    p2: QgsPointXY,
    axis: str,  # "x" (horizontal dimension line, measures the X-difference) or "y" (vertical, measures Y-difference)
    offset_px: float,  # perpendicular distance of the dimension line from p1, in canvas pixels
    unit: str,
    precision: int,
    color: str,
    dim_id: str | None = None,
) -> LinearResult:
    """A "Linear" dimension in CAD terms: constrained to measure only the
    horizontal or only the vertical component of the distance between p1 and
    p2 (unlike Aligned, which measures the true distance between them). The
    extension lines run from the original points out to an axis-aligned
    dimension line, exactly like AutoCAD's DIMLINEAR."""
    a, b = _point(p1), _point(p2)
    a_px, b_px = _to_pixel(map_to_pixel, p1), _to_pixel(map_to_pixel, p2)
    if axis == "x":
        # Horizontal dimension line on screen: offset is applied along pixel Y.
        baseline_px_y = a_px[1] + offset_px
        o1 = _to_map(map_to_pixel, (a_px[0], baseline_px_y))
        o2 = _to_map(map_to_pixel, (b_px[0], baseline_px_y))
        projected_b = QgsPointXY(b[0], a[1])
    else:
        # Vertical dimension line on screen: offset is applied along pixel X.
        baseline_px_x = a_px[0] + offset_px
        o1 = _to_map(map_to_pixel, (baseline_px_x, a_px[1]))
        o2 = _to_map(map_to_pixel, (baseline_px_x, b_px[1]))
        projected_b = QgsPointXY(a[0], b[1])

    value_meters = measurer.length_meters(p1, projected_b)
    label = format_length(value_meters, unit, precision)
    dim_id = dim_id or new_dim_id()

    features = [
        _make_feature(
            fields, _line([a, _point(o1)]), dim_id, "linear", PART_EXTENSION, None, unit, precision, None, color
        ),
        _make_feature(
            fields, _line([b, _point(o2)]), dim_id, "linear", PART_EXTENSION, None, unit, precision, None, color
        ),
        _make_feature(
            fields, _line([_point(o1), _point(o2)]), dim_id, "linear", PART_DIM_DOUBLE, value_meters, unit, precision, label, color
        ),
    ]
    return LinearResult(features=features, value_meters=value_meters)


@dataclass
class AngularResult:
    features: list[QgsFeature]
    value_degrees: float


def build_angular_features(
    fields: QgsFields,
    map_to_pixel: QgsMapToPixel,
    p1: QgsPointXY,
    vertex: QgsPointXY,
    p2: QgsPointXY,
    arc_radius_px: float,  # canvas pixels, so the arc looks the same size at any zoom
    precision: int,
    color: str,
    dim_id: str | None = None,
) -> AngularResult | None:
    v, a, b = _point(vertex), _point(p1), _point(p2)
    angle = geom.angle_at_vertex_degrees(v, a, b)
    if angle < 0.01:
        return None

    # The angle itself is measured in map space (a CAD angular dimension
    # describes the drawing's own geometry, not a geodesic bearing), but the
    # arc is sampled in pixel space so its radius reads as the same size on
    # screen regardless of zoom -- same reasoning as the offset in
    # build_aligned_features above.
    v_px, a_px, b_px = _to_pixel(map_to_pixel, vertex), _to_pixel(map_to_pixel, p1), _to_pixel(map_to_pixel, p2)
    start_angle, sweep = geom.signed_sweep(v_px, a_px, b_px)
    arc_px = geom.arc_points(v_px, arc_radius_px, start_angle, sweep, ARC_SEGMENTS)
    arc = [_point(_to_map(map_to_pixel, pt)) for pt in arc_px]
    label = format_angle(angle, precision)
    dim_id = dim_id or new_dim_id()

    features = [
        _make_feature(fields, _line([v, a]), dim_id, "angular", PART_RAY, None, "deg", precision, None, color),
        _make_feature(fields, _line([v, b]), dim_id, "angular", PART_RAY, None, "deg", precision, None, color),
        _make_feature(
            fields, _line(arc), dim_id, "angular", PART_DIM_DOUBLE, angle, "deg", precision, label, color
        ),
    ]
    return AngularResult(features=features, value_degrees=angle)


def build_radius_features(
    fields: QgsFields,
    measurer: Measurer,
    center: QgsPointXY,
    edge: QgsPointXY,
    unit: str,
    precision: int,
    color: str,
    dim_id: str | None = None,
) -> LinearResult:
    radius_m = measurer.length_meters(center, edge)
    label = f"R {format_length(radius_m, unit, precision)}"
    dim_id = dim_id or new_dim_id()
    # Vertex order [center, edge]: the arrow (a single-headed
    # QgsArrowSymbolLayer) is drawn at the line's *last* vertex, so it must
    # land on the circle's edge, not its center.
    feature = _make_feature(
        fields,
        _line([_point(center), _point(edge)]),
        dim_id,
        "radius",
        PART_DIM_SINGLE,
        radius_m,
        unit,
        precision,
        label,
        color,
    )
    return LinearResult(features=[feature], value_meters=radius_m)


def build_diameter_features(
    fields: QgsFields,
    measurer: Measurer,
    center: QgsPointXY,
    edge: QgsPointXY,
    unit: str,
    precision: int,
    color: str,
    dim_id: str | None = None,
) -> LinearResult:
    c, e = _point(center), _point(edge)
    opposite = (2 * c[0] - e[0], 2 * c[1] - e[1])
    radius_m = measurer.length_meters(center, edge)
    diameter_m = radius_m * 2
    label = f"⌀ {format_length(diameter_m, unit, precision)}"
    dim_id = dim_id or new_dim_id()
    feature = _make_feature(
        fields,
        _line([e, opposite]),
        dim_id,
        "diameter",
        PART_DIM_DOUBLE,
        diameter_m,
        unit,
        precision,
        label,
        color,
    )
    return LinearResult(features=[feature], value_meters=diameter_m)


def build_leader_feature(
    fields: QgsFields,
    target: QgsPointXY,
    label_position: QgsPointXY,
    note: str,
    color: str,
    dim_id: str | None = None,
) -> QgsFeature:
    dim_id = dim_id or new_dim_id()
    # Vertex order [label_position, target]: same reasoning as radius above,
    # the single-headed arrow must land on the point being annotated.
    return _make_feature(
        fields,
        _line([_point(label_position), _point(target)]),
        dim_id,
        "leader",
        PART_DIM_SINGLE,
        None,
        "",
        0,
        note,
        color,
        note=note,
    )
