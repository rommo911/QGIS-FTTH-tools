# 06 – Problems and fixes

[← Back to the guide](README.md)

## Backup and restore

The data is one file, so a backup is one copy. Do it **before** any big job:
importing, deleting many features, adding columns, new tables.

**Make a backup**
1. **Close QGIS** completely. (While QGIS is open, the latest changes may still
   be in the `-wal` file next to the `.gpkg`. Closing QGIS writes them in.)
2. In Windows Explorer, copy the `.gpkg` and the `.qgz`.
3. Paste them into a backup folder **outside** the project folder, e.g.
   `D:\FTTH_backup\`.
4. Add the date to the names: `idlib_ftth_2026-10-12.gpkg`.

**Restore a backup**
1. Close QGIS.
2. Copy the backup into the project folder, replacing the current file.
3. Rename it back to the **exact** original name (`idlib_ftth.gpkg`), or the
   project can't find it.

---

## A feature disappeared after I saved it

Its `block_id` doesn't match the layer's filter (empty, or a typo). It is saved,
just not shown in this block.

1. **Browser panel → Project Home →** the `.gpkg` → double-click the table
   (`site` or `cable`). This adds the **whole** table, with no filter.
2. Open its attribute table (`F6`). Click the `block_id` header to sort. Empty
   values come first.
3. Find your feature, turn on the pencil, fix `block_id` (and `sector_code`,
   `block_no`), **Save Edits**.
4. Remove that unfiltered layer (right-click → **Remove Layer…**).

## A feature is saved but I can't see it (no symbol)

Its `type_raw` doesn't exactly match the spelling the colours use: a different
letter, an extra space, or empty. Open the attribute table, compare with a
neighbour of the same kind, and copy the neighbour's exact value
([how](02-editing-features.md#what-to-type-in-the-form)).

## A layer has a red warning sign

The project can't find the GeoPackage. Usually the `.gpkg` was renamed, or
moved away from the `.qgz`.

- Put the `.gpkg` back in the same folder as the `.qgz`, with its original
  name, and reopen the project.
- Or: **right-click the layer → Change Data Source…** → choose the `.gpkg` and
  the right table → **OK**. Check the filter is still there (right-click →
  **Filter…**), then **Project → Save**.

Always keep the `.qgz` and the `.gpkg` together, in the same folder, with
their names unchanged.

## "Database is locked" / can't save

Someone else, or another QGIS window, is editing the same GeoPackage.

- Close any other QGIS window that has the project open.
- Ask colleagues to stop editing (**Layer → Toggle Editing → Save**).
- Don't open the `.gpkg` in other programs while editing.

Only **one person edits at a time**.

## There are `.gpkg-wal` and `.gpkg-shm` files next to the GeoPackage

That's normal while QGIS has the file open. **Don't delete them.** They go away
when QGIS closes. Don't copy or move the `.gpkg` while they exist.

## The colours and labels are gone

- If you haven't saved the project: **Project → Close → Discard**, then open the
  project again. Everything comes back.
- If you have: **right-click the layer → Properties… → Style → Load Style… →
  From Database**, if a style was saved there. Otherwise copy the style from
  another block's layer: right-click that layer → **Styles → Copy Style**, then
  right-click the broken layer → **Styles → Paste Style**.

## A line or area looks broken (invalid geometry)

1. **Vector → Geometry Tools → Check Validity…**
2. **Input layer:** the layer → **Run**.
3. A layer called *Invalid output* appears and lists each problem and where it
   is. Zoom to them and fix them with **Edit → Vertex Tool**.
4. Remove the *Invalid output* layer when done (it is temporary, not a file).

Don't use the *Fix Geometries* tool: it makes a new layer instead of fixing
ours.

## Arabic text shows as `????` or strange letters in an export

- Shapefile or CSV: export again with **Encoding: UTF-8**.
- In Excel: export as **XLSX** instead of CSV. If you must use CSV, open it in
  Excel with **Data → From Text/CSV** and choose **65001: Unicode (UTF-8)**.

## The `.gpkg` file got big after deleting a lot

**Browser panel →** right-click the `.gpkg` → **Compact Database (VACUUM)**.
Nobody else may have it open while you do this.

## I saved a mistake

There is no undo after saving. **Stop editing** and restore the last
[backup](#backup-and-restore). If you have no backup, don't keep working on
it: tell the project owner what you did and when.

## I clicked "Overwrite"

Don't save anything. Close QGIS and **don't save the project**. Restore the
last backup, then tell the project owner.

---

## Ask the project owner before you…

- delete a table, or rename or delete a column
- change a `site_id`, `cable_id` or any other ID
- move a feature into another block
- add a new sector or a new kind of site or cable (new `type_code`)
- change a block boundary
- edit anything in `vocab`, `vocab_map`, `sector`, `project_meta`, or the
  `survey_…` tables
- run any tool that isn't in this guide on the project's `.gpkg`
