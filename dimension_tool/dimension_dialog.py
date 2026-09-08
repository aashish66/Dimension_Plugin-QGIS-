"""The "New Dimension Layer" dialog: picks the GeoPackage path/layer name,
the CRS (project/map CRS, an existing layer's CRS, or any CRS via the
ordinary QGIS projection browser), and the default symbology/unit/precision a
new Dimension layer is created with.
"""

from __future__ import annotations

from qgis.core import QgsCoordinateReferenceSystem, QgsProject
from qgis.gui import QgsColorButton, QgsFileWidget, QgsProjectionSelectionWidget
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from .dimension_layer import DimensionStyle
from .units import LENGTH_UNIT_ORDER, LENGTH_UNITS


class NewDimensionLayerDialog(QDialog):
    def __init__(self, parent=None, default_crs: QgsCoordinateReferenceSystem | None = None):
        super().__init__(parent)
        self.setWindowTitle("New Dimension Layer")
        self.setMinimumWidth(420)

        self.file_widget = QgsFileWidget()
        self.file_widget.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.file_widget.setFilter("GeoPackage (*.gpkg)")

        self.name_edit = QLineEdit("dimensions")

        self.layer_crs_combo = QComboBox()
        self.layer_crs_combo.addItem("Project (map) CRS", None)
        for layer in QgsProject.instance().mapLayers().values():
            self.layer_crs_combo.addItem(f"Same as: {layer.name()}", layer.crs())
        self.layer_crs_combo.addItem("Choose below…", "custom")
        self.layer_crs_combo.currentIndexChanged.connect(self._apply_combo_crs)

        self.crs_widget = QgsProjectionSelectionWidget()
        self.crs_widget.setCrs(default_crs or QgsProject.instance().crs())
        self.crs_widget.crsChanged.connect(self._crs_widget_edited)

        self.color_button = QgsColorButton()
        self.color_button.setColor(QColor(DimensionStyle().color))

        self.width_spin = self._make_double_spin(0.1, 5.0, DimensionStyle().line_width_mm, 0.1)
        self.head_length_spin = self._make_double_spin(0.5, 10.0, DimensionStyle().arrow_head_length_mm, 0.1)
        self.head_thickness_spin = self._make_double_spin(0.2, 6.0, DimensionStyle().arrow_head_thickness_mm, 0.1)
        self.text_height_spin = self._make_double_spin(1.0, 12.0, DimensionStyle().text_height_mm, 0.1)

        self.unit_combo = QComboBox()
        for key in LENGTH_UNIT_ORDER:
            self.unit_combo.addItem(LENGTH_UNITS[key].label, key)
        default_index = self.unit_combo.findData(DimensionStyle().default_unit)
        if default_index >= 0:
            self.unit_combo.setCurrentIndex(default_index)

        self.precision_spin = QSpinBox()
        self.precision_spin.setRange(0, 6)
        self.precision_spin.setValue(DimensionStyle().default_precision)

        form = QFormLayout()
        form.addRow("GeoPackage file", self.file_widget)
        form.addRow("Layer name", self.name_edit)
        form.addRow("Coordinate system", self.layer_crs_combo)
        form.addRow("", self.crs_widget)
        form.addRow("Color", self.color_button)
        form.addRow("Line width (mm)", self.width_spin)
        form.addRow("Arrow head length (mm)", self.head_length_spin)
        form.addRow("Arrow head thickness (mm)", self.head_thickness_spin)
        form.addRow("Label text height (mm)", self.text_height_spin)
        form.addRow("Default unit", self.unit_combo)
        form.addRow("Default decimal precision", self.precision_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @staticmethod
    def _make_double_spin(minimum: float, maximum: float, value: float, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        spin.setValue(value)
        return spin

    def _apply_combo_crs(self, index: int) -> None:
        data = self.layer_crs_combo.itemData(index)
        if data in (None, "custom"):
            if data is None:
                self.crs_widget.setCrs(QgsProject.instance().crs())
            return
        self.crs_widget.setCrs(data)

    def _crs_widget_edited(self) -> None:
        # The user picked a CRS directly in the browser rather than through
        # the combo; make sure the combo reflects "custom" so it doesn't look
        # like it still matches whatever preset was last selected.
        custom_index = self.layer_crs_combo.findData("custom")
        if custom_index >= 0 and self.layer_crs_combo.currentIndex() != custom_index:
            self.layer_crs_combo.blockSignals(True)
            self.layer_crs_combo.setCurrentIndex(custom_index)
            self.layer_crs_combo.blockSignals(False)

    def _on_accept(self) -> None:
        if not self.file_widget.filePath():
            self.file_widget.setFocus()
            return
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        self.accept()

    # -- results -----------------------------------------------------------
    def gpkg_path(self) -> str:
        path = self.file_widget.filePath()
        if not path.lower().endswith(".gpkg"):
            path += ".gpkg"
        return path

    def layer_name(self) -> str:
        return self.name_edit.text().strip() or "dimensions"

    def crs(self) -> QgsCoordinateReferenceSystem:
        return self.crs_widget.crs()

    def style(self) -> DimensionStyle:
        return DimensionStyle(
            color=self.color_button.color().name(),
            line_width_mm=self.width_spin.value(),
            arrow_head_length_mm=self.head_length_spin.value(),
            arrow_head_thickness_mm=self.head_thickness_spin.value(),
            text_height_mm=self.text_height_spin.value(),
            default_unit=self.unit_combo.currentData(),
            default_precision=self.precision_spin.value(),
        )
