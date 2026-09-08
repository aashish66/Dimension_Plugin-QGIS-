"""The plugin's QGIS entry point: wires a toolbar + Dimension menu, owns the
shared `DimensionController` state the map tools read from, and handles
creating/selecting the active Dimension layer."""

from __future__ import annotations

import os

from qgis.core import QgsProject
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QActionGroup

from .dimension_dialog import NewDimensionLayerDialog
from .dimension_layer import create_dimension_layer, dimension_fields, is_dimension_layer
from .dimension_tools import (
    AlignedDimensionTool,
    AngularDimensionTool,
    DiameterDimensionTool,
    LeaderDimensionTool,
    LinearDimensionTool,
    RadiusDimensionTool,
)
from .measurement import Measurer
from .units import DEFAULT_LENGTH_UNIT

ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")
MENU_NAME = "&Dimension"

# (internal key, icon file, menu/toolbar text, tool class)
TOOL_SPECS = [
    ("linear", "linear.svg", "Linear Dimension", LinearDimensionTool),
    ("aligned", "aligned.svg", "Aligned Dimension", AlignedDimensionTool),
    ("angular", "angular.svg", "Angular Dimension", AngularDimensionTool),
    ("radius", "radius.svg", "Radius Dimension", RadiusDimensionTool),
    ("diameter", "diameter.svg", "Diameter Dimension", DiameterDimensionTool),
    ("leader", "leader.svg", "Leader", LeaderDimensionTool),
]


class DimensionController:
    """Shared state the map tools read from and write into; owned by the
    plugin so every tool (and the dialog, indirectly) sees the same active
    layer/style/unit/snap setting."""

    def __init__(self, iface):
        self.iface = iface
        self.active_layer = None
        self.color = "#1d4ed8"
        self.unit = DEFAULT_LENGTH_UNIT
        self.precision = 2
        self.snap_enabled = True
        self._measurer: Measurer | None = None
        self._measurer_crs = None

    @property
    def fields(self):
        return self.active_layer.fields() if self.active_layer else dimension_fields()

    @property
    def measurer(self) -> Measurer:
        crs = self.active_layer.crs() if self.active_layer else QgsProject.instance().crs()
        if self._measurer is None or self._measurer_crs != crs:
            self._measurer = Measurer(crs, QgsProject.instance().transformContext())
            self._measurer_crs = crs
        return self._measurer

    def set_status(self, message: str) -> None:
        self.iface.statusBarIface().showMessage(message, 0)

    def set_active_layer(self, layer) -> None:
        self.active_layer = layer
        self._measurer = None

    def commit_features(self, features) -> None:
        if not self.active_layer or not features:
            return
        layer = self.active_layer
        was_editable = layer.isEditable()
        if not was_editable and not layer.startEditing():
            self.iface.messageBar().pushWarning(
                "Dimension Tool", "Could not start editing the Dimension layer."
            )
            return
        layer.addFeatures(features)
        if not was_editable:
            layer.commitChanges()
        layer.triggerRepaint()


class DimensionPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.controller = DimensionController(iface)
        self.toolbar = None
        self.tool_group: QActionGroup | None = None
        self.new_layer_action: QAction | None = None
        self.snap_action: QAction | None = None
        self.tool_actions: dict[str, QAction] = {}
        self.tools = {}
        self._all_actions: list[QAction] = []

    # -- QGIS plugin interface ------------------------------------------
    def initGui(self) -> None:
        self.toolbar = self.iface.addToolBar("Dimension Tools")
        self.toolbar.setObjectName("DimensionToolsToolbar")

        self.new_layer_action = self._add_action(
            "new_layer.svg", "New Dimension Layer…", self._new_layer, checkable=False
        )

        self.tool_group = QActionGroup(self.toolbar)
        self.tool_group.setExclusive(True)
        for key, icon_file, text, tool_cls in TOOL_SPECS:
            action = self._add_action(
                icon_file, text, lambda checked, k=key: self._activate_tool(k, checked), checkable=True
            )
            self.tool_group.addAction(action)
            self.tool_actions[key] = action
            tool = tool_cls(self.iface.mapCanvas(), self.controller)
            tool.setAction(action)
            self.tools[key] = tool

        self.snap_action = self._add_action(
            "snap.svg", "Snap to features", self._toggle_snap, checkable=True
        )
        self.snap_action.setChecked(True)

        self.iface.mapCanvas().mapToolSet.connect(self._on_map_tool_changed)

    def unload(self) -> None:
        self.iface.mapCanvas().mapToolSet.disconnect(self._on_map_tool_changed)
        for action in self._all_actions:
            self.iface.removePluginMenu(MENU_NAME, action)
            self.toolbar.removeAction(action)
        if self.toolbar is not None:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        self.tools.clear()
        self.tool_actions.clear()
        self._all_actions.clear()

    # -- wiring helpers ---------------------------------------------------
    def _add_action(self, icon_file: str, text: str, callback, *, checkable: bool) -> QAction:
        icon = QIcon(os.path.join(ICON_DIR, icon_file))
        action = QAction(icon, text, self.iface.mainWindow())
        action.setCheckable(checkable)
        if checkable:
            action.toggled.connect(callback)
        else:
            action.triggered.connect(callback)
        self.toolbar.addAction(action)
        self.iface.addPluginToMenu(MENU_NAME, action)
        self._all_actions.append(action)
        return action

    # -- actions -----------------------------------------------------------
    def _new_layer(self) -> None:
        default_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        dialog = NewDimensionLayerDialog(self.iface.mainWindow(), default_crs=default_crs)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            layer = create_dimension_layer(dialog.gpkg_path(), dialog.layer_name(), dialog.crs(), dialog.style())
        except RuntimeError as error:
            self.iface.messageBar().pushCritical("Dimension Tool", str(error))
            return

        QgsProject.instance().addMapLayer(layer)
        style = dialog.style()
        self.controller.set_active_layer(layer)
        self.controller.color = style.color
        self.controller.unit = style.default_unit
        self.controller.precision = style.default_precision
        self.iface.messageBar().pushSuccess("Dimension Tool", f"Created '{dialog.layer_name()}'.")

    def _activate_tool(self, key: str, checked: bool) -> None:
        if not checked:
            return
        if self.controller.active_layer is None or not is_dimension_layer(self.controller.active_layer):
            candidate = self.iface.activeLayer()
            if candidate is not None and is_dimension_layer(candidate):
                self.controller.set_active_layer(candidate)
        if self.controller.active_layer is None:
            self.iface.messageBar().pushWarning(
                "Dimension Tool", "Create or select a Dimension layer first (Dimension → New Dimension Layer…)."
            )
            self.tool_actions[key].setChecked(False)
            return
        self.iface.mapCanvas().setMapTool(self.tools[key])

    def _toggle_snap(self, checked: bool) -> None:
        self.controller.snap_enabled = checked

    def _on_map_tool_changed(self, new_tool, old_tool) -> None:
        if new_tool not in self.tools.values():
            for action in self.tool_actions.values():
                action.setChecked(False)
