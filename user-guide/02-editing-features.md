# 02 – Editing features (points, lines, values)

[← Back to the guide](README.md)

Edits are written **straight into the GeoPackage**. No new files are created.

## Start and stop editing

| Do this | Click |
|---|---|
| start editing a layer | select the layer in the Layers panel → **Layer → Toggle Editing** (pencil icon) |
| save your work | **Layer → Save Layer Edits** |
| undo (only **before** saving) | **Edit → Undo** (`Ctrl+Z`) |
| stop editing | **Layer → Toggle Editing** again → **Save** or **Discard** |

Rules:
- **Edit one layer at a time.** Save it and stop editing before you start the
  next one.
- **Save often.** After saving there is no undo. A backup is your undo
  ([how](06-problems-and-fixes.md#backup-and-restore)).

---

## Add a point

Example: a new building entrance in block 01 of قطاع الثورة.

1. In the Layers panel, click the **site layer of that block**
   (`قطاع الثورة → 01 → المواقع`).
2. **Layer → Toggle Editing**.
3. **Edit → Add Point Feature** (`Ctrl+.`).
4. Click on the map where the point goes. A form opens.
5. Fill the form using the table below → **OK**.
6. **Layer → Save Layer Edits**.

### What to type in the form

| Column | What to put | Example |
|---|---|---|
| `site_id` | next free number in this block (see below) | `THW-B01-SITE-0418` |
| `sector_code` | the sector code | `THW` |
| `block_id` | **the block this layer shows. Must match the layer filter.** | `THW-B01` |
| `block_no` | the block number only | `1` |
| `type_raw` | the kind, **copied exactly** from a neighbour of the same kind | `مداخل الأبنية` |
| `type_code` | copied from the same neighbour | `building_entrance` |
| `building_ref`, `floors`, `apartments`, `occupants`, `clients`, `box_1`, … | only what you **know**. Unknown = leave empty. | `5` |
| everything else (`legacy_id`, `source_file`, `source_fid`, `data_source`, `survey_…`, `surveyed_…`, `rev`, `external_ref`) | **leave empty** | |

**Why `block_id` matters:** the layer only shows features whose `block_id`
matches its filter. A wrong or empty `block_id` saves the point, but it
**disappears from the map**.

**Why `type_raw` must be exact:** the colours and symbols are chosen by the
text in `type_raw`. One different letter or an extra space, and the point is
drawn with no symbol (invisible) or the wrong one.

**To copy a value exactly:** use **View → Identify Features**, click a
neighbour of the same kind, and in the *Identify Results* panel
**right-click the value → Copy Attribute Value**. Then paste it into the form
(`Ctrl+V`).

**To find the next free `site_id`:** open the layer's attribute table (`F6`)
and click the `site_id` column header twice to sort from highest to lowest. The
top row is the highest. Add 1. Keep the four digits: `0417` → `0418`.

> Never change or reuse an existing `site_id`. Field survey apps and reports
> find buildings by this ID.

---

## Add a line (cable)

1. Click the **cable layer of the block** (`… → 01 → الكبلات`).
2. **Layer → Toggle Editing**.
3. Turn on snapping so the cable ends sit exactly on poles and boxes:
   **Project → Snapping Options…** → click the magnet (**Enable Snapping**).
4. **Edit → Add Line Feature** (`Ctrl+.`).
5. **Left-click** each corner of the cable. **Right-click** to finish.
6. Fill the form: `cable_id` (next number, e.g. `THW-B01-CABL-0213`),
   `sector_code`, `block_id`, `block_no`, `type_raw` + `type_code` (copied from
   a neighbour cable of the same kind), `cores` if known.
7. **Layer → Save Layer Edits**.
8. Fill `length_m` (next section).

### Fill the cable length

The length is stored in the `length_m` column, so reports can add it up. QGIS
does **not** update it by itself. Do this after drawing or reshaping a cable:

1. **Right-click the cable layer → Open Attribute Table**.
2. Select the new or changed cables (click their row numbers; hold `Ctrl` for
   several).
3. Click the **Field Calculator** button (abacus icon, `Ctrl+I`).
4. Tick **Update existing field** → choose `length_m`.
5. Expression: `round(length($geometry), 3)`
6. Make sure **Only update N selected features** is ticked → **OK**.
7. **Layer → Save Layer Edits**.

Use exactly `length($geometry)` (not `$length`). It measures the same way as
the existing lengths.

---

## Move or reshape

| To… | Click |
|---|---|
| move a whole point or line | **Edit → Move Feature(s)**, click the feature, click the new place |
| move one corner of a line | **Edit → Vertex Tool**, drag the corner |
| add a corner | **Vertex Tool**, double-click on the line |
| delete a corner | **Vertex Tool**, click the corner, press `Delete` |

After reshaping a cable, [fill the length again](#fill-the-cable-length).

If a point must move **into another block**, don't change its IDs yourself.
Note the `site_id` and tell the project owner.

---

## Delete a feature

1. **Layer → Toggle Editing**.
2. **Edit → Select → Select Feature(s)**, click the feature (it turns yellow).
   Hold `Shift` to select more.
3. **Edit → Delete Selected** (`Delete` key).
4. **Layer → Save Layer Edits**.

This deletes it from the table for good. It does not "go back to a shapefile".

---

## Change attribute values

1. **Right-click the layer → Open Attribute Table** (`F6`).
2. Click the **pencil** at the top-left of the table to start editing.
3. Double-click a cell, type the new value, press `Enter`.
4. Click **Save Edits** (the disk icon in the table) → stop editing with the
   pencil.

Text in Arabic is typed as normal.

## Change many values at once

Example: the selected 12 buildings all have 4 floors.

1. Open the attribute table → pencil on.
2. Select the rows (click the row numbers; `Ctrl`+click or `Shift`+click for
   several).
3. In the bar at the top of the table:
   - left box: choose the column, e.g. `floors`
   - middle box: type the value, e.g. `4`
   - click **Update Selected** (not *Update All*).
4. **Save Edits**.

Text values go in single quotes: `'بناء 12'`. Numbers do not: `4`.
