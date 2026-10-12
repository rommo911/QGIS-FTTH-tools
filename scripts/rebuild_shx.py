r"""
Rebuild missing or unreadable .shx shapefile indexes.

A .shx carries no unique information: it is a derived index into the .shp, and
GDAL can regenerate it byte-for-byte from the geometry file. That makes this the
safe repair for two situations that otherwise stop a whole project loading:

  MISSING   the .shx was never copied, or was deleted
  CORRUPT   the .shx exists but cannot be read - typically a broken ACL whose
            owner SID no longer resolves, which on Windows also blocks moving
            and deleting it without an elevated takeown

For the corrupt case the original cannot be overwritten in place, so the whole
shapefile is rebuilt under a new basename and the original is left inert. Point
the project at the rebuild (repair_project_paths.py will do it), or rename it
during the ASCII migration, at which point the corrupt original is simply an
orphan nobody references.

Always verify the rebuild: this script compares the feature count and geometry
type against what the .shp itself reports, and refuses to install a rebuild that
does not match.

Usage
-----
    python rebuild_shx.py [workspace] [--dry-run] [--suffix " repaired"]

Run under the QGIS interpreter - it needs GDAL:

    "C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" rebuild_shx.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

from osgeo import gdal, ogr

ogr.UseExceptions()

SIDECARS = (".shp", ".dbf", ".prj", ".cpg", ".qmd", ".qml")


def readable(path):
    try:
        with open(path, "rb") as fh:
            fh.read(1)
        return True
    except OSError:
        return False


def probe(shp):
    """(feature_count, geometry_type) read with the index regenerated in memory."""
    gdal.SetConfigOption("SHAPE_RESTORE_SHX", "YES")
    ds = ogr.Open(shp)
    if ds is None:
        return None, None
    lyr = ds.GetLayer(0)
    n, gt = lyr.GetFeatureCount(), ogr.GeometryTypeToName(lyr.GetGeomType())
    ds = None
    return n, gt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", nargs="?", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--suffix", default=" repaired",
                    help="basename suffix used when the original cannot be replaced")
    args = ap.parse_args()

    root = os.path.abspath(args.workspace)
    todo = []
    for name in sorted(os.listdir(root)):
        if not name.lower().endswith(".shp"):
            continue
        stem = name[:-4]
        shx = os.path.join(root, stem + ".shx")
        if not os.path.exists(shx):
            todo.append((stem, "missing"))
        elif not readable(shx):
            todo.append((stem, "unreadable"))

    if not todo:
        print("every .shp has a readable .shx - nothing to do")
        return 0

    print(f"shapefiles needing an index rebuild: {len(todo)}\n")
    failures = 0
    for stem, why in todo:
        shp = os.path.join(root, stem + ".shp")
        if not readable(shp):
            print(f"  ! {stem}: the .shp itself is unreadable - cannot rebuild")
            failures += 1
            continue

        n, gt = probe(shp)
        if n is None:
            print(f"  ! {stem}: GDAL cannot open the .shp - cannot rebuild")
            failures += 1
            continue
        print(f"  {stem}  [{why}]  {n} feature(s), {gt}")

        if args.dry_run:
            continue

        # Build in a scratch directory so a half-written index is never left
        # next to real data.
        with tempfile.TemporaryDirectory() as tmp:
            for ext in SIDECARS:
                src = os.path.join(root, stem + ext)
                if os.path.exists(src) and readable(src):
                    shutil.copy2(src, os.path.join(tmp, stem + ext))
            gdal.SetConfigOption("SHAPE_RESTORE_SHX", "YES")
            ds = ogr.Open(os.path.join(tmp, stem + ".shp"))
            if ds is None:
                print("      ! rebuild failed")
                failures += 1
                continue
            lyr = ds.GetLayer(0)
            got_n, got_gt = lyr.GetFeatureCount(), ogr.GeometryTypeToName(lyr.GetGeomType())
            ds = None

            if (got_n, got_gt) != (n, gt):
                print(f"      ! rebuild disagrees ({got_n}, {got_gt}) - refusing to install")
                failures += 1
                continue

            new_shx = os.path.join(tmp, stem + ".shx")
            if not os.path.exists(new_shx):
                print("      ! no index produced")
                failures += 1
                continue

            target = os.path.join(root, stem + ".shx")
            if why == "missing":
                shutil.copy2(new_shx, target)
                print(f"      installed {stem}.shx ({os.path.getsize(target)} B)")
            else:
                # The corrupt original cannot be replaced; install the whole
                # shapefile under a new basename instead.
                newstem = stem + args.suffix
                for ext in SIDECARS + (".shx",):
                    src = os.path.join(tmp, stem + ext)
                    if os.path.exists(src):
                        shutil.copy2(src, os.path.join(root, newstem + ext))
                print(f"      installed as {newstem}.* - repoint the project at it")
                print(f"      the corrupt {stem}.shx is inert; clearing it needs an")
                print(f"      elevated:  takeown /f \"{stem}.shx\"")

    if args.dry_run:
        print("\ndry-run: nothing written")
    if failures:
        print(f"\n{failures} rebuild(s) failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
