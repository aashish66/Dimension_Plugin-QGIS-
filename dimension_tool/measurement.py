"""CRS-aware length measurement, returning a canonical value in meters so
`units.py` (whose `LENGTH_UNITS` table is meters-based) is the single place
display-unit conversion happens.

The two CRS cases need genuinely different math, verified against a real
QGIS install rather than assumed:

- Geographic CRS (degrees): a straight-line Cartesian distance between two
  [lng, lat] pairs is meaningless as a length, so this measures the
  ellipsoidal (geodesic) distance via QgsDistanceArea, which already returns
  meters.
- Projected CRS (a linear unit -- meters, US survey feet, ...): a CAD-style
  dimension tool should report the *planar* distance in the drawing's own
  units -- literally the length of the line as digitized -- not a secondary
  geodesic correction. Enabling QgsDistanceArea's ellipsoidal mode for a
  projected CRS measurably disagrees with the planar distance (confirmed:
  500.0 m planar vs 500.2 m ellipsoidal for the same two UTM points), which
  would make the dimension's reported value not match its own geometry.
  Instead this measures planar in the CRS's native unit, then converts that
  unit to meters with QgsUnitTypes.fromUnitToUnitFactor.
"""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsDistanceArea,
    QgsPointXY,
    QgsUnitTypes,
)


class Measurer:
    """Wraps one QgsDistanceArea configured for a specific layer CRS."""

    def __init__(self, crs: QgsCoordinateReferenceSystem, transform_context: QgsCoordinateTransformContext):
        self.crs = crs
        self._distance_area = QgsDistanceArea()
        self._distance_area.setSourceCrs(crs, transform_context)
        if crs.isGeographic():
            self._is_planar = False
            self._distance_area.setEllipsoid(crs.ellipsoidAcronym() or "WGS84")
            self._unit_factor = 1.0
        else:
            self._is_planar = True
            self._distance_area.setEllipsoid("NONE")
            self._unit_factor = QgsUnitTypes.fromUnitToUnitFactor(
                crs.mapUnits(), QgsUnitTypes.DistanceUnit.DistanceMeters
            )

    def length_meters(self, p1: QgsPointXY, p2: QgsPointXY) -> float:
        raw = self._distance_area.measureLine(p1, p2)
        return raw * self._unit_factor if self._is_planar else raw
