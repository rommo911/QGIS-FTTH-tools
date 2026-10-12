# 04 – Importing data (shapefile, KML, Excel, DXF)

[← Back to the guide](README.md)

Someone sends you data: a contractor's shapefile, a Google Earth KML, an Excel
sheet of buildings, an AutoCAD drawing. This page shows how to get it **into
the GeoPackage**, without leaving extra files in the project folder.

First decide which case you have:

| The data is… | Do |
|---|---|
| more of what we already have (buildings, poles, cables…) | **[A. Add into an existing table](#a-add-into-an-existing-table)** (most common) |
| a new kind of reference data (roads, parcels, a municipality layer) | **[B. Import as a new table](#b-import-as-a-new-table)** |

**Before you start:** put the received file in a folder **outside** the project
folder, e.g. `Desktop\incoming\`. Make a [backup](06-problems-and-fixes.md#backup-and-restore).

---

## Step 0: open the received file

| File | Click |
|---|---|
| shapefile `.shp`, KML/KMZ, GeoJSON, GeoPackage | drag it from Windows Explorer onto the QGIS map. Or **Layer → Add Layer → Add Vector Layer…** → **Vector Dataset(s): …** → pick the file → **Add**. |
| AutoCAD `.dxf` | same as above. QGIS asks which part to add: pick *points* or *lines*. A DXF has no coordinate system: when asked, choose the one the sender used (ask them). |
| Excel / CSV with coordinates | see [Excel and CSV](#excel-and-csv) below |

It appears as a new layer at the top of the Layers panel. It is only a
**viewer** of the received file. You will remove it at the end.

Check it lands in the right place on the map. If it appears far away (in
Africa, or the sea), its coordinate system is wrong. Ask the sender which one
they used.

### Excel and CSV

1. In Excel: **File → Save As →** type **CSV UTF-8 (Comma delimited) (\*.csv)**.
   (Plain *CSV* breaks Arabic text.)
2. In QGIS: **Layer → Add Layer → Add Delimited Text Layer…**
3. **File name:** the `.csv`. **Encoding:** `UTF-8`.
4. **Geometry Definition:** *Point coordinates*.
   **X field:** the longitude / easting column. **Y field:** the latitude /
   northing column.
5. **Geometry CRS:** for phone/GPS coordinates (like `36.63`, `35.93`) choose
   `EPSG:4326 - WGS 84`. For metre coordinates, ask the sender.
6. **Add**.

---

## A. Add into an existing table

Example: a contractor sends `new_buildings.shp`, 37 new building entrances in
block 01.

### 1. Make the column names match (only if they differ)

QGIS copies a value only when the column name is **exactly** the same as ours.
Open both attribute tables and compare. If the received file says `Floors_No`
and ours says `floors`, fix the names first:

1. **Processing → Toolbox** (`Ctrl+Alt+T`) → search **Refactor fields** →
   double-click it.
2. **Input layer:** the received layer.
3. Click **Load fields from template layer** → choose our block's site layer →
   **Load fields**. Now the list shows *our* columns.
4. For each of our columns, in **Source Expression**, pick the received column
   that holds that value (`floors` ← `Floors_No`). Leave it empty if they have
   no such column.
5. **Refactored:** leave as *Create temporary layer* → **Run**.
6. A layer called *Refactored* appears. Use it instead of the received layer in
   the next step.

### 2. Copy and paste

1. Click the received (or *Refactored*) layer.
   **Edit → Select → Select All Features** (`Ctrl+A`).
2. **Edit → Copy Features** (`Ctrl+C`).
3. Click **our** layer for that block (`قطاع الثورة → 01 → المواقع`).
   **Layer → Toggle Editing**.
4. **Edit → Paste Features** (`Ctrl+V`).

QGIS converts the coordinates automatically. The pasted features are now
selected (yellow).

> Use **Paste Features**, not *Paste Features as → Temporary Scratch Layer*.
> Scratch layers are lost when QGIS closes.

### 3. Fill the block and ID columns

The pasted features don't have our `block_id` yet, so they will disappear
after saving unless you fill it now. Keep them selected:

1. **Right-click our layer → Open Attribute Table**. At the bottom-left, choose
   **Show Selected Features**.
2. Use the bar at the top of the table (column, value, **Update Selected**) for
   each of these:

   | Column | Value |
   |---|---|
   | `sector_code` | `'THW'` |
   | `block_id` | `'THW-B01'` |
   | `block_no` | `1` |
   | `type_raw` | `'مداخل الأبنية'` (exactly as in our existing features) |
   | `type_code` | `'building_entrance'` |

3. Give them new IDs. Find the highest `site_id` in the block
   ([how](02-editing-features.md#what-to-type-in-the-form)), e.g.
   `THW-B01-SITE-0417`. Then column `site_id`, value:
   ```
   'THW-B01-SITE-' || lpad(to_string(417 + @row_number), 4, '0')
   ```
   → **Update Selected**. The 37 buildings get `…-0418` to `…-0454`.
   Change `THW-B01` and `417` to your block and your highest number.
4. **Layer → Save Layer Edits**.

If you are not sure what kind a feature is, leave `type_raw` and `type_code`
empty and tell the project owner. Don't guess.

### 4. Clean up

**Right-click** the received layer (and *Refactored*) → **Remove Layer…**.
Delete the file from `Desktop\incoming\` when you're done. Nothing was added to
the project folder.

For cables, also [fill the length](02-editing-features.md#fill-the-cable-length).

---

## B. Import as a new table

Example: the municipality sends `roads.shp` to use as a background layer.

1. Open it ([Step 0](#step-0-open-the-received-file)).
2. **Right-click it → Export → Save Features As…**
3. **Format:** `GeoPackage`.
4. **File name:** click **…** and choose the project's **existing** `.gpkg`.
5. **Layer name:** English, lowercase, no spaces, starting with `ref_` for
   reference data: `ref_roads`.
6. **CRS:** the project CRS (shown at the bottom-right of QGIS, e.g. `EPSG:32637`).
7. Tick **Add saved file to map** → **OK**.
8. QGIS says the file already exists. Click **Add new layer**.

   > ⚠️ **Never click Overwrite file.** It erases the whole GeoPackage.

9. Remove the original received layer (right-click → **Remove Layer…**).
10. Rename the new layer to an Arabic display name (`F2`), drag it into place,
    **Project → Save**.

Don't drag a layer onto the `.gpkg` in the Browser panel. It works, but it
names the table after the layer, and that name may be Arabic. Table names must
be English.
