"""Creates the GeoPackage a Dimension layer lives in, with its schema, a
rule-based renderer (native QGIS arrow symbol layers for the measured
line/arc, a plain thin symbol for extension lines/rays), and a label
expression -- so once created, every bit of styling stays fully editable
through the ordinary Layer Properties panel like any other vector layer.

Every PyQGIS call here was verified against a real QGIS 3.44 install before
being written (see dev-notes/qgis-api-verification.md) rather than assumed
from documentation memory alone -- in particular `QgsArrowSymbolLayer`'s
enums live on the class itself (`QgsArrowSymbolLayer.HeadDouble`, etc.), not
on `Qgis`, and `QgsField`'s `QVariant`-based constructor is deprecated in
favor of `QMetaType.Type`.
"""

from __future__ import annotations

from dataclasses import dataclass

from qgis.core import (
    Qgis,
    QgsArrowSymbolLayer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsField,
    QgsFields,
    QgsLineSymbol,
    QgsPalLayerSettings,
    QgsProperty,
    QgsRuleBasedRenderer,
    QgsSymbolLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType

# Geometry "part" values a dimension's constituent features carry. A single
# dimension (identified by `dim_id`) is made of one or more of these; exactly
# one of PART_DIM_DOUBLE / PART_DIM_SINGLE per dimension carries the label
# (see build_renderer / build_labeling: the "Show label" rule is simply
# `part IN (dim_double, dim_single)`, so every dimension type is covered by
# the same rule with no per-type special-casing).
PART_EXTENSION = "ext"  # linear/aligned's extension lines: thin, no arrow
PART_RAY = "ray"  # angular's two rays: thin, no arrow
PART_DIM_DOUBLE = "dim_double"  # linear/aligned/angular-arc/diameter: both ends arrowed
PART_DIM_SINGLE = "dim_single"  # radius/leader: arrow only at the last vertex

DIM_TYPES = ("linear", "aligned", "angular", "radius", "diameter", "leader")

GEOMETRY_LABEL_EXPRESSION = f"\"part\" IN ('{PART_DIM_DOUBLE}', '{PART_DIM_SINGLE}')"


@dataclass
class DimensionStyle:
    """Default symbology a new Dimension layer is created with. Every value
    here is only the *starting point* -- editable afterwards like any other
    layer's style, and overridable per-feature via the `color` field."""

    color: str = "#1d4ed8"
    line_width_mm: float = 0.4
    arrow_head_length_mm: float = 2.6
    arrow_head_thickness_mm: float = 1.8
    text_height_mm: float = 2.6
    font_family: str = ""  # "" = the application's default font
    default_unit: str = "m"
    default_precision: int = 2


def dimension_fields() -> QgsFields:
    fields = QgsFields()
    fields.append(QgsField("dim_id", QMetaType.Type.QString))
    fields.append(QgsField("dim_type", QMetaType.Type.QString))
    fields.append(QgsField("part", QMetaType.Type.QString))
    fields.append(QgsField("value", QMetaType.Type.Double))
    fields.append(QgsField("unit", QMetaType.Type.QString))
    fields.append(QgsField("precision", QMetaType.Type.Int))
    fields.append(QgsField("label_text", QMetaType.Type.QString))
    fields.append(QgsField("color", QMetaType.Type.QString))
    # Free-text note for a leader dimension (its label_text mirrors this at
    # creation time, but the field is kept editable/attribute-table-visible
    # separately, since label_text may later diverge -- e.g. if a user hides
    # the map label but wants the note preserved in the attribute table).
    fields.append(QgsField("note", QMetaType.Type.QString))
    return fields


def _color_property(style: DimensionStyle) -> QgsProperty:
    """A per-feature color override from the `color` field, falling back to
    the layer's default when the field is null/empty."""
    return QgsProperty.fromExpression(
        f"CASE WHEN \"color\" IS NULL OR \"color\" = '' THEN '{style.color}' ELSE \"color\" END"
    )


def _thin_symbol(style: DimensionStyle) -> QgsLineSymbol:
    symbol = QgsLineSymbol.createSimple(
        {"color": style.color, "width": str(style.line_width_mm * 0.6)}
    )
    layer = symbol.symbolLayer(0)
    prop = _color_property(style)
    layer.setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeColor, prop)
    return symbol


def _arrow_symbol(style: DimensionStyle, head_type) -> QgsLineSymbol:
    arrow = QgsArrowSymbolLayer()
    arrow.setArrowType(QgsArrowSymbolLayer.ArrowPlain)
    arrow.setHeadType(head_type)
    arrow.setIsCurved(False)
    arrow.setIsRepeated(False)
    arrow.setArrowWidth(style.line_width_mm)
    arrow.setArrowStartWidth(style.line_width_mm)
    arrow.setHeadLength(style.arrow_head_length_mm)
    arrow.setHeadThickness(style.arrow_head_thickness_mm)
    color = _qcolor(style.color)
    arrow.setColor(color)
    arrow.setFillColor(color)
    arrow.setStrokeColor(color)
    prop = _color_property(style)
    arrow.setDataDefinedProperty(QgsSymbolLayer.PropertyFillColor, prop)
    arrow.setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeColor, prop)

    symbol = QgsLineSymbol()
    symbol.changeSymbolLayer(0, arrow)
    return symbol


