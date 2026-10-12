# Survey exchange contract

How field survey data moves between the QGIS project and an external app
(Android, or any tool that can read and write JSON/CSV over the file server).

This is a **settled constraint**, not an option: the schema was designed around
it from the first build, so adding the app later needs no migration.

**Built today:** the tables, the provenance columns, and the export view.
**Not built yet:** the app itself and the import/promote CLI — deliberately, so
the wire format can be agreed with whoever writes the app first.

---

## The two directions

```
QGIS  ──[ v_survey_export ]──►  file server  ──►  Android app
                                                      │  surveyor fills in
                                                      ▼
QGIS  ◄──[ survey_record ]───   file server  ◄──  JSON / CSV
              │
              └─► review ─► promote ─► site (stamped with provenance)
```

Nothing from the app writes directly into `site`. Everything lands in staging
first, is reviewed, and is then promoted. That is what makes a bad submission
recoverable.

## Going out — what the app receives

Read from `v_survey_export`, filtered to one block or sector:

```sql
SELECT * FROM v_survey_export WHERE block_id = '<SECTOR>-B07';
```

| Field | Meaning |
|---|---|
| `site_id` | **the key.** `<SECTOR>-B07-SITE-0042`. Printable, scannable as a QR code, and the only thing the app must send back unchanged. |
| `sector_code`, `block_id` | context for offline grouping |
| `type_code` | site type; the app shows the Arabic label from `vocab` |
| `building_ref`, `floors`, `apartments`, `occupants`, `clients` | current values, blank where never collected |
| `rev` | revision counter — send it back so a stale submission can be detected |

Coordinates: export `site` geometry reprojected to **EPSG:4326** for the phone's
GPS. The project itself stays in EPSG:32637.

## Coming back — what the app sends

One JSON object per surveyed site (or one CSV row with the same columns):

```json
{
  "site_id": "<SECTOR>-B07-SITE-0042",
  "external_ref": "app-local-8891",
  "rev": 1,
  "building_ref": "بناء 12",
  "floors": 5,
  "apartments": 14,
  "occupants": 61,
  "clients": 9,
  "type_raw": "مداخل الأبنية",
  "lon": 36.6301, "lat": 35.9312, "accuracy_m": 4.2,
  "captured_utc": "2026-09-14T08:31:00Z",
  "surveyor": "…", "device": "…", "app_version": "…"
}
```

Rules for the app:

- **`site_id` is returned exactly as received.** Never regenerate it.
- A **newly discovered** building sends `site_id: null` with `external_ref` set
  and coordinates supplied; the reconcile step allocates the next `site_id` in
  that block.
- **Omit a field you did not collect.** Do not send `0` or `""` for unknown —
  the project treats missing as missing and reports it, and a zero would be
  recorded as a surveyed fact.
- Arabic text is sent as **UTF-8, NFC normalised**. (An NFD filename is exactly
  what silently broke a layer in this project before the repair.)

## Where it lands

`survey_batch` — one row per received file. Immutable.

| Column | Note |
|---|---|
| `batch_id`, `file_name`, `file_sha256` | identity of the submission |
| `source`, `surveyor`, `device`, `app_version` | who and what produced it |
| `received_utc`, `record_count` | when and how much |
| `status` | `received` → `validated` → `promoted` \| `rejected` |

`survey_record` — one row per submitted observation. Also immutable.

The full submission is kept verbatim in **`payload_json`**, so a field the
schema does not know about yet is never lost — it can be promoted later without
re-collecting anything. `status` moves `pending` → `accepted` / `rejected` /
`superseded`, with `reject_reason` filled in on rejection.

`v_survey_pending` lists everything awaiting a decision.

## Promotion into `site`

Only after review. When a value is promoted, `site` records where it came from:

| Column | Set to |
|---|---|
| `data_source` | `field_app` |
| `survey_batch_id`, `surveyed_utc` | the batch it came from and when |
| `surveyed_lon`, `surveyed_lat`, `surveyed_accuracy_m` | the GPS fix **as captured** |
| `rev` | incremented |
| `external_ref` | the app's own id, kept for future round-trips |

**The GPS fix never overwrites `site.geom`.** Designed geometry and observed
position are different facts and are stored separately; a 4-metre phone fix must
not silently move a surveyed pole. Where they disagree materially, that is a
question for a human, and the two columns make the comparison possible.

Promotion is also where the frozen-content rule is honoured properly: an
incoming survey is *new information arriving legitimately*, not a repair
invented by a script. The provenance stamp is what keeps the two distinguishable
forever.

## Suggested rejection rules

Enforce at import, before anything reaches `site`:

- `site_id` not present in `site` and `external_ref` also absent
- `rev` lower than the current `site.rev` — a stale submission
- `apartments`, `floors`, `occupants` or `clients` negative
- `accuracy_m` above an agreed threshold
- `type_raw` not in `vocab_map` — record it, flag it, do not guess a code
- coordinates outside the block's polygon by more than an agreed tolerance
  (possible now that boundaries are closed polygons — see decision D5)

## Who the first customer is

The least-surveyed sector. On the reference project that was one sector with
3,738 building entrances and apartment data for 418 of them (11%), where 14 of
20 site layers never had an `apartments` column at all — exactly the gap this
channel exists to close. Its rows are already in the GeoPackage with NULLs where
data is missing, so nothing needs restructuring before surveying starts.

## What to agree before the app is written

1. **Wire format** — JSON lines or CSV. JSON preserves types; CSV is easier for
   whoever is doing this in a spreadsheet.
2. **Transport** — file drop on the server, or an HTTP endpoint.
3. **`clients` vs `occupants`** — the schema carries both. Confirm the
   definitions: occupants is people, clients is subscribing households.
4. **Accuracy threshold** for auto-rejection.
5. **Who reviews** a batch before promotion.
