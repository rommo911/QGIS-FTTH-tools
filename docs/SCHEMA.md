# Target schema

What `build_geopackage.py` produces, and why each piece is shaped the way it is.
Adjust table and column names to the domain; keep the principles.

---

## Principles

**Sector and block are columns, not filenames.** The single biggest structural
change. A project that models a block by *creating files for it* needs 164
shapefiles where 7 tables would do — and then every total is a loop over layers,
adding a block means hand-creating 15 files, and cross-block queries have no
expression at all.

**Identifiers are semantic and printable.** `THW-B01-SITE-0042` — sector, block,
type, serial. Readable in the field, sorts correctly, survives a CSV round-trip,
and a wrong value is obvious on sight. This is the key an external app writes
back against, so it must never be regenerated.

**Quantities are stored, not derived on demand.** `length_m` and `area_m2` are
written at build time, so a bill of quantities is a `SUM`, not a script run.

**One code per concept, and the raw value kept.** `type_code` is what you group
by; `type_raw` holds exactly what was recorded. Counting becomes correct without
editing survey content, and a wrong mapping is a config edit.

**Rules live in generated views, never stored columns.** Edit the config,
rebuild, and every answer changes. Nothing to migrate, and no stale derived
column pretending to be a fact.

**Missing is missing.** A NULL that a QA view reports beats a zero that reads as
a surveyed measurement.

---

## Tables

```
vocab         domain, code, label_ar, label_en, sort_order
              one row per canonical concept; label_ar is the display string

vocab_map     domain, raw, code, note
              every raw string seen in the source, and what it maps to.
              The audit trail for D4.

sector        sector_code PK, slug, name_ar, name_en, status, cabinet_ref

block         block_id PK, sector_code, block_no, status,
              area_m2, perimeter_m,
              ring_gap_m, ring_closed, geom_valid, geom_repaired, review_flag,
              source_file, geom(MultiPolygon)
              The ring_* columns record how an open boundary line became a
              polygon, so the repair is auditable rather than silent.

site          site_id PK, sector_code, block_id, block_no,
              type_code, type_raw,
              building_ref, floors, apartments, occupants, clients,
              cores_recorded,
              box_1, box_2, fdb_ref, cabinet_ref, phone_box,
              data_source, external_ref, survey_batch_id, surveyed_utc,
              surveyed_lon, surveyed_lat, surveyed_accuracy_m, rev,
              source_file, source_fid, geom(Point)

cable         cable_id PK, sector_code, block_id, block_no,
              type_code, type_raw, drop_name, d24, feeder_24, feeder_96,
              cores, length_m, source_file, source_fid, geom(LineString)

cable_count   count_id PK, sector_code, block_id, block_no,
              count_value, count_raw, source_file, source_fid, geom(Point)

cabinet       cabinet_id PK, sector_code, name_ar, source_file, geom(Point)

feeder_main   feeder_id PK, name_ar, length_m, source_file, geom(LineString)

project_meta  key, value
              build time, CRS, schema level, and the status of any unconfirmed
              engineering rule
```

`source_file` and `source_fid` on every migrated row make it possible to trace
any value back to the shapefile feature it came from. Keep them.

## Survey round-trip tables

Immutable staging, so a bad submission is recoverable and nothing from an
external app writes straight into `site`. Full contract in
`SURVEY_EXCHANGE.md`.

```
survey_batch   batch_id PK, source, surveyor, device, app_version,
               file_name, file_sha256, received_utc, record_count,
               status, notes

survey_record  record_id PK, batch_id FK, site_id, external_ref,
               building_ref, floors, apartments, occupants, clients,
               type_raw, lon, lat, accuracy_m, captured_utc,
               payload_json, status, reject_reason
```

`payload_json` keeps the submission exactly as received, so a field the schema
does not know about yet is never lost and can be promoted later without
re-collecting anything.

The surveyed GPS fix lands in `site.surveyed_lon/lat` and **never overwrites
`site.geom`**. Designed geometry and observed position are different facts; a
4-metre phone fix must not silently move a surveyed pole.

## Views

| View | Answers |
|---|---|
| `v_boq_cable` | length and segment count by type — the bill of quantities |
| `v_boq_cable_by_block` | the same, per block, for phased procurement |
| `v_boq_site` | how many of each site type |
| `v_demand` | buildings, apartments, occupants and recorded cores per block |
| `v_cores_demand` | cores required per building, **generated from the config rule** |
| `v_cores_variance` | where the rule and the recorded value disagree |
| `v_qa_vocab` | raw values with no code — the "you forgot to map this" list |
| `v_qa_coverage` | attribute coverage per block, worst first |
| `v_qa_geometry` | zero-length segments, unclosed rings, repaired rings, outliers |
| `v_qa_cores_orderable` | cable core counts that are not an orderable size |
| `v_survey_pending` | submissions awaiting review |
| `v_survey_export` | exactly what the field app should be sent |

Register views in `gpkg_contents` with `data_type='attributes'` so QGIS lists
them alongside the tables.

---

## Levels

Cumulative, not alternatives. Decide where to stop (D2).

**Level 1 — structure.** Tables, vocabulary, semantic IDs. Removes the file
sprawl. Quantities still computed by hand.

**Level 2 — quantities.** Adds `length_m`, `area_m2` and the BOQ and QA views.
This is the level that delivers measure, count and order. Recommended target.

**Level 3 — topology.** Adds a real network model:

```
node   node_id PK, type_code, parent_node, capacity,
       sector_code, block_id, geom(Point)
edge   edge_id PK, from_node, to_node, cable_id, cores, length_m
```

This is what makes fibre engineering computable — core counts along a path,
splitter utilisation, optical loss budget, cut-impact analysis. Derive the first
version by snapping cable endpoints to nearby sites and seeding `parent_node`
from existing text columns (`box_1`, `fdb_ref`, `cabinet_ref`), then correct by
hand. Build it **after** validation exists, or you will correct it twice.