def build_renderer(style: DimensionStyle) -> QgsRuleBasedRenderer:
    root_rule = QgsRuleBasedRenderer.Rule(None)

    double_symbol = _arrow_symbol(style, QgsArrowSymbolLayer.HeadDouble)
    rule_double = QgsRuleBasedRenderer.Rule(
        double_symbol, 0, 0, f"\"part\" = '{PART_DIM_DOUBLE}'"
    )
    rule_double.setLabel("Dimension line (double arrow)")
    root_rule.appendChild(rule_double)

    single_symbol = _arrow_symbol(style, QgsArrowSymbolLayer.HeadSingle)
    rule_single = QgsRuleBasedRenderer.Rule(
        single_symbol, 0, 0, f"\"part\" = '{PART_DIM_SINGLE}'"
    )
    rule_single.setLabel("Dimension line (single arrow)")
    root_rule.appendChild(rule_single)

    thin_symbol = _thin_symbol(style)
    rule_thin = QgsRuleBasedRenderer.Rule(
        thin_symbol, 0, 0, f"\"part\" IN ('{PART_EXTENSION}', '{PART_RAY}')"
    )
    rule_thin.setLabel("Extension line / ray")
    root_rule.appendChild(rule_thin)

    return QgsRuleBasedRenderer(root_rule)


def build_labeling(style: DimensionStyle) -> QgsVectorLayerSimpleLabeling:
    settings = QgsPalLayerSettings()
    settings.fieldName = "label_text"
    settings.isExpression = False
    settings.placement = Qgis.LabelPlacement.Line
    settings.priority = 10

    text_format = settings.format()
    font = text_format.font()
    if style.font_family:
        font.setFamily(style.font_family)
    text_format.setFont(font)
    text_format.setSize(style.text_height_mm)
    text_format.setSizeUnit(Qgis.RenderUnit.Millimeters)
    text_format.setColor(_qcolor(style.color))
    text_format.buffer().setEnabled(True)
    text_format.buffer().setSize(0.5)
    text_format.buffer().setColor(_qcolor("#ffffff"))
    settings.setFormat(text_format)

    # Exactly one feature per dimension (the measured line/arc itself, never
    # its extension lines or rays) carries a label -- see
    # GEOMETRY_LABEL_EXPRESSION's docstring above for why this single rule
    # covers every dimension type with no per-type branching.
    show_property = QgsProperty.fromExpression(GEOMETRY_LABEL_EXPRESSION)
    settings.dataDefinedProperties().setProperty(
        QgsPalLayerSettings.Property.Show, show_property
    )

    return QgsVectorLayerSimpleLabeling(settings)


def _qcolor(hex_color: str):
    from qgis.PyQt.QtGui import QColor

    return QColor(hex_color)


def create_dimension_layer(
    gpkg_path: str,
    layer_name: str,
    crs: QgsCoordinateReferenceSystem,
    style: DimensionStyle,
) -> QgsVectorLayer:
    """Create (or add a layer to) a GeoPackage at `gpkg_path` and return it,
    loaded and styled. Raises RuntimeError with the driver's own message on
    failure."""
    import os

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    options.fileEncoding = "UTF-8"
    # Only meaningful (and only valid) when the file already exists: adding a
    # dimensions layer into a GeoPackage the user already has other layers
    # in, without disturbing them. A brand-new path must be left at the
    # default (create the file fresh) -- CreateOrOverwriteLayer assumes an
    # openable existing file and raises "Opening of data source in update
    # mode failed" otherwise.
    if os.path.exists(gpkg_path):
        options.actionOnExistingFile = (
            QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
        )

    writer = QgsVectorFileWriter.create(
        gpkg_path,
        dimension_fields(),
        QgsWkbTypes.LineString,
        crs,
        QgsCoordinateTransformContext(),
        options,
    )
    if isinstance(writer, tuple):
        error_code, error_message = writer[0], writer[1]
        raise RuntimeError(f"Could not create GeoPackage layer: {error_message}")
    if writer.hasError() != QgsVectorFileWriter.WriterError.NoError:
        message = writer.errorMessage()
        del writer
        raise RuntimeError(f"Could not create GeoPackage layer: {message}")
    del writer  # Flush/close before QgsVectorLayer opens the same file.

    layer = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", layer_name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Created '{gpkg_path}' but the resulting layer failed to load.")

    layer.setRenderer(build_renderer(style))
    layer.setLabeling(build_labeling(style))
    layer.setLabelsEnabled(True)
    layer.setCustomProperty("dimension_tool/is_dimension_layer", True)
    layer.setCustomProperty("dimension_tool/default_unit", style.default_unit)
    layer.setCustomProperty("dimension_tool/default_precision", style.default_precision)
    return layer


def is_dimension_layer(layer) -> bool:
    return bool(layer is not None and layer.customProperty("dimension_tool/is_dimension_layer", False))
