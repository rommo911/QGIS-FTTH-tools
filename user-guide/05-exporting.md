# 05 – Exporting data (for contractors, Google Earth, Excel, AutoCAD)

[← Back to the guide](README.md)

An export is a **copy for someone else**. The GeoPackage stays the master.

- Save exports in a folder **outside** the project folder, e.g.
  `Desktop\exports\2026-10-12_THW-B01\`.
- Never edit an export and copy it back over the project. If the contractor
  returns changes, bring them in with [04 – Importing](04-importing.md).

---

## Export one layer

Example: send block 01's cables to a contractor as a shapefile.

1. **Right-click the layer** (`قطاع الثورة → 01 → الكبلات`) →
   **Export → Save Features As…**
2. **Format:** pick one from the table below.
3. **File name:** click **…** → go to your exports folder → type a name,
   e.g. `THW-B01_cables`.
4. **CRS:** leave the project CRS, unless the receiver asks for another one.
5. **Encoding** (if shown): `UTF-8`, so Arabic text survives.
6. Only some features? Select them on the map first, then tick
   **Save only selected features**.
7. **Untick** **Add saved file to map**. You don't need it in the project.
8. **OK**.

| They want… | Format |
|---|---|
| shapefile (most GIS software) | `ESRI Shapefile` |
| Google Earth | `Keyhole Markup Language [KML]` (coordinates are converted for Google Earth automatically) |
| Excel | `MS Office Open XML spreadsheet [XLSX]` |
| AutoCAD | `AutoCAD DXF` |
| one modern GIS file | `GeoPackage`, saved as a **new** file in the exports folder |

The block layers already contain only their own block, so exporting
`… → 01 → الكبلات` gives only block 01.

---

## Export many layers in one file

Example: send all of قطاع الثورة in one file.

1. **Processing → Toolbox** (`Ctrl+Alt+T`) → search **Package layers** →
   double-click.
2. **Input layers:** click **…** → tick the layers to send → **OK**.
3. **Destination GeoPackage:** **…** → **Save to File…** → your exports folder
   → name it `THW_2026-10-12.gpkg`.
4. Tick **Save layer styles into GeoPackage** so they get your colours.
5. **Run**.

The receiver opens that single `.gpkg` file in QGIS. Send this file only,
never the project's own `.gpkg`.

---

## Bill of quantities to Excel

The GeoPackage already contains ready-made reports. They update by themselves
whenever the data changes.

| Report | Shows |
|---|---|
| `v_boq_cable` | total cable length and number of segments, by cable type |
| `v_boq_cable_by_block` | the same, for each block |
| `v_boq_site` | how many of each site type (poles, manholes…) |
| `v_demand` | buildings, apartments and occupants per block |
| `v_qa_coverage` | how complete the survey is in each block, worst first |

To get one into Excel:

1. **Browser panel → Project Home →** the `.gpkg` → double-click `v_boq_cable`.
2. **Right-click `v_boq_cable`** in the Layers panel → **Export → Save Features As…**
3. **Format:** `MS Office Open XML spreadsheet [XLSX]` → file name in your
   exports folder → untick **Add saved file to map** → **OK**.
4. Open the `.xlsx` in Excel.

Lengths are in metres, measured flat on the map. They don't include slack,
coils or vertical runs up buildings.

When you're done, remove the report from the Layers panel
(right-click → **Remove Layer…**) if you don't want it in the project.
