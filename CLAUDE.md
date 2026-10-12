# QGIS-FTTH-tools

Scripts that migrate messy, GUI-built QGIS fibre-optic (FTTH) projects into a
clean, machine-readable GeoPackage. Owner: Rami Zayat, FTTH planning engineer.
Long-term goal: projects that scripts and AI can read, so templating, fibre-count
calculation and automated building tagging can be built on top.

**Keep this file current.** Update it in the same commit as any change to the
layout, the pipeline or the status below.

## The workflow

```
target/<project>/   the old project, dropped in AS RECEIVED   (git-ignored, never modified)
output/<project>/   the migrated, validated result             (git-ignored)
```

One command per project, reading `target/<project>`, writing only to
`output/<project>`: audit -> repair -> rename -> GeoPackage -> cutover -> validate
-> report. **That driver does not exist yet - it is the next task.**

## Layout

| Path | What |
|---|---|
| `scripts/` | the pipeline, in run order: `audit_workspace`, `repair_project_paths`, `rebuild_shx`, `validate_project`, `rename_to_ascii`, `build_geopackage`, `validate_gpkg` |
| `legacy/idlib_tools/` | the first project's in-place scripts. Newer in places than `scripts/` - see task 2. Delete once merged. |
| `config/templates/` | `naming`, `vocabulary`, `fibre_rules` JSON - filled per project. Carry the Idlib values as a worked example. |
| `docs/RUNBOOK.md` | the method, phase by phase. **Read before running anything.** |
| `docs/PITFALLS.md` | 16 traps that fail silently. Read before writing any XML/path code. |
| `docs/SCHEMA.md`, `DECISIONS.md`, `SURVEY_EXCHANGE.md` | target schema, the 8 design decisions, field-app round-trip contract |
| `user-guide/` | click-by-click QGIS guides for the people who edit a migrated project (Word-level users, not programmers): open, edit, layers, import, export, fixes. Keep them in step with the schema: table/column names, ID formats, the per-block layer filters. |

## Status

Every script was **verified by replay** on the Idlib project, but run *in place*
from the project folder (they take the workspace from the current directory or
`$WORKSPACE`). Not yet adapted to `target/` -> `output/`.

**Test fixture, local only:**
- `target/idlib/` - Idlib FTTH exactly as received: 828 files, 172 layers, Arabic
  filenames, 341 broken paths, one missing `.shx`.
- `output/idlib/` - the known-good result from the manual migration. Acceptance
  numbers: **172/172 layers valid, 24,107 features, 16,951 sites, 6,190 cables,
  312.615 km of cable, 0 hard failures.** `output/idlib/PROJECT_NOTES.md` is the
  full write-up of that project.
- Full git history of that work: `../idlib_ftth_history.bundle`
  (`git clone` it to inspect; commit `556006d` = as received).

## Next tasks, in order

1. **`scripts/migrate.py <name>`** - copy `target/<name>` to `output/<name>`,
   then run the pipeline there. Make every script take the workspace as an
   explicit argument. Never write to `target/`.
2. **Merge `legacy/idlib_tools/` into `scripts/`**, keeping the portable
   behaviour of `scripts/`. Missing from `scripts/`: the `block_line` table,
   `legacy_id` columns, the reconciliation baseline written to `project_meta`, the
   validator's fallback to that baseline when shapefiles are gone, and
   `cutover_to_gpkg.py`. The cutover hard-codes `TABLE_OF`/`TABLE_BY_ID`; move
   them into `naming.json`.
3. **Per-project config:** decide where a project's filled-in JSON lives. Suggest
   `projects/<name>/config/`, tracked in git.
4. **Acceptance:** `migrate.py idlib` must reproduce the `output/idlib` numbers
   above from `target/idlib`. Compare against the reference, don't overwrite it.
5. Then generalise to other old projects, which will have other languages,
   layer types and schemas. Every project-specific value goes in config, never in code.

## Standing rules

1. **Display text is never translated.** ASCII is for identifiers only (files,
   layer IDs, columns, codes). Legend names, labels and values stay in the
   original language. Tables carry `type_code` beside `type_ar`.
2. **Survey content is frozen.** Missing attributes, typos in values and
   undesigned sectors are *findings to report*, not to fix. Repairs to the
   *container* (paths, IDs, filenames, indexes) are in scope.
3. **Never guess a value.** Unknown stays NULL; a QA view reports it.
4. **Validate before deleting anything**, and report real numbers. Hard-fail
   only on defects the migration introduced; source quirks are warnings.

## Environment

- Windows. QGIS 4.2.1 at `C:\Program Files\QGIS 4.2.1`. Run PyQGIS/GDAL scripts with
  `"C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat"`; plain `python` (3.14) has neither.
- Set `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`, or printing Arabic crashes.
- Shell heredocs eat backslashes (`\b`, `\d`). Edit Python and JSON with the
  editor tools, not `cat <<EOF`.
- `جامعة حدود الكتلة 12.shx` at the repo root has a corrupt ACL. It can't be read
  or deleted without an elevated `takeown`. It is git-ignored; leave it.
