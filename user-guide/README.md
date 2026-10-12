# User guide: working with the GeoPackage project

This guide is for people who **draw and edit** the FTTH maps in QGIS.
You don't need to know programming or databases. If you can use Word and open
a QGIS project, you can follow it.

Written for QGIS 3.40 and 4.x. Menus are written like this:
**Layer → Add Layer → Add Vector Layer…** means: click the *Layer* menu at the
top, then *Add Layer*, then *Add Vector Layer…*.

---

## What changed: one file instead of hundreds

**Before:** every block had its own shapefiles. Each shapefile is really 4–8
files (`.shp .shx .dbf .prj .cpg .qmd …`). One project had **828 files**.

**Now:** all the data is in **one file**, the GeoPackage (`.gpkg`). The project
folder looks like this (the Idlib project as the example; your file names may
differ):

```
idlib_ftth.qgz      ← the project (map, groups, colours, labels)
idlib_ftth.gpkg     ← ALL the data: every point, line, block and table
```

Inside the GeoPackage are **tables**. Each table holds one kind of thing for
the **whole project**, for every sector and block:

| Table | Holds |
|---|---|
| `site` | every point: building entrances, poles, manholes, boxes… |
| `cable` | every cable line |
| `cable_count` | the cable-count labels |
| `block_line` | block boundaries (as drawn) |
| `block` | block boundaries as areas, with their size |
| `cabinet`, `feeder_main` | cabinets and the main feeder |
| `v_boq_…`, `v_qa_…` | **ready-made reports** (bill of quantities, checks). Read only. |

## The most important idea: a layer is a *window* on a table

In the **Layers** panel you still see the same groups and layers as before:

```
قطاع الثورة                      (group: sector)
 └── 01                          (group: block)
      ├── المواقع                → table "site",  filter: block_id = 'THW-B01'
      ├── الكبلات                → table "cable", filter: block_id = 'THW-B01'
      └── حدود الكتلة            → table "block_line", filter: block_id = 'THW-B01'
```

Each layer is **not a separate file any more**. It is a filtered view of one
shared table. The filter (`block_id = 'THW-B01'`) decides which features this
layer shows.

Two things follow from this. Remember them and you will avoid most problems:

1. **A new feature must carry the right `block_id`**, or it disappears from the
   layer after saving (it is saved, but in "no block"). See
   [02 – Editing features](02-editing-features.md).
2. **Adding a column to one layer adds it to every layer of that table.**
   All site layers share the `site` table.

---

## The 6 golden rules

1. **Never save new data as a shapefile or a temporary layer.** New data goes
   *into the GeoPackage*. Shapefiles are only for sending to other people.
2. **Never click "Overwrite file"** when saving into the `.gpkg`. It erases
   the whole GeoPackage, every block. Always choose **Add new layer** or
   **Append**.
3. **Only one person edits the GeoPackage at a time.** Others can look, but
   not edit, while someone is editing.
4. **Close QGIS, then make a backup copy** of the `.gpkg` before any big job.
   It is one file, so this takes seconds. See [06 – Problems and fixes](06-problems-and-fixes.md#backup-and-restore).
5. **Arabic names stay Arabic.** Layer names, labels and values are written in
   Arabic as always. Only *column names* and *codes* are English
   (`block_id`, `site_id`). Don't translate anything.
6. **Don't guess.** If you don't know a value (floors, apartments…), leave it
   empty. Empty means "not surveyed yet". A `0` means "surveyed, and the answer
   is zero", which is a different fact.

---

## I want to… (find your task)

| I want to… | Go to |
|---|---|
| open the project and see what is inside the GeoPackage | [01 – Open and look around](01-open-and-look.md) |
| add a building, pole, manhole or cable | [02 – Editing features](02-editing-features.md#add-a-point) |
| move, reshape or delete a feature | [02 – Editing features](02-editing-features.md#move-or-reshape) |
| change attribute values (floors, apartments, names) | [02 – Editing features](02-editing-features.md#change-attribute-values) |
| change many values at once | [02 – Editing features](02-editing-features.md#change-many-values-at-once) |
| add a layer for a **new block** | [03 – Layers and groups](03-layers-and-groups.md#add-a-layer-for-a-new-block) |
| rename, group or reorder layers | [03 – Layers and groups](03-layers-and-groups.md#rename-group-reorder) |
| remove a layer | [03 – Layers and groups](03-layers-and-groups.md#remove-a-layer) |
| add a new column | [03 – Layers and groups](03-layers-and-groups.md#add-a-column) |
| create a completely new kind of layer | [03 – Layers and groups](03-layers-and-groups.md#create-a-new-table) |
| save a layer's colours and labels | [03 – Layers and groups](03-layers-and-groups.md#save-the-style) |
| bring in a shapefile / KML / Excel / DXF from someone | [04 – Importing data](04-importing.md) |
| send data to a contractor (shapefile, KML, Excel, DXF) | [05 – Exporting data](05-exporting.md) |
| get cable lengths and counts (bill of quantities) | [05 – Exporting data](05-exporting.md#bill-of-quantities-to-excel) |
| fix something that went wrong | [06 – Problems and fixes](06-problems-and-fixes.md) |

## Words used in this guide

| Word | Meaning |
|---|---|
| **GeoPackage** / `.gpkg` | the one file that holds all the data |
| **table** | one "sheet" inside the GeoPackage, like a sheet in an Excel file |
| **layer** | what you see in the Layers panel: a view of a table, often filtered to one block |
| **feature** | one thing on the map: one point, one line, one area |
| **attribute** | a value of a feature: floors, apartments, cable type… |
| **edit mode** | the pencil is on; you can change the layer. Turn it off to stop. |
