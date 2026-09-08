# How this plugin was verified

PyQGIS's API surface is large and easy to misremember (enum locations move
between versions, some methods are deprecated in favor of a differently-named
replacement, some behave subtly differently than the equivalent-sounding
method). Rather than writing this plugin from documentation memory alone,
every non-trivial API call was run against a real QGIS install
(`C:\Program Files\QGIS 3.44.13`, via its bundled
`bin\python-qgis-ltr.bat` interpreter) before being committed, using small
throwaway scripts. This caught real bugs that a plausible-looking first draft
would not have surfaced:

1. **`QgsField(name, QVariant.String)`** — the classic constructor is
   deprecated in 3.44; the replacement takes a `QMetaType.Type` instead
   (`QgsField(name, QMetaType.Type.QString)`).

2. **`QgsVectorFileWriter.create(...)`** — the transform-context argument
   cannot be `None`; it needs a real `QgsCoordinateTransformContext()`.

3. **`QgsVectorFileWriter.SaveVectorOptions.actionOnExistingFile`** — setting
   `CreateOrOverwriteLayer` on a path that doesn't exist yet fails with
   *"Opening of data source in update mode failed"*. It's only valid when
   appending a layer to a GeoPackage that already exists; a brand-new path
   must leave this unset.

4. **`QgsArrowSymbolLayer`'s enums live on the class itself**
   (`QgsArrowSymbolLayer.HeadDouble`, `.HeadSingle`, `.ArrowPlain`), not on
   `Qgis` (there is no `Qgis.ArrowType`).

5. **`QgsSymbolLayer.setColor()` / `setFillColor()` / `setStrokeColor()`**
   require an actual `QColor`, not a hex string — unlike
   `QgsLineSymbol.createSimple({"color": "#rrggbb"})`, which does accept a
   string in its properties dict.

6. **`QgsDistanceArea` with an ellipsoid set always measures geodesically**,
   even for a projected CRS. For two real UTM10N points 500 m apart, enabling
   the ellipsoid measured 500.2 m instead of 500.0 m. A CAD-style dimension
   tool wants the *planar* distance in the drawing's own projected units —
   what's literally drawn — not a secondary geodesic correction, so
   `measurement.py`'s `Measurer` only enables the ellipsoid for a *geographic*
   CRS (where a Cartesian distance between two `[lng, lat]` pairs would be
   meaningless anyway) and otherwise measures planar and converts the CRS's
   native linear unit to meters via `QgsUnitTypes.fromUnitToUnitFactor`.

7. **Pixel ↔ map coordinate transforms must go through `QgsMapToPixel`, and
   the offset math must happen entirely in pixel space**, not partially in
   map space. Pixel Y increases downward while map Y increases upward, so
   computing a "perpendicular direction" in map-space coordinates and a
   "which side did the user click" test in pixel-space coordinates would
   silently disagree about which side is positive, mirroring the dimension
   line relative to where the user actually placed it. `QgsMapToPixel` also
   needed `toMapCoordinatesF` (not the plain, int-only `toMapCoordinates`) to
   round-trip sub-pixel positions.

## What was verified end-to-end

- `dimension_layer.create_dimension_layer()`: GeoPackage creation, the
  rule-based renderer (all three rules, by their filter expressions), the
  label expression and its `Show`-property gating, and adding real features
  through `QgsVectorLayer`'s edit buffer.
- `dimension_features.py`: every builder (`build_aligned_features`,
  `build_linear_features` for both axes, `build_angular_features`,
  `build_radius_features`, `build_diameter_features`,
  `build_leader_feature`), checked against hand-computed expected values (a
  3-4-5 triangle, a 90° angle, etc.) in both a projected CRS (UTM10N) and a
  geographic CRS (EPSG:4326).
- `dimension_dialog.NewDimensionLayerDialog`: constructs, the CRS combo ↔
  projection-widget sync in both directions, and the GeoPackage path/name/
  style getters.
- `dimension_plugin.DimensionPlugin`: `initGui()`/`unload()` against a
  hand-written fake `iface` (QGIS's real `iface` only exists inside a running
  QGIS process), tool activation with and without an active Dimension layer,
  the exclusive tool-button group, and a full click→build→commit round trip
  writing a feature into a real layer.

## What was *not* verified this way

Real mouse-event dispatch (`canvasPressEvent`/`canvasMoveEvent` triggered by
actual Qt input, as opposed to calling `build_features()` directly with
`pending` populated by hand) and the on-screen rendering of the arrow
symbology and labels were not exercised — synthesizing realistic `QMouseEvent`
sequences and comparing rendered pixels was judged lower value than the
correctness work above, given the time available. Load this plugin in an
interactive QGIS session and try each tool before relying on it for real
survey/engineering work.

## Reproducing this

```
"C:\Program Files\QGIS 3.44.13\bin\python-qgis-ltr.bat" your_script.py
```

sets up `PYTHONPATH`/`PATH`/`QT_QPA_PLATFORM` the way QGIS's own Python
console does. Add `os.environ["QT_QPA_PLATFORM"] = "offscreen"` before any
`qgis.gui` import to construct real widgets (QgsMapCanvas, dialogs, map
tools) without a display.
