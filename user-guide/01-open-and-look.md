# 01 – Open the project and look around

[← Back to the guide](README.md)

## Open the project

1. **Project → Open…** (`Ctrl+O`)
2. Pick the `.qgz` file in the project folder → **Open**.

The map opens with the same groups, colours and labels as before.

> If a window called **Handle Unavailable Layers** appears, click
> **Keep Unavailable Layers**. Never click *Remove*. Then see
> [06 – Problems and fixes](06-problems-and-fixes.md#a-layer-has-a-red-warning-sign).

## Show the two panels you need

- **View → Panels → Layers**: the list of layers on the left.
- **View → Panels → Browser**: a file explorer inside QGIS.

## See everything inside the GeoPackage

1. In the **Browser** panel, open **Project Home** (the folder of the open
   project).
2. Click the small arrow next to the `.gpkg` file. Every table inside it is
   listed: `site`, `cable`, `block_line`, `v_boq_cable` …
3. **Double-click** a table to add it to the map, or drag it onto the map.

The tables starting with `v_` are reports. They have no shape on the map. Open
them with **right-click → Open Attribute Table**.

Example: to see total cable length by type, double-click `v_boq_cable` in the
Browser, then in the Layers panel **right-click `v_boq_cable` → Open Attribute
Table**.

## Find out what a layer really shows

**Right-click the layer → Properties… → Source** tab.

- **Settings → Data source** shows the file and table, e.g.
  `idlib_ftth.gpkg|layername=site`.
- **Provider Feature Filter** (at the bottom) shows the filter, e.g.
  `"block_id" = 'THW-B01'`. This is the block this layer shows.

Faster: **right-click the layer → Filter…** shows the same filter.

## Look at one feature

1. **View → Identify Features** (`Ctrl+Shift+I`), or the **i** icon on the toolbar.
2. Click a point or line on the map.
3. The **Identify Results** panel lists all its values.

## Look at all features of a layer

**Right-click the layer → Open Attribute Table** (`F6`). It works like an Excel
sheet: click a column header to sort, and double-click a row number to zoom to
that feature.

## How the IDs read

Every feature has a printable ID that tells you where it is:

```
THW-B01-SITE-0042
 │   │   │    └── number in that block
 │   │   └─────── kind: SITE (point), CABL (cable), CNT (cable count)
 │   └─────────── block 01
 └─────────────── sector code (THW = قطاع الثورة)
```

A block's ID is the first two parts: `THW-B01`. That is the value of the
`block_id` column.
