# 03 – Layers, groups, columns and new tables

[← Back to the guide](README.md)

Remember: a layer is a **window** on a table, usually filtered to one block.
Making a new layer does **not** need a new file.

After any change in the Layers panel, save the project: **Project → Save**
(`Ctrl+S`). Use *Save*, not *Save As…*. *Save As* makes a second project file,
and soon nobody knows which one is current.

---

## Add a layer for a new block

Example: block 20 is added to قطاع الثورة. Its ID will be `THW-B20`.

You don't create anything new. You copy block 01's layers and point the copies
at block 20:

1. In the Layers panel, **right-click** the group `قطاع الثورة` →
   **Add Group** → name it `20`.
2. **Right-click** the layer `قطاع الثورة → 01 → المواقع` →
   **Duplicate Layer**. A copy appears next to it.
3. **Right-click the copy → Filter…**
4. In the box at the bottom, change `'THW-B01'` to `'THW-B20'`:
   ```
   "block_id" = 'THW-B20'
   ```
   Click **Test** (it may say 0 rows if block 20 is still empty; that's fine)
   → **OK**.
5. **Right-click the copy → Rename Layer** (`F2`) → give it the same Arabic name
   as the original (`المواقع`).
6. Drag the copy into the group `20`.
7. Repeat steps 2–6 for the other layers of the block (`الكبلات`,
   `حدود الكتلة`, `عدد الكبلات` …).
8. **Project → Save**.

The copies keep the colours and labels of block 01. Now draw the new block's
features in these layers with `block_id` = `THW-B20`
([how](02-editing-features.md#add-a-point)).

> **Filter…** is greyed out while the layer is in edit mode. Stop editing first.

---

## Rename, group, reorder

| To… | Click |
|---|---|
| rename a layer (display name) | right-click → **Rename Layer** (`F2`). Arabic is fine: it is only a display name. |
| make a group | right-click a group (or an empty area of the Layers panel) → **Add Group** |
| move a layer into a group | drag it onto the group |
| change drawing order | drag layers up or down. The top layer is drawn on top. |
| hide a layer | untick its box |

None of these touch the data. They are saved in the project with
**Project → Save**.

---

## Remove a layer

There are two very different "removes":

| | **Remove from the map** | **Delete the table** |
|---|---|---|
| where | Layers panel → right-click → **Remove Layer…** | Browser panel → `.gpkg` → right-click a table → **Delete Layer…** |
| what happens | the window closes. **The data stays** in the GeoPackage. | the table and **all its data, for every block**, are erased |
| undo | add it again from the Browser | only from a backup |
| when | a layer you don't need on this map | almost never. Ask the project owner first. |

**Never delete** `site`, `cable`, `cable_count`, `block`, `block_line`,
`cabinet`, `feeder_main`, `vocab`, `vocab_map`, `sector`, `project_meta`,
`survey_…` or any `v_…` table.

To delete the **features** of one block (not the table): open that block's
layer, select all with **Edit → Select → Select All Features** (`Ctrl+A`) in edit
mode, then **Edit → Delete Selected** and save. Check the layer's filter first
(right-click → Filter…), so you know which block you are deleting.

---

## Add a column

Example: you want to record pole height on the sites.

1. **Right-click the layer → Properties… → Fields** tab.
2. Click the **pencil** (Toggle Editing Mode) at the top of the tab.
3. Click **New Field** (`Ctrl+W`):
   - **Name:** English, lowercase, no spaces, words joined with `_`.
     Put the unit at the end: `pole_height_m`.
   - **Type:** *Whole number* (counts), *Decimal number* (lengths, heights),
     *Text* (names, notes).
   - **OK**.
4. Click the pencil again → **Save**.
5. Give it an Arabic display name: same window → **Attributes Form** tab →
   click `pole_height_m` in the list → **Alias:** `ارتفاع العمود` → **OK**.
6. **Project → Save**.

Good to know:
- The new column appears in **every layer of that table** (every block), and
  it is empty everywhere. Empty is correct: nothing has been measured yet.
- Don't delete or rename existing columns. Reports, the survey app and the
  checks read them by name. Ask the project owner.

---

## Create a new table

**Most of the time you don't need one.** New buildings, poles, manholes and
boxes go into `site`. New cables go into `cable`. A new block is a new
`block_id`, not a new table.

Make a new table only for a **new kind of thing** that has no table yet.
Example: planned trenches (lines).

1. **Layer → Create Layer → New GeoPackage Layer…**
2. **Database:** click **…** and choose the project's **existing** `.gpkg`
   file. Don't type a new file name.
3. **Table name:** English, lowercase, no spaces: `trench`.
4. **Geometry type:** *Point*, *Line* or *Polygon*.
5. **CRS:** choose the same one as the project (shown at the bottom-right of the
   QGIS window, e.g. `EPSG:32637`).
6. Under **New Field**, add at least `sector_code` (Text), `block_id` (Text),
   `block_no` (Whole number), then your own columns → **Add to Fields List**
   after each one.
7. **OK**.
8. QGIS says the file already exists. Click **Add New Layer**.

   > ⚠️ **Never click Overwrite.** It replaces the whole GeoPackage with an
   > empty one. Every block, every cable, gone.

9. The new layer appears in the Layers panel. Rename it to Arabic (`F2`), e.g.
   `الحفريات`, and drag it into the right group.
10. **Project → Save**.

---

## Save the style

Colours and labels are saved in the project with **Project → Save**. You don't
need to do anything else.

To also store a style **inside the GeoPackage**, so it comes back when someone
adds the table fresh from the Browser (useful for a new table):

1. **Right-click the layer → Properties…**
2. At the bottom-left, click **Style → Save Style…**
3. **Save style:** choose **In Database (GeoPackage)**.
4. Give it a name, tick **Use as default style for this layer** → **OK**.

To get it back: **Properties → Style → Load Style… → From Database**.

Don't save styles as `.qml` files into the project folder. That's more files.
