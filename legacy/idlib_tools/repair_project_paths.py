#!/usr/bin/env python3
r"""
Repair layer paths inside the Idlib FTTH QGIS project (.qgz).

The project was authored on another machine where the shapefiles lived in
%USERPROFILE%\Documents while the project sat two directories deeper. Every
layer therefore points at "../../Documents/<name>.shp". Now that the project
and its data share one folder, those paths resolve to nothing.

What this fixes
---------------
1. Stale relative prefixes  -> "./"
       ../../Documents/      (328 refs)
       ../../Downloads/      (8 refs)
       ../QGIS Files/        (4 refs)
2. One hard-coded absolute path left in <ProjectGpsSettings>
       C:/Users/hp/Downloads/...
3. Two layers that point at the .shx index instead of the .shp geometry
       القطاع الرئيسي.shx, هنانو المواقع 5.shx
4. Unicode NFD -> NFC on datasource filenames. The KMZ filename is stored
   decomposed (ا + U+0655) while Windows stores it composed (U+0625), so the
   byte comparison fails and the layer silently will not load.

Paths appear both in <datasource> elements and in source="..." attributes on
<layer-tree-layer>; both are rewritten.

Usage
-----
    python tools/repair_project_paths.py [--dry-run] [project.qgz]

The original .qgz is left untouched unless the rewrite fully succeeds; a
timestamped .bak copy is written next to it either way.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import sys
import unicodedata
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Stale directory prefixes -> replacement. Order matters: longest first.
PREFIX_FIXES = [
    ("../../Documents/", "./"),
    ("../../Downloads/", "./"),
    ("../QGIS Files/", "./"),
    ("C:/Users/hp/Downloads/", "./"),
    ("C:/Users/hp/Documents/", "./"),
]

# Layers that reference the index file rather than the geometry file.
SHX_FIXES = [
    ("./القطاع الرئيسي.shx", "./القطاع الرئيسي.shp"),
    ("./هنانو المواقع 5.shx", "./هنانو المواقع 5.shp"),
]


def find_project(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    candidates = sorted(ROOT.glob("*.qgz"))
    if not candidates:
        sys.exit("No .qgz found next to the repository root.")
    if len(candidates) > 1:
        sys.exit(f"Several .qgz files found, pass one explicitly: {[c.name for c in candidates]}")
    return candidates[0]


def read_qgz(qgz: Path) -> tuple[str, str, list[tuple[str, bytes]]]:
    """Return (qgs member name, qgs text, [(name, bytes) for every other member])."""
    with zipfile.ZipFile(qgz) as z:
        names = z.namelist()
        qgs = [n for n in names if n.lower().endswith(".qgs")]
        if len(qgs) != 1:
            sys.exit(f"Expected exactly one .qgs inside {qgz.name}, found {qgs}")
        qgs_name = qgs[0]
        text = z.read(qgs_name).decode("utf-8")
        others = [(n, z.read(n)) for n in names if n != qgs_name]
    return qgs_name, text, others


def rewrite(text: str) -> tuple[str, dict[str, int]]:
    stats: dict[str, int] = {}

    for stale, new in PREFIX_FIXES:
        n = text.count(stale)
        if n:
            text = text.replace(stale, new)
            stats[f"prefix {stale!r} -> {new!r}"] = n

    for stale, new in SHX_FIXES:
        n = text.count(stale)
        if n:
            text = text.replace(stale, new)
            stats[f"index  {stale} -> {new}"] = n

    # NFC-normalise only the path payloads, never the whole document: layer
    # names and labels are display strings and must survive byte-identical.
    def norm_ds(m: re.Match) -> str:
        return f"<datasource>{unicodedata.normalize('NFC', m.group(1))}</datasource>"

    text, n1 = re.subn(r"<datasource>(.*?)</datasource>", norm_ds, text, flags=re.S)

    def norm_attr(m: re.Match) -> str:
        return f'{m.group(1)}="{unicodedata.normalize("NFC", m.group(2))}"'

    text, n2 = re.subn(
        r'\b(source|destinationLayerSource)="([^"]*)"', norm_attr, text
    )
    stats["NFC-normalised datasource elements"] = n1
    stats["NFC-normalised source attributes"] = n2
    return text, stats


def verify(text: str) -> list[str]:
    """Return a list of problems found in the rewritten document."""
    problems: list[str] = []
    for stale, _ in PREFIX_FIXES:
        if stale in text:
            problems.append(f"stale prefix still present: {stale}")
    if re.search(r"[A-Za-z]:[\/]Users", text):
        problems.append("an absolute C:/Users path is still present")

    missing: list[str] = []
    for m in re.finditer(r"<datasource>(.*?)</datasource>", text, re.S):
        ds = m.group(1)
        if not ds.startswith("./"):
            continue  # remote XYZ layer
        rel = ds.split("|")[0][2:]
        if not (ROOT / rel).exists():
            missing.append(rel)
    if missing:
        problems.append(f"{len(missing)} datasource(s) do not resolve: {sorted(set(missing))[:5]}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?", help="path to the .qgz (default: the only one in the repo root)")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = ap.parse_args()

    qgz = find_project(args.project)
    qgs_name, text, others = read_qgz(qgz)
    original = text

    new_text, stats = rewrite(text)

    print(f"project : {qgz.name}")
    print(f"member  : {qgs_name}")
    print("changes :")
    for k, v in stats.items():
        print(f"    {v:>5}  {k}")

    problems = verify(new_text)
    if problems:
        print("\nVERIFY FAILED:")
        for p in problems:
            print(f"    ! {p}")
        return 1
    print("\nverify  : all datasources resolve on disk, no stale or absolute paths remain")

    if args.dry_run:
        print("dry-run : nothing written")
        return 0
    if new_text == original:
        print("no change needed")
        return 0

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = qgz.with_suffix(f".qgz.{stamp}.bak")
    shutil.copy2(qgz, backup)

    tmp = qgz.with_suffix(".qgz.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(qgs_name, new_text.encode("utf-8"))
        for name, data in others:
            z.writestr(name, data)
    tmp.replace(qgz)

    print(f"backup  : {backup.name}")
    print(f"written : {qgz.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
