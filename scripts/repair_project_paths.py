r"""
Repair broken layer paths in a QGIS project. Portable: nothing is hard-coded.

Stale prefixes are DISCOVERED, not configured. Every datasource that does not
resolve is tested against the workspace by basename; if the file is sitting
next to the project, the path is rewritten to "./<name>".

Also fixed, because each of these silently invalidates a layer:

  * absolute paths left over from the authoring machine
  * datasources pointing at .shx (the index) instead of .shp (the geometry)
  * Unicode NFD filenames - Windows stores names composed (NFC), so a
    decomposed name never matches and the layer fails with no visible error

Paths live in BOTH <datasource> elements and source="..." attributes on
<layer-tree-layer>. Rewriting only one leaves the project half-broken, so both
are handled.

Usage
-----
    python repair_project_paths.py [project.qgz] [--dry-run]

A timestamped .bak is written before anything is replaced. Verify afterwards
with validate_project.py.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import os
import re
import shutil
import sys
import unicodedata
import zipfile


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def find_project(root, explicit):
    if explicit:
        return os.path.abspath(explicit)
    found = sorted(glob.glob(os.path.join(root, "*.qgz"))) or \
        sorted(glob.glob(os.path.join(root, "*.qgs")))
    if not found:
        sys.exit("no .qgz or .qgs found")
    if len(found) > 1:
        sys.exit(f"several projects found, pass one: {[os.path.basename(f) for f in found]}")
    return found[0]


def read_project(path):
    """Return (member_name_or_None, xml_text, other_members)."""
    if path.lower().endswith(".qgs"):
        with open(path, encoding="utf-8") as fh:
            return None, fh.read(), []
    with zipfile.ZipFile(path) as z:
        qgs = [n for n in z.namelist() if n.lower().endswith(".qgs")]
        if len(qgs) != 1:
            sys.exit(f"expected one .qgs inside the archive, found {qgs}")
        return qgs[0], z.read(qgs[0]).decode("utf-8"), \
            [(n, z.read(n)) for n in z.namelist() if n != qgs[0]]


def write_project(path, member, xml, others, dry):
    if dry:
        return None
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.{stamp}.bak"
    shutil.copy2(path, backup)
    if member is None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(xml)
    else:
        tmp = path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(member, xml.encode("utf-8"))
            for n, data in others:
                z.writestr(n, data)
        os.replace(tmp, path)
    return backup


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    proj = find_project(os.getcwd(), args.project)
    root = os.path.dirname(proj)
    member, xml, others = read_project(proj)
    original = xml

    on_disk = {nfc(n): n for n in os.listdir(root)
               if os.path.isfile(os.path.join(root, n))}

    # Every path-bearing string in the document.
    refs = set(re.findall(r"<datasource>(.*?)</datasource>", xml, re.S))
    refs |= set(re.findall(r'\b(?:source|destinationLayerSource)="([^"]*)"', xml))

    stats = {"relocated": 0, "shx_to_shp": 0, "nfc": 0, "unresolved": []}
    rewrites: dict[str, str] = {}

    for ref in refs:
        head, sep, tail = ref.partition("|")
        if head.startswith("crs=") or head.startswith("http") or not head:
            continue

        base = nfc(os.path.basename(head))
        newbase = base

        # .shx is a derived index; the layer must point at the geometry file.
        if newbase.lower().endswith(".shx"):
            cand = newbase[:-4] + ".shp"
            if cand in on_disk:
                newbase = cand
                stats["shx_to_shp"] += 1

        if newbase not in on_disk:
            if not head.startswith("./"):
                stats["unresolved"].append(head)
            continue

        real = on_disk[newbase]           # the exact bytes Windows stores
        newhead = "./" + real
        if newhead != head:
            if nfc(head) != head:
                stats["nfc"] += 1
            if os.path.dirname(head) not in ("", "."):
                stats["relocated"] += 1

        # A shapefile's internal layer name follows its FILENAME. A stale
        # |layername= from before a rename stops the layer opening; KMZ and
        # other multi-layer containers genuinely need theirs.
        newtail = tail
        if sep and real.lower().endswith(".shp"):
            newtail = re.sub(r"layername=[^|]*",
                             f"layername={os.path.splitext(real)[0]}", tail)

        new = newhead + (sep + newtail if sep else "")
        if new != ref:
            rewrites[ref] = new

    if rewrites:
        pattern = re.compile("|".join(re.escape(k) for k in
                                      sorted(rewrites, key=len, reverse=True)))
        xml = pattern.sub(lambda m: rewrites[m.group(0)], xml)

    print(f"project        : {os.path.basename(proj)}")
    print(f"path strings   : {len(refs)}")
    print(f"rewritten      : {len(rewrites)}")
    print(f"  relocated to ./       {stats['relocated']}")
    print(f"  .shx -> .shp          {stats['shx_to_shp']}")
    print(f"  NFD -> NFC            {stats['nfc']}")
    if stats["unresolved"]:
        print(f"\n! {len(stats['unresolved'])} datasource(s) match no file in the workspace:")
        for u in sorted(set(stats["unresolved"]))[:10]:
            print(f"    {u}")
        print("  Find the files and copy them in, or delete those layers.")

    # Verify before writing.
    problems = []
    for m in re.finditer(r"<datasource>(.*?)</datasource>", xml, re.S):
        head = m.group(1).split("|")[0]
        if head.startswith("./") and nfc(head[2:]) not in on_disk:
            problems.append(head)
    if re.search(r"<datasource>[A-Za-z]:[\\/]", xml):
        problems.append("an absolute path remains in a datasource")
    if problems:
        print("\nVERIFY FAILED:")
        for p in problems[:10]:
            print(f"    ! {p}")
        return 1
    print("\nverify         : every local datasource resolves on disk")

    if args.dry_run:
        print("dry-run: nothing written")
        return 0
    if xml == original:
        print("no change needed")
        return 0
    backup = write_project(proj, member, xml, others, args.dry_run)
    print(f"backup         : {os.path.basename(backup)}")
    print(f"written        : {os.path.basename(proj)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
