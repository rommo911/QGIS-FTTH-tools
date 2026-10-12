r"""
Validation gate for idlib_ftth.gpkg (decision D8).

Two kinds of check:

  RECONCILE  the GeoPackage against the source shapefiles - feature counts and
             total cable length must match, or the migration lost something.
  QA         the rules a reviewer would apply by eye, from the QA views.

Exit code 0 only when every hard check passes. Warnings do not fail the run:
missing survey data is a finding, not a defect, and Hananu is expected to be
incomplete.

    "C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" tools\validate_gpkg.py
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys

from osgeo import ogr

ogr.UseExceptions()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GPKG = os.path.join(ROOT, "idlib_ftth.gpkg")

hard_failures: list[str] = []
warnings: list[str] = []


def ok(label, detail=""):
    print(f"  [ ok ] {label:<42} {detail}")


def fail(label, detail=""):
    print(f"  [FAIL] {label:<42} {detail}")
    hard_failures.append(f"{label} {detail}".strip())


def warn(label, detail=""):
    print(f"  [warn] {label:<42} {detail}")
    warnings.append(f"{label} {detail}".strip())


def shapefile_totals():
    """Ground truth read straight from the source shapefiles."""
    counts = {"site": 0, "cable": 0, "cable_count": 0, "block": 0}
    length = 0.0
    for pat, key in (("*_sites.shp", "site"), ("*_cables.shp", "cable"),
                     ("*_cablecount.shp", "cable_count"), ("*_boundary.shp", "block")):
        for p in glob.glob(os.path.join(ROOT, pat)):
            ds = ogr.Open(p)
            lyr = ds.GetLayer(0)
            counts[key] += lyr.GetFeatureCount()
            if key == "cable":
                for f in lyr:
                    g = f.GetGeometryRef()
                    if g is not None:
                        length += g.Length()
            ds = None
    return counts, length


def main() -> int:
    if not os.path.exists(GPKG):
        print("idlib_ftth.gpkg not found - run tools/build_geopackage.py first")
        return 2

    con = sqlite3.connect(GPKG)
    cur = con.cursor()

    def scalar(sql):
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None

    # After the cutover the shapefiles are gone, so reconcile against the
    # expectations recorded in project_meta at build time - captured while the
    # shapefiles were still present. If they are still on disk, prefer them:
    # a live comparison beats a remembered one.
    cur.execute("SELECT key, value FROM project_meta")
    meta = dict(cur.fetchall())
    have_shp = bool(glob.glob(os.path.join(ROOT, "*_sites.shp")))

    if have_shp:
        print("RECONCILE against source shapefiles")
        src, src_len = shapefile_totals()
    else:
        print("RECONCILE against the baseline recorded at build time")
        src = {t: int(meta.get(f"expect_count_{t}", -1))
               for t in ("site", "cable", "cable_count", "block")}
        src_len = float(meta.get("expect_cable_length_m", -1))
        if -1 in src.values() or src_len < 0:
            warn("no recorded baseline", "rebuild to capture one")
    for table in ("site", "cable", "cable_count", "block"):
        got = scalar(f"SELECT COUNT(*) FROM {table}")
        if got == src[table]:
            ok(f"{table} feature count", f"{got}")
        else:
            fail(f"{table} feature count", f"gpkg {got} vs shapefiles {src[table]}")

    got_len = scalar("SELECT SUM(length_m) FROM cable") or 0.0
    if src_len < 0:
        warn("total cable length", f"{got_len/1000:.3f} km (no baseline to compare)")
    elif abs(got_len - src_len) < 1.0:
        ok("total cable length", f"{got_len/1000:.3f} km")
    else:
        fail("total cable length", f"gpkg {got_len:.1f} m vs shapefiles {src_len:.1f} m")

    print("\nINTEGRITY")
    for table, key in (("site", "site_id"), ("cable", "cable_id"),
                       ("block", "block_id"), ("cable_count", "count_id")):
        n = scalar(f"SELECT COUNT(*) FROM {table}")
        d = scalar(f"SELECT COUNT(DISTINCT {key}) FROM {table}")
        if n == d:
            ok(f"{key} unique", f"{n}")
        else:
            fail(f"{key} unique", f"{n - d} duplicate(s)")

    orphan = scalar("SELECT COUNT(*) FROM site s "
                    "LEFT JOIN block b ON b.block_id = s.block_id WHERE b.block_id IS NULL")
    (ok if orphan == 0 else fail)("every site resolves to a block",
                                  "" if orphan == 0 else f"{orphan} orphans")

    nogeom = scalar("SELECT COUNT(*) FROM site WHERE geom IS NULL")
    (ok if nogeom == 0 else fail)("every site has geometry",
                                  "" if nogeom == 0 else f"{nogeom} without")

    print("\nVOCABULARY")
    unmapped = scalar("SELECT COALESCE(SUM(n),0) FROM v_qa_vocab")
    if unmapped == 0:
        ok("every raw value mapped to a code")
    else:
        cur.execute("SELECT tbl, raw, n FROM v_qa_vocab ORDER BY n DESC")
        fail("unmapped vocabulary values", f"{unmapped} features")
        for t, raw, n in cur.fetchall():
            print(f"         {t}: {raw!r} x{n}")

    bad_cores = scalar("SELECT COUNT(*) FROM v_qa_cores_orderable")
    if bad_cores:
        warn("cable core counts not orderable", f"{bad_cores} cable(s)")
    else:
        ok("cable core counts orderable", "cable.cores not yet populated")

    print("\nGEOMETRY")
    cur.execute("SELECT issue, COUNT(*) FROM v_qa_geometry GROUP BY issue ORDER BY 2 DESC")
    rows = cur.fetchall()
    if not rows:
        ok("no geometry issues")
    # Only defects the MIGRATION could have introduced are hard failures.
    # Quirks that exist in the source shapefiles are findings: per the standing
    # rule they get reported, not repaired, and must not block a build.
    SOURCE_FINDINGS = {
        "block_ring_repaired", "block_ring_gap_needs_review",
        "drop_over_max_length", "cable_very_short",
    }
    for issue, n in rows:
        (warn if issue in SOURCE_FINDINGS else fail)(issue, f"{n}")

    invalid = scalar("SELECT COUNT(*) FROM block WHERE geom_valid = 0")
    (ok if invalid == 0 else fail)("all block polygons valid",
                                   "" if invalid == 0 else f"{invalid} invalid")

    print("\nCOVERAGE (findings, never failures)")
    cur.execute("""SELECT sector_code, SUM(entrances), SUM(missing_apartments),
                          ROUND(100.0*SUM(entrances - missing_apartments)/SUM(entrances),1)
                   FROM v_qa_coverage GROUP BY sector_code ORDER BY 4""")
    for sc, ent, miss, pct in cur.fetchall():
        line = f"{sc}: {ent} entrances, {pct}% with apartment data"
        (warn if pct < 100 else ok)("attribute coverage", line)

    nocables = scalar("SELECT COUNT(*) FROM block WHERE status = 'surveyed'")
    if nocables:
        warn("blocks with no cable design", f"{nocables}")

    print("\nENGINEERING RULE")
    tot = scalar("SELECT COUNT(*) FROM v_cores_demand WHERE cores_required IS NOT NULL")
    var = scalar("SELECT COUNT(*) FROM v_cores_variance")
    if tot:
        ok("cores rule vs recorded", f"{tot-var}/{tot} agree ({(tot-var)/tot*100:.1f}%)")
        if var:
            warn("cores variance to adjudicate", f"{var} site(s) - see v_cores_variance")
    status = scalar("SELECT value FROM project_meta WHERE key='cores_rule_status'")
    if status and "CONFIRMED" not in status.split(" - ")[0]:
        warn("cores rule not engineer-confirmed", status.split(" - ")[0])

    con.close()

    print("\n" + "=" * 66)
    if hard_failures:
        print(f"FAILED - {len(hard_failures)} hard check(s), {len(warnings)} warning(s)")
        for f in hard_failures:
            print(f"   ! {f}")
        return 1
    print(f"PASSED - 0 hard failures, {len(warnings)} warning(s) recorded as findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
