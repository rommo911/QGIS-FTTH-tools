# Migration decision sheet — TEMPLATE

Eight decisions that define the target layout. `[x]` marks the recommendation.
Change any of them — this file is the record of what was chosen and why.

**Status: not yet decided.**

Fill this in with the project owner before Phase 4 of the runbook.
`[x]` marks the recommendation; change any of them. Record *why* when you
deviate — the consequence lines say what you are trading away.

---

## Settled — not up for decision

- **The display language is never translated.** ASCII is for identifiers only:
  IDs, filenames, column names, vocabulary codes. Every label a person reads
  stays in the original language — legend names, attribute labels, map output,
  reports. Each table carries `type_code` (ASCII) beside `type_ar` (the label).
- **Survey content is frozen.** Gaps are recorded, never filled. Migration
  reshapes the container; it does not edit values or geometry.
- **GeoPackage is the target.** One `idlib_ftth.gpkg` replaces 164 shapefiles.
- **The layout must support survey round-trip.** A field app (Android) will
  send JSON or CSV to the file server — houses, buildings, occupants, clients —
  for import into the project, and must be able to receive an export to fill in
  on the ground. The schema carries this from day one: stable printable IDs,
  immutable `survey_batch` / `survey_record` staging with the raw payload kept
  verbatim, provenance stamps on every promoted value, and surveyed GPS stored
  separately from designed geometry. See `docs/SURVEY_EXCHANGE.md`.

## What the layout must do

| Verb | Mechanism |
|---|---|
| Measure | `length_m`, `area_m2` stored on write — a total is a `SUM`, not a 19-layer loop |
| Count | a `vocab` table with one code per concept, so aerial cable stops splitting across two spellings |
| Order | `v_boq_*` views turn quantities into a bill of quantities by type, sector and block |
| Automate | stable feature IDs that survive a round-trip, so external tagging can write back safely |

## Measured baseline

Fill in from the audit before the conversation — decisions are much easier when
the quantities are on the table. Record at least: total line length by type,
feature counts per table, block count, attribute coverage per sector, and how
much quantity is currently splitting across duplicate spellings.

*Reference project, for scale: 312.6 km of cable across 6,190 segments; 16,951
sites; 9,461 building entrances; 56 blocks; 8.6 km hiding under second
spellings.*

---

## Target schema

```
LEVEL 1 · structure
vocab       domain, code, label_ar, label_en, sort_order
sector      sector_code PK, name_ar, cabinet_ref, status
block       block_id PK, sector_code, block_no, status, geom(Polygon)
site        site_id PK, sector_code, block_id, type_code, type_raw,
            building_ref, floors, apartments, cores_req,
            box_1, box_2, fdb_ref, cabinet_ref, geom(Point)
cable       cable_id PK, sector_code, block_id, type_code, type_raw,
            drop_name, cores, geom(LineString)

LEVEL 2 · quantities
block      + area_m2
cable      + length_m
views        v_boq_cable, v_boq_site, v_demand, v_qa_*

LEVEL 3 · topology
node        node_id PK, type_code, parent_node, capacity,
            sector_code, block_id, geom(Point)
edge        edge_id PK, from_node, to_node, cable_id, cores, length_m
```

`type_raw` holds the original string byte-for-byte, so the frozen-content rule
holds while `type_code` gives counting something stable to group by.

---

## Decisions

### D1 · Migration sequence
- [x] **Pilot Thawra end-to-end, then roll out.** 19 blocks, 100% coverage,
      every field type present. The pipeline is proven on real data before the
      other 37 blocks move.
- [ ] One layer type at a time across all sectors.
- [ ] Single big-bang run. *Higher risk with 48 source schemas.*

### D2 · How far to take the model
- [ ] Level 1 — structure only.
- [x] **Level 2 — structure + quantities.** Delivers measure, count and order.
- [ ] Level 3 now. *Defer: topology built before validation gets corrected twice.*

