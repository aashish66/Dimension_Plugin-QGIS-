"""QGIS entry point. QGIS calls classFactory(iface) to instantiate the plugin."""


def classFactory(iface):
    from .dimension_plugin import DimensionPlugin

    return DimensionPlugin(iface)
