# Dimension Tool (QGIS plugin)

CAD/ArcGIS-Pro-style dimension lines for QGIS: Linear, Aligned, Angular,
Radius, Diameter, and Leader dimensions, drawn interactively and stored as a
real GeoPackage layer.

## What it does

**Dimension → New Dimension Layer…** opens a dialog to create a GeoPackage
with:

- a coordinate system (the project/map CRS, an existing layer's CRS, or any
  CRS via the ordinary QGIS projection browser)
- default color, line width, arrow size, label text height, unit
  (Meters/Kilometers/Feet/US Survey Feet/Yards/Miles/Nautical Miles), and
  decimal precision

The new layer comes pre-styled with a rule-based renderer (a native QGIS
double- or single-headed arrow symbol for the measured line, a thin plain
symbol for extension lines/rays) and a label expression — every bit of that
stays fully editable afterwards through the ordinary **Layer Properties**
panel, like any other vector layer. Nothing about the styling is baked in or
plugin-controlled after creation.

The **Dimension** toolbar then has one tool per type:

| Tool | Clicks | Measures |
| --- | --- | --- |
| Linear | 2 points, then place the dimension line | Only the horizontal *or* vertical component between the two points (whichever is larger) — like AutoCAD's `DIMLINEAR` |
| Aligned | 2 points, then place the dimension line | The true straight-line distance between the two points |
| Angular | first ray, vertex, second ray | The angle at the vertex, drawn as an arc |
| Radius | center, then a point on the edge | Distance from center to edge, labeled `R …` |
| Diameter | center, then a point on the edge | Twice that distance, drawn through the center, labeled `⌀ …` |
| Leader | the point to annotate, then where the label sits | Prompts for free text; no measurement |

A **Snap** toggle on the toolbar controls whether clicks snap to nearby
features — through QGIS's own Snapping Options, not a separate
reimplementation, so it respects whatever the project is already configured
to snap to. Escape or a right click cancels a dimension in progress.

## Installing

Copy (or symlink) `dimension_tool/` into your QGIS profile's plugin folder —
on Windows, typically:

```
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\dimension_tool
```

then enable **Dimension Tool** in QGIS's **Plugins → Manage and Install
Plugins**.

## Project layout

```
dimension_tool/
  metadata.txt          plugin manifest QGIS reads
  __init__.py            classFactory() entry point
  units.py                length-unit conversion (no qgis import; plain pytest)
  dimension_geometry.py   pure 2D vector/arc math (no qgis import; plain pytest)
  measurement.py          CRS-aware length measurement (planar vs geodesic)
  dimension_layer.py       GeoPackage schema, renderer, labeling
  dimension_features.py   builds the QgsFeatures for one dimension
  dimension_tools.py       the six interactive QgsMapTool subclasses
  dimension_dialog.py      the "New Dimension Layer" dialog
  dimension_plugin.py      toolbar/menu wiring, the shared controller
  icons/                   toolbar SVGs
tests/                    plain pytest for units.py / dimension_geometry.py
dev-notes/
  qgis-api-verification.md   what was checked against a real QGIS install, and why
```

`units.py` and `dimension_geometry.py` have no `qgis` import at all, so
`tests/` runs with plain `pytest` — no QGIS installation needed:

```
pip install pytest
pytest tests/
```

Everything else needs a real QGIS install to import `qgis.core`/`qgis.gui`.
See `dev-notes/qgis-api-verification.md` for how those modules were exercised
against QGIS 3.44 without a full interactive session, and what's *not* yet
covered that way (real mouse-event dispatch, on-screen rendering).

## Design notes

- **Why a GeoPackage, not a memory layer**: dimensions should persist,
  survive closing QGIS, and be shareable, the way any other vector layer's
  data is expected to.
- **Why native QGIS arrow symbols, not custom geometry**: `QgsArrowSymbolLayer`
  already draws a correct, scale-independent double- or single-headed arrow
  along a line; hand-building arrowhead polygons (as some web-based
  equivalents do) would be reinventing something QGIS already does natively,
  and would fight the Layer Properties panel instead of being editable
  through it.
- **Why Linear and Aligned are different tools, not one tool with a mode
  flag**: they measure genuinely different things (axis-constrained vs. true
  distance), matching the same distinction AutoCAD's `DIMLINEAR` /
  `DIMALIGNED` make.
- **Why offsets are computed in canvas-pixel space**: a dimension line's
  offset from the points it measures should look the same number of pixels
  away regardless of zoom level. Computing it in map (ground) units would
  make it enormous at low zoom and invisible at high zoom.
