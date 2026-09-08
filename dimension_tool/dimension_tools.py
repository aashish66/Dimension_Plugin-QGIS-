"""Interactive QgsMapTool subclasses, one per dimension type. All the actual
measurement/geometry logic lives in dimension_features.py and
dimension_geometry.py (headlessly testable); these classes only translate
mouse events into calls onto that logic, mirroring the split between
GeoLibre's click handlers and its build*DimensionFeatures() functions.

Every tool is a click-count state machine, reset by Escape or a right click,
finished automatically once its last point is placed. All snapping goes
through the *canvas's own* snapping configuration (QgsSnappingUtils), so a
Dimension tool respects whatever the project's Snapping Options panel is
already set to rather than reimplementing snapping.
"""

from __future__ import annotations

from qgis.core import QgsPointXY, QgsWkbTypes
from qgis.gui import QgsMapMouseEvent, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QInputDialog

from . import dimension_features as feat
from . import dimension_geometry as geom


class DimensionMapTool(QgsMapTool):
    """Shared click-state-machine, preview rubber band, and snapping for
    every dimension tool. Subclasses set `required_points` and implement
    `instructions()` and `build_features()`; those needing a live preview
    richer than "a straight line to the cursor" also override
    `update_preview()`."""

    required_points: int = 2

    def __init__(self, canvas, controller):
        super().__init__(canvas)
        self.controller = controller
        self.pending: list[QgsPointXY] = []
        # A plain guide line during drawing -- QGIS's arrow symbol layer
        # draws the real arrowheads on the *committed* feature via the
        # layer's renderer, not via geometry type, so the rubber band never
        # needs a polygon band of its own.
        self.preview_line = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # -- lifecycle -----------------------------------------------------
    def activate(self) -> None:
        super().activate()
        self._restyle_preview()
        self.controller.set_status(self.instructions())

    def deactivate(self) -> None:
        self.reset()
        self.controller.set_status("")
        super().deactivate()

    def _restyle_preview(self) -> None:
        color = QColor(self.controller.color)
        self.preview_line.setColor(color)
        self.preview_line.setWidth(2)

    def reset(self) -> None:
        self.pending = []
        self.preview_line.reset(QgsWkbTypes.LineGeometry)

    # -- shared plumbing -------------------------------------------------
    def instructions(self) -> str:
        return ""

    def snap_point(self, event: QgsMapMouseEvent) -> QgsPointXY:
        if self.controller.snap_enabled:
            match = self.canvas().snappingUtils().snapToMap(event.pos())
            if match.isValid():
                return match.point()
        return self.toMapCoordinates(event.pos())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reset()
            self.controller.set_status(self.instructions())

    def canvasReleaseEvent(self, event: QgsMapMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.reset()
            self.controller.set_status(self.instructions())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self.controller.active_layer:
            self.controller.set_status("Create or select a Dimension layer first (Dimension → New Dimension Layer…).")
            return

        point = self.snap_point(event)
        self.pending.append(point)
        if len(self.pending) >= self.required_points:
            self.finish()
        else:
            self.controller.set_status(self.instructions())

    def canvasMoveEvent(self, event: QgsMapMouseEvent) -> None:
        if not self.pending:
            return
        cursor = self.snap_point(event)
        self.update_preview(cursor)

    def update_preview(self, cursor: QgsPointXY) -> None:
        """Default preview: a straight line from the last pending point to
        the cursor. Subclasses that need a richer preview (the angular arc,
        the offset dimension line) override this."""
        self.preview_line.reset(QgsWkbTypes.LineGeometry)
        self.preview_line.addPoint(self.pending[-1])
        self.preview_line.addPoint(cursor)

    def finish(self) -> None:
        features = self.build_features()
        self.reset()
        if features:
            self.controller.commit_features(features)
        self.controller.set_status(self.instructions())

    def build_features(self):
        raise NotImplementedError


class AlignedDimensionTool(DimensionMapTool):
    required_points = 3

    def instructions(self) -> str:
        n = len(self.pending)
        if n == 0:
            return "Aligned dimension: click the first point."
        if n == 1:
            return "Aligned dimension: click the second point."
        return "Aligned dimension: click to place the dimension line."

    def update_preview(self, cursor: QgsPointXY) -> None:
        if len(self.pending) == 1:
            super().update_preview(cursor)
            return
        p1, p2 = self.pending
        m2p = self.canvas().mapSettings().mapToPixel()
        offset_px = geom.signed_perpendicular_offset(
            _to_px(m2p, p1), _to_px(m2p, p2), _to_px(m2p, cursor)
        )
        result = feat.build_aligned_features(
            self.controller.fields, self.controller.measurer, m2p, p1, p2,
            offset_px, self.controller.unit, self.controller.precision, self.controller.color,
        )
        _show_preview(self.preview_line, result.features)

    def build_features(self):
        p1, p2, placement = self.pending
        m2p = self.canvas().mapSettings().mapToPixel()
        offset_px = geom.signed_perpendicular_offset(
            _to_px(m2p, p1), _to_px(m2p, p2), _to_px(m2p, placement)
        )
        result = feat.build_aligned_features(
            self.controller.fields, self.controller.measurer, m2p, p1, p2,
            offset_px, self.controller.unit, self.controller.precision, self.controller.color,
        )
        return result.features


class LinearDimensionTool(DimensionMapTool):
    required_points = 3

    def instructions(self) -> str:
        n = len(self.pending)
        if n == 0:
            return "Linear dimension: click the first point."
        if n == 1:
            return "Linear dimension: click the second point."
        return "Linear dimension: click to place the dimension line."

    def _axis(self) -> str:
        p1, p2 = self.pending[0], self.pending[1]
        return "x" if abs(p2.x() - p1.x()) >= abs(p2.y() - p1.y()) else "y"

    def update_preview(self, cursor: QgsPointXY) -> None:
        if len(self.pending) == 1:
            super().update_preview(cursor)
            return
        p1, p2 = self.pending
        m2p = self.canvas().mapSettings().mapToPixel()
        axis = self._axis()
        offset_px = self._offset_px(m2p, p1, axis, cursor)
        result = feat.build_linear_features(
            self.controller.fields, self.controller.measurer, m2p, p1, p2,
            axis, offset_px, self.controller.unit, self.controller.precision, self.controller.color,
        )
        _show_preview(self.preview_line, result.features)

    @staticmethod
    def _offset_px(m2p, p1: QgsPointXY, axis: str, cursor: QgsPointXY) -> float:
        p1_px = _to_px(m2p, p1)
        cursor_px = _to_px(m2p, cursor)
        return (cursor_px[1] - p1_px[1]) if axis == "x" else (cursor_px[0] - p1_px[0])

    def build_features(self):
        p1, p2, placement = self.pending
        m2p = self.canvas().mapSettings().mapToPixel()
        axis = self._axis()
        offset_px = self._offset_px(m2p, p1, axis, placement)
        result = feat.build_linear_features(
            self.controller.fields, self.controller.measurer, m2p, p1, p2,
            axis, offset_px, self.controller.unit, self.controller.precision, self.controller.color,
        )
        return result.features


class AngularDimensionTool(DimensionMapTool):
    required_points = 3

    def instructions(self) -> str:
        n = len(self.pending)
        if n == 0:
            return "Angular dimension: click the first ray's endpoint."
        if n == 1:
            return "Angular dimension: click the angle's vertex."
        return "Angular dimension: click the second ray's endpoint."

    def _arc_radius_px(self, vertex: QgsPointXY, cursor: QgsPointXY) -> float:
        m2p = self.canvas().mapSettings().mapToPixel()
        v_px, c_px = _to_px(m2p, vertex), _to_px(m2p, cursor)
        return max(20.0, geom.distance(v_px, c_px) * 0.6)

    def update_preview(self, cursor: QgsPointXY) -> None:
        if len(self.pending) == 1:
            super().update_preview(cursor)
            return
        p1, vertex = self.pending
        m2p = self.canvas().mapSettings().mapToPixel()
        radius_px = self._arc_radius_px(vertex, cursor)
        result = feat.build_angular_features(
            self.controller.fields, m2p, p1, vertex, cursor,
            radius_px, self.controller.precision, self.controller.color,
        )
        if result:
            _show_preview(self.preview_line, result.features)

    def build_features(self):
        p1, vertex, p2 = self.pending
        m2p = self.canvas().mapSettings().mapToPixel()
        radius_px = self._arc_radius_px(vertex, p2)
        result = feat.build_angular_features(
            self.controller.fields, m2p, p1, vertex, p2,
            radius_px, self.controller.precision, self.controller.color,
        )
        return result.features if result else []


class RadiusDimensionTool(DimensionMapTool):
    required_points = 2

    def instructions(self) -> str:
        return "Radius dimension: click the center, then a point on the edge." if not self.pending \
            else "Radius dimension: click a point on the edge."

    def build_features(self):
        center, edge = self.pending
        result = feat.build_radius_features(
            self.controller.fields, self.controller.measurer, center, edge,
            self.controller.unit, self.controller.precision, self.controller.color,
        )
        return result.features


class DiameterDimensionTool(DimensionMapTool):
    required_points = 2

    def instructions(self) -> str:
        return "Diameter dimension: click the center, then a point on the edge." if not self.pending \
            else "Diameter dimension: click a point on the edge."

    def update_preview(self, cursor: QgsPointXY) -> None:
        center = self.pending[0]
        result = feat.build_diameter_features(
            self.controller.fields, self.controller.measurer, center, cursor,
            self.controller.unit, self.controller.precision, self.controller.color,
        )
        _show_preview(self.preview_line, result.features)

    def build_features(self):
        center, edge = self.pending
        result = feat.build_diameter_features(
            self.controller.fields, self.controller.measurer, center, edge,
            self.controller.unit, self.controller.precision, self.controller.color,
        )
        return result.features


class LeaderDimensionTool(DimensionMapTool):
    required_points = 2

    def instructions(self) -> str:
        return "Leader: click the point to annotate, then where the label should sit." if not self.pending \
            else "Leader: click where the label should sit."

    def build_features(self):
        target, label_position = self.pending
        note, accepted = QInputDialog.getMultiLineText(
            self.canvas(), "Leader note", "Text for this leader:"
        )
        if not accepted or not note.strip():
            return []
        feature = feat.build_leader_feature(
            self.controller.fields, target, label_position, note.strip(), self.controller.color
        )
        return [feature]


def _to_px(map_to_pixel, point: QgsPointXY) -> tuple[float, float]:
    px = map_to_pixel.transform(point)
    return (px.x(), px.y())


def _show_preview(line_band: QgsRubberBand, features) -> None:
    line_band.reset(QgsWkbTypes.LineGeometry)
    for feature in features:
        line_band.addGeometry(feature.geometry())
