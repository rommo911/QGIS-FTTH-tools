# Pitfalls

Every one of these was hit on the reference project. Most fail **silently** —
no error, no warning, just a wrong answer or an empty layer. Each entry says how
to detect it and what to do.

---

## 1. Paths live in two places

`<datasource>` elements **and** `source="..."` attributes on `<layer-tree-layer>`
both carry the path. On the reference project that was 173 of each, 341
references in total. Rewrite only one and the project is half-broken in a way
that looks fine until QGIS reloads the tree.

**Detect:** the audit's PATHS section counts both.
**Fix:** `repair_project_paths.py` handles both.

## 2. "Absolute paths" often aren't

The obvious diagnosis is wrong more often than not. On the reference project
`Paths/Absolute` was already `false`; the paths were *stale relative* ones —
`../../Documents/x.shp` — pointing at where the data sat on the author's
machine. Exactly one genuine absolute path existed, hidden in
`<ProjectGpsSettings>`.

**Detect:** the audit lists prefixes with counts and marks absolutes separately.
**Fix:** discover, don't assume — resolve each basename against the workspace.

## 3. Unicode NFD vs NFC filenames

The nastiest one. A filename can be stored **decomposed** (`ا` + U+0655) in the
project while Windows stores it **composed** (U+0625). The two render
identically, compare unequal byte-for-byte, and the layer fails to load with no
visible cause. Invisible in the GUI, invisible in a text diff.

**Detect:** the audit's NFD check.
**Fix:** normalise to NFC. **Prevent:** rename to ASCII (Phase 2).

Also true of your own tooling: when comparing a filename you typed against one
from disk, normalise both first.

## 4. Layer IDs are derived from names, with non-ASCII stripped

QGIS builds a layer ID from the layer *name*. Non-ASCII characters are removed,
so Arabic names collapse to `_______224320d5_2763_45f2_…`. Combined with names
duplicated 29 times, **nothing can address a layer** except its file path.

**Detect:** the audit's ADDRESSABILITY section.
**Fix:** rewrite the IDs (Phase 2). This is the single highest-value change.

## 5. A layer ID appears in six or seven places

`<maplayer><id>`, `layer-tree-layer`, `layerorder`, `snapping-settings`, the
legacy `<legend>` block, `ProjectGpsSettings`, and widget configs.

**Fix:** replace every old ID document-wide in **one** regex pass with an
alternation, never a loop of `str.replace` — a sequential loop can re-match an
ID it has already written.

## 6. A shapefile's internal layer name follows its filename

Rename `x.shp` to `y.shp` and any `|layername=x` left in the datasource stops
the layer opening. This bites *after* an otherwise perfect rename, so it looks
like the rename broke something.

**Detect:** validate after renaming; the layer reports invalid with a source
that looks correct.
**Fix:** rewrite `layername=` to the new stem for `.shp` sources. KMZ and other
multi-layer containers genuinely need theirs — leave those alone.

## 7. `.shx` referenced instead of `.shp`

Easy to do by mis-clicking in a file dialog. The layer may even load, but the
reference is fragile and the `.shp` shows up as an orphan.

**Detect:** the audit lists them.
**Fix:** point at the `.shp`.

## 8. A corrupt ACL can make a file unreadable, unmovable and undeletable

If a file's owner SID no longer resolves, you cannot read it, move it, delete
it, or even read its ACL — and git cannot index it. `Move-Item` and `del` both
fail with *Access denied*.

**Fix:** if it is a `.shx`, rebuild it — it is derived data with no unique
content (`rebuild_shx.py`). Otherwise it needs an elevated shell:

```bash
takeown /f "name.shx" && icacls "name.shx" /grant "%USERNAME%:F"
```

Meanwhile add it to `.gitignore` with a comment so the baseline commit can
proceed. A later ASCII rename orphans it anyway.

## 9. Field-name typos fail silently

`buildungs`, `byildings`, `building n`, `buildings ` (trailing space),
`foolrs num`, `apatments`, `box2` vs `box 2`, `Type` vs `type`. A script reading
the majority spelling gets **NULL** on the others — no exception, no warning,
just a quietly wrong total.

**Detect:** the audit's near-duplicate check uses edit distance, so it catches a
moved letter (`floors`/`foolrs`) that a single-substitution test misses. It
deliberately ignores names differing only in a trailing digit, because `box 1` /
`box 2` are legitimately different fields.
**Fix:** map every spelling to one canonical column in `field_aliases`.

## 10. Value typos split your counts

On the reference project, aerial cable was recorded as both `الكبلات الهوائية`
(117.3 km) and `هوائي` (2.6 km). Any naive total was wrong by 2.6 km. Across all
types, **8.6 km** was hiding under second spellings.

**Detect:** the audit's vocabulary section flags near-duplicates with counts.
**Fix:** map raw → code, keep the raw value verbatim in `type_raw`. Never
rewrite the recorded string: that edits survey content and destroys the evidence.

## 11. Boundaries drawn as open lines

Block and area boundaries are often LineStrings that never close. All 56 on the
reference project were open — so no site could be assigned to a block by
geometry, and there was no area to compute.

The gaps were tiny: median **0.08 m**, max 2.53 m. That is a drawing slip, not
design intent, and closing on a tolerance is correct. Redrawing 56 boundaries by
hand is not.

**Detect:** the audit's RING CANDIDATES section isolates layers whose lines
almost close (gap under 1% of perimeter), so boundaries are not buried among
thousands of cables.

## 12. Closing a ring can produce an invalid polygon

19 of the 56 pinched at a point, making the ring self-touching and the polygon
invalid. `MakeValid()` resolved every one into a MultiPolygon with a **0.00%
area change** — verify that before accepting it, then record that a repair
happened. Declare the layer as MultiPolygon, not Polygon.

## 13. SQLite integer division floors before you can round

`apartments / 8` with both operands integers gives `14 / 8 = 1`, not 1.75, so a
ceiling applied afterwards is meaningless. This silently under-reports demand.

**Fix:** cast the **input column** to REAL, not the finished expression:
`CAST(apartments AS REAL) / 8`.

## 14. Don't validate a value against the wrong domain

`cores_recorded` on the reference project holds 1–6: a per-building fibre
demand. Checking it against orderable *cable* sizes (2, 4, 8, 12, 24…) flagged
4,159 rows as errors. They were not errors; the check was.

**Rule:** before writing a QA check, look at the actual distribution of the
column.

## 15. Distinguish source defects from migration defects

A validation gate that hard-fails on a 0.44 m cable stub that exists in the
source data is unusable — the build can never pass. Hard-fail only on things the
*migration* could have broken: count mismatches, duplicate IDs, orphans,
geometry the migration produced. Everything pre-existing is a **finding**.

## 16. Basemaps and console encoding

- XYZ basemaps (Google tiles and similar) render blank offline and headless, and
  their terms often do not fit commercial redistribution. Note it; do not assume
  the map output is fine because it looks fine on your screen.
- Windows Python defaults to a cp1252 console and raises `UnicodeEncodeError` on
  Arabic. Set `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` before any script that
  prints non-ASCII.
- `\b`, `\d`, `\n` inside a shell heredoc that reaches Python get eaten. Writing
  files through a heredoc corrupted a documented path (`\bin` → backspace) and a
  regex on this project. Use a file-editing tool, or `chr(92)`, for anything
  containing backslashes.
