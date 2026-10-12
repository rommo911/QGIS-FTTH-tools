# Runbook — messy QGIS workspace to machine-readable GeoPackage

Follow in order. Every phase ends in a commit, so any phase can be reverted
alone. Do not skip Phase 0.

All commands assume the QGIS interpreter, which is the only Python here with
PyQGIS and GDAL bound:

```bash
"C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" <script> [args]
```

Adjust the version. Plain `python` works for the scripts that do not import
GDAL — the audit degrades gracefully and says so.

---

## Choose your path

| Situation | Do this |
|---|---|
| **New project, never migrated** | The whole runbook, Phase 0 → 6. |
| **Updated version of a project already migrated** | Phase 0, then jump to *Re-running on an updated source* at the end. |
| **Same project, config change only** | Edit `config/*.json`, rebuild, revalidate. Phase 5 only. |

---

## Phase 0 — Baseline and audit

**Never edit anything before this is committed.**

```bash
git init
git config core.quotepath false      # readable non-ASCII filenames
git config core.autocrlf false       # do not mangle binary sidecars
```

Create `.gitattributes` so git never treats binary GIS files as text:

```
*.shp binary
*.shx binary
*.dbf binary
*.qgz binary
*.kmz binary
*.gpkg binary
*.qgs text eol=lf
*.prj text eol=lf
*.cpg text eol=lf
```

Then commit everything, untouched:

```bash
git add -A && git commit -m "Baseline: project exactly as received"
```

If a file refuses to be indexed with *Permission denied*, it has a corrupt ACL.
Add it to `.gitignore` with a comment saying why, commit the rest, and fix it in
Phase 1 — do not stall here.

Now audit:

```bash
"C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" scripts/audit_workspace.py . --json audit.json
```

Read the whole report before touching anything. It is the input to every
decision that follows.

---

## Phase 1 — Repair the container

The goal is a project that loads. Nothing here touches feature data.

```bash
python scripts/repair_project_paths.py --dry-run
python scripts/repair_project_paths.py
```

It discovers stale prefixes rather than being told them, and fixes absolute
paths, `.shx`-instead-of-`.shp` references and NFD filenames in the same pass.
It rewrites **both** `<datasource>` elements and `source="..."` attributes —
fixing only one leaves the project half-broken.

If any shapefile is missing or has an unreadable index:

```bash
"C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" scripts/rebuild_shx.py .
```

A `.shx` is a derived index and carries no unique data, so rebuilding it is
lossless. The script verifies feature count and geometry type before installing.

Verify, always:

```bash
"C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" scripts/validate_project.py
```

Do not proceed until this reports **0 invalid layers**. Commit.

---

## Phase 2 — Make layers addressable

This is the step that unlocks automation, and the reason is worth understanding:
QGIS derives a layer's ID from its **name** by stripping non-ASCII. A project
named in Arabic ends up with IDs like `_______224320d5_2763_45f2_…`. Layer names
are usually duplicated too. So neither ID nor name identifies a layer, and the
only unique key is the file path.

Write the naming config from the audit's group tree and filename list:

```bash
cp config/templates/naming.template.json config/naming.json
```

Order `layer_types` **most-specific first** — a "cable count" rule must precede
a "cables" rule, or every count layer is misclassified.

```bash
python scripts/rename_to_ascii.py --dry-run
```

It refuses to run on an ID collision or an unmatched layer, and tells you which.
Fix the config and repeat until clean, then run it for real, and validate again.

**Layer names stay in the original language.** The group tree already gives a
human the context that duplicate names lack; scripts use the new IDs.

Commit. `docs/layers.csv` is now the authoritative ID ↔ name ↔ sector ↔ type map.

---

## Phase 3 — Agree the decisions

Copy `docs/DECISIONS.md` into `docs/` and work through the eight
decisions with the project owner. They are genuinely decisions, not defaults —
but every one has a recommendation and a stated consequence, so this is usually
a short conversation.

Do not start Phase 4 with D3 (identifiers) or D4 (vocabulary) unresolved. Both
are expensive to change later.

---

## Phase 4 — Vocabulary and rules

```bash
cp config/templates/vocabulary.template.json config/vocabulary.json
cp config/templates/fibre_rules.template.json config/fibre_rules.json
```

Fill `vocabulary.json` from the audit's **VOCABULARY CANDIDATES** section, which
lists every distinct value with its count and flags near-duplicate spellings.
Three parts:

- `terms` — the canonical concepts: ASCII `code`, plus the label in the display
  language.
- `aliases` — every raw string found in the data, mapped to a code. Include the
  typos; that is the point. The raw value is still stored verbatim, so a wrong
  mapping is a config edit, not a data migration.
- `field_aliases` — every spelling of each field name across the source
  schemas, mapped to one canonical column.

**Derive engineering rules from the data rather than inventing them.** On the
reference project, `ceil(apartments / 8)` reproduced the recorded core count for
97.6% of buildings — that is a finding about how the design was actually done,
not a guess. Check candidate rules against recorded values and record the match
rate as evidence. Mark the rule unconfirmed until an engineer signs it off.

---

## Phase 5 — Build and validate the GeoPackage

Pilot one sector first (D1). It proves the loader against real data before the
rest moves.

```bash
"C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" scripts/build_geopackage.py --sector THW --dry-run
"C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" scripts/build_geopackage.py --sector THW
```

Then everything:

```bash
"C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" scripts/build_geopackage.py
"C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" scripts/validate_gpkg.py
```

The validator **reconciles against the source shapefiles** — feature counts and
total line length must match exactly, or the migration lost something. That is
the check that matters; everything else is a finding.

The GeoPackage is **regenerable — never hand-edit it.** Change the config or the
builder, rebuild, revalidate. Add it to `.gitignore` if it churns; track it if
you want reviewers to open the project without running a build.

Commit config, builder and docs together.

---

## Phase 6 — Document the workspace

Write `CLAUDE.md` at the workspace root so the next session starts informed.
Copy the structure from `config/templates/CLAUDE.template.md`. It must
state: what the project is, the domain model, the display-language rule, the
frozen-content rule, every repair applied and why, the known issues, and the
commands to verify. Keep it current in the same commit as any change.

---

## Re-running on an updated source

When a newer version of the same project arrives:

1. **New branch**, then drop the new files in and commit them as a baseline.
2. **Audit and diff against the old audit** — `audit.json` is there to be
   compared. New layers, new vocabulary values and new schemas are what you are
   looking for.
3. `repair_project_paths.py` — idempotent, safe to re-run.
4. `rename_to_ascii.py --dry-run` — it will refuse on any layer the naming config
   does not cover. That refusal *is* the diff: it names exactly what is new.
5. Extend `config/vocabulary.json` with any new raw values. **Unmapped values
   are never guessed** — they land as NULL and appear in `v_qa_vocab`, so the
   validator tells you what you missed.
6. Rebuild and revalidate. Compare reconciliation totals against the previous
   run; a change in total length is either real new design or a bug, and you
   should know which.

The configs are the only thing that carries project knowledge, so a new version
is usually a config extension, not a code change.

---

## Reference results

From the untouched baseline of the reference project, this runbook produced:

| | |
|---|---|
| Layers valid | 172 / 172 |
| Features | 24,107 |
| Files renamed | 822 |
| Layer IDs rewritten | 173, all unique ASCII |
| Shapefiles → tables | 164 → 7 tables + 12 views |
| Reconciliation | 16,951 sites, 6,190 cables, 312.615 km — exact match |
| Validation | 0 hard failures |