### D3 · Feature identifiers
- [ ] Integer sequence per table. *Meaningless on a plan, easy to renumber.*
- [x] **Semantic composite key** — `<SECTOR>-B01-SITE-0042`. Readable in the field,
      sorts correctly, survives CSV round-trip, wrong values are obvious.
- [ ] UUID. *Choose this instead if several teams will merge data.*

### D4 · Vocabulary normalisation
- [ ] Rewrite recorded values to canonical in place. *Conflicts with the frozen
      content rule and destroys the evidence.*
- [x] **Add `type_code`, keep `type_raw` verbatim.** Reversible and auditable.
      Unmapped values surface in `v_qa_vocab` rather than being guessed.
- [ ] External lookup table only.

### D5 · Block boundaries
Check the audit's RING CANDIDATES section for this project's numbers.
*Reference project: all 56 open, median gap 0.08 m, max 2.53 m.*
- [x] **Auto-close to polygons, 5 m tolerance, report every fix.** Gives
      `area_m2`, point-in-block assignment and overlap checks. The two gaps
      above 1 m get flagged for review.
- [ ] Keep as lines, assign blocks from the source layer.
- [ ] Hand-redraw all 56.

### D6 · An incomplete sector's place
- [x] **Migrate structure, leave the gaps visible.** Its blocks and sites move;
      tables it has no data for simply have no rows for it. Coverage reports read
      honestly and the slot is ready when the survey happens.
- [ ] Full scope — commission survey and design first.
- [ ] Exclude for now.

### D7 · What contractors receive
- [x] **GeoPackage authoritative + scripted export** to shapefile / CSV / KMZ
      per sector or block. Exports are disposable so none becomes a shadow master.
- [ ] GeoPackage only. *Consequence: each external request is a manual QGIS
      export. The survey exchange is a separate channel, unaffected either way.*

### D8 · How the automation runs
- [x] **Python + GDAL in `tools/`, with a validation gate.** Same pattern as the
      repair scripts: `--dry-run`, verify, commit. The gate refuses a commit
      that breaks a QA rule.
- [ ] QGIS Processing models. *Better for handover to a non-Python engineer.*
- [ ] Scripts only, no gate.

---

## Work packages, if every recommendation stands

| # | Package | Covers | Size | Driver |
|---|---|---|---|---|
| 1 | Vocabulary + schema spec | D3, D4 | small | agreeing ~20 codes; no bulk data movement |
| 2 | Thawra pilot into GeoPackage | D1, D2, D5 | medium | writing the loader once against 48 source schemas |
| 3 | Roll out the remaining sectors | D6 | small | mostly a re-run; incomplete sectors need null handling |
| 4 | BOQ views, exports, validation gate | D7, D8 | medium | deciding which QA rules block a commit vs warn |

Topology (level 3) sits after package 4 deliberately — validation will expose
the connectivity errors that would otherwise be corrected twice.

## Open questions

1. **D1–D8** — accept the defaults or name what changes.
2. **Vocabulary codes.** Propose them from the audit's vocabulary section, then
   have the owner confirm the domain-specific ones. Terms that drive quantities
   (single vs double distribution, cable sizes) matter most.
3. **Engineering rules.** Derive candidates from the recorded data and report the
   match rate as evidence; do not invent one. Mark unconfirmed until signed off.
4. **Scope of any incomplete sector** — it decides whether the rollout package is
   a re-run or a placeholder.

---

*Cable lengths are 2D geometry lengths in metres, EPSG:32637; they exclude
slack, coiling and vertical drops.*

**Standing instruction for gaps:** fill in what can be decided without asking;
where a required value is genuinely unknown, leave it NULL and let a QA view
report it. Never substitute a guess for a missing measurement.


IMPORTANT RULE 
make sure the layout and design can support later automated surveys, example, a survey from android app that exports or sends to our file server a json or csv with survey , houeses, number of building, and number clients / occupant , that can later be inserted to the QGIS project  ( or exported from QGIS to the andoird app in some way so we can fill info on the grous   ) JUST keep the design support such things for later use 
