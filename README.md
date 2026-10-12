# QGIS-FTTH-tools

Migrate old, GUI-built QGIS fibre-optic (FTTH) planning projects into one clean,
machine-readable GeoPackage, without losing a feature or changing what the map
shows.

Put a project in `target/<name>/` as received. The pipeline audits it, repairs
broken paths and corrupt indexes, gives layers stable ASCII identifiers (display
names stay in the original language), and consolidates hundreds of shapefiles
into one GeoPackage with a normalised schema, quantity views and QA views. It
validates the result against the source and writes it to `output/<name>/`.

## Pipeline

| Step | Script |
|---|---|
| 1. Audit (read-only) | `scripts/audit_workspace.py` |
| 2. Repair paths | `scripts/repair_project_paths.py` |
| 3. Rebuild broken indexes | `scripts/rebuild_shx.py` |
| 4. Load check | `scripts/validate_project.py` |
| 5. ASCII identifiers | `scripts/rename_to_ascii.py` |
| 6. Build GeoPackage | `scripts/build_geopackage.py` |
| 7. Validate | `scripts/validate_gpkg.py` |

Project-specific values live in JSON (`config/templates/`), never in code. The
method is in [`docs/RUNBOOK.md`](docs/RUNBOOK.md), and the traps are in
[`docs/PITFALLS.md`](docs/PITFALLS.md).

For the people who edit a migrated project in QGIS, there is a click-by-click
guide in [`user-guide/`](user-guide/README.md).

## Requirements

QGIS 3.40+ or 4.x, for its bundled Python with PyQGIS and GDAL. On Windows, set
`PYTHONUTF8=1`.

## Status

The steps were verified end-to-end on a 172-layer, 24,107-feature city project:
341 broken paths repaired, 828 files consolidated into one GeoPackage, and
16,951 sites and 312.615 km of cable reconciled exactly. A single
`target/` -> `output/` driver is in progress.
