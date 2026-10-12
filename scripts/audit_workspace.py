r"""
Audit a messy QGIS shapefile workspace. Read-only: writes nothing but a report.

This replaces the whole manual exploration phase. Run it first, in any workspace
containing a .qgz/.qgs plus shapefiles, and it answers in one pass:

  PROJECT    which layers exist, how the group tree is organised, and whether
             layer IDs and names can address a layer at all
  PATHS      every stale prefix, absolute path, .shx-instead-of-.shp reference,
             and Unicode NFD mismatch, counted per location
  FILES      what is referenced but missing, what is on disk but orphaned, and
             any file that cannot be read (corrupt ACL)
  CRS        .prj and .cpg consistency
  SCHEMAS    every distinct .dbf field set, and the near-duplicate field names
             that indicate typos
  VOCABULARY distinct values of every short text field, so the controlled
             vocabulary can be drafted from real data
  GEOMETRY   type per layer group, open vs closed rings, degenerate segments

Usage
-----
    python audit_workspace.py [workspace_dir] [--json report.json]

Plain Python is enough for most checks. Run it under the QGIS interpreter to
also get geometry analysis, which needs GDAL:

    "C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" audit_workspace.py

Nothing here modifies the workspace.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import struct
import sys
import unicodedata
import zipfile

try:
    from osgeo import ogr
    ogr.UseExceptions()
    HAVE_GDAL = True
except Exception:
    HAVE_GDAL = False


# --------------------------------------------------------------------------- #
def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def hr(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


# --------------------------------------------------------------------------- #
# project file
# --------------------------------------------------------------------------- #
def read_project(root):
    """Return (project_path, qgs_xml_text) or (None, None)."""
    for name in sorted(os.listdir(root)):
        if name.lower().endswith(".qgz"):
            path = os.path.join(root, name)
            with zipfile.ZipFile(path) as z:
                qgs = [n for n in z.namelist() if n.lower().endswith(".qgs")]
                if qgs:
                    return path, z.read(qgs[0]).decode("utf-8", "replace")
    for name in sorted(os.listdir(root)):
        if name.lower().endswith(".qgs"):
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="replace") as fh:
                return path, fh.read()
    return None, None


def audit_project(xml, report):
    hr("PROJECT")
    ver = re.search(r'version="([^"]+)"', xml)
    saved_by = re.search(r'saveUser="([^"]*)"', xml)
    print(f"authored in     : {ver.group(1) if ver else '?'}")
    print(f"saved by        : {saved_by.group(1) if saved_by else '?'}")

    ids = re.findall(r"<id>([^<]+)</id>", xml)
    names = re.findall(r"<layername>(.*?)</layername>", xml, re.S)
    groups = re.findall(r'<layer-tree-group[^>]*name="([^"]*)"', xml)
    print(f"map layers      : {len(re.findall(r'<maplayer', xml))}")
    print(f"layer ids       : {len(ids)} ({len(set(ids))} unique)")
    print(f"groups          : {len(groups)}")

    # Can a script address a layer?
    opaque = [i for i in ids if re.match(r"^_+", i)]
    print(f"\nADDRESSABILITY")
    if opaque:
        print(f"  ! {len(opaque)} layer id(s) begin with underscores - QGIS stripped")
        print(f"    non-ASCII from the layer name, so the id carries no meaning.")
        print(f"    e.g. {opaque[0][:52]}")
    else:
        print("  ok  layer ids look meaningful")

    dupes = {n: c for n, c in collections.Counter(names).items() if c > 1}
    if dupes:
        top = sorted(dupes.items(), key=lambda kv: -kv[1])[:5]
        print(f"  ! {len(dupes)} layer name(s) are duplicated; worst:")
        for n, c in top:
            print(f"      {c:3d}x  {n!r}")
    ws = [n for n in set(names) if n != n.strip()]
    if ws:
        print(f"  ! {len(ws)} name(s) differ only by leading/trailing whitespace")

    report["project"] = {
        "version": ver.group(1) if ver else None,
        "layers": len(ids), "unique_ids": len(set(ids)),
        "opaque_ids": len(opaque), "duplicate_names": len(dupes),
        "whitespace_names": len(ws),
    }
    return ids, names


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def audit_paths(xml, root, report):
    hr("PATHS")
    ds = re.findall(r"<datasource>(.*?)</datasource>", xml, re.S)
    attrs = re.findall(r'\b(?:source|destinationLayerSource)="([^"]*)"', xml)
    print(f"<datasource> elements   : {len(ds)}")
    print(f"source=\"...\" attributes : {len(attrs)}")
    print("  (both carry paths - a fix that rewrites only one leaves the project"
          " half-broken)")

    every = ds + attrs
    prefixes = collections.Counter()
    for d in every:
        p = d.split("|")[0]
        if p.startswith(".."):
            prefixes["/".join(p.split("/")[:-1]) + "/"] += 1
        elif re.match(r"^[A-Za-z]:", p):
            prefixes["ABSOLUTE " + "/".join(p.split("/")[:-1]) + "/"] += 1

    print("\nstale / absolute prefixes:")
    if prefixes:
        for pre, n in prefixes.most_common():
            print(f"  {n:5d}  {pre}")
    else:
        print("  none - all paths are already local")

    shx = [d for d in every if d.split("|")[0].lower().endswith(".shx")]
    if shx:
        print(f"\n! {len(shx)} datasource(s) point at .shx instead of .shp:")
        for d in sorted(set(shx)):
            print(f"    {d}")

    nfd = sorted({d for d in every if nfc(d) != d})
    if nfd:
        print(f"\n! {len(nfd)} datasource(s) stored in Unicode NFD (decomposed).")
        print("  Windows stores filenames composed, so these never match on disk")
        print("  and the layer fails silently. Normalise to NFC.")
        for d in nfd[:5]:
            print(f"    {d}")

    absolute = re.compile(r"^[A-Za-z]:")
    abs_refs = sorted({d for d in every if absolute.match(d.split('|')[0])})
    if abs_refs:
        print(f"\n! {len(abs_refs)} absolute path(s) - will break on another machine:")
        for d in abs_refs[:5]:
            print(f"    {d}")

    report["paths"] = {
        "datasource_elements": len(ds), "source_attributes": len(attrs),
        "prefixes": dict(prefixes), "shx_refs": len(shx),
        "nfd_refs": len(nfd), "absolute_refs": len(abs_refs),
    }
    return every


# --------------------------------------------------------------------------- #
# files on disk
# --------------------------------------------------------------------------- #
def audit_files(every, root, report):
    hr("FILES")
    disk = {nfc(n): n for n in os.listdir(root) if os.path.isfile(os.path.join(root, n))}

    referenced = set()
    for d in every:
        p = d.split("|")[0]
        if p.startswith("crs=") or p.startswith("http"):
            continue
        referenced.add(nfc(os.path.basename(p)))

    missing = sorted(r for r in referenced if r and r not in disk)
    print(f"referenced files : {len(referenced)}")
    print(f"missing on disk  : {len(missing)}")
    for m in missing[:10]:
        print(f"    ! {m}")

    shp_disk = {n for n in disk if n.lower().endswith(".shp")}
    orphans = sorted(shp_disk - referenced)
    print(f"\nshapefiles on disk : {len(shp_disk)}")
    print(f"orphans (unreferenced): {len(orphans)}")
    for o in orphans[:10]:
        print(f"    {o}")

    unreadable = []
    for n in sorted(disk):
        try:
            with open(os.path.join(root, disk[n]), "rb") as fh:
                fh.read(1)
        except OSError as exc:
            unreadable.append((n, exc.strerror or str(exc)))
    if unreadable:
        print(f"\n! {len(unreadable)} file(s) cannot be read (corrupt ACL / lock):")
        for n, err in unreadable:
            print(f"    {n}  -  {err}")
        print("  A .shx is a derived index and can be rebuilt with GDAL")
        print("  SHAPE_RESTORE_SHX; anything else needs an elevated takeown.")

    incomplete = []
    for n in sorted(shp_disk):
        stem = n[:-4]
        for ext in (".shx", ".dbf", ".prj"):
            if nfc(stem + ext) not in disk:
                incomplete.append(stem + ext)
    if incomplete:
        print(f"\n! {len(incomplete)} missing shapefile sidecar(s):")
        for i in incomplete[:10]:
            print(f"    {i}")

    report["files"] = {
        "referenced": len(referenced), "missing": missing,
        "shapefiles": len(shp_disk), "orphans": orphans,
        "unreadable": [n for n, _ in unreadable],
        "missing_sidecars": incomplete,
    }


# --------------------------------------------------------------------------- #
# crs / encoding
# --------------------------------------------------------------------------- #
def audit_crs(root, report):
    hr("CRS AND ENCODING")
    prj = collections.Counter()
    for n in os.listdir(root):
        if n.lower().endswith(".prj"):
            with open(os.path.join(root, n), encoding="utf-8", errors="replace") as fh:
                prj[fh.read(70).strip()] += 1
    print(f"distinct .prj    : {len(prj)}")
    for text, n in prj.most_common(5):
        print(f"  {n:4d}  {text[:64]}")
    if len(prj) > 1:
        print("  ! more than one CRS in the workspace - reproject before merging")

    shp = [n for n in os.listdir(root) if n.lower().endswith(".shp")]
    nocpg = [n[:-4] for n in shp
             if not os.path.exists(os.path.join(root, n[:-4] + ".cpg"))]
    cpgs = collections.Counter()
    for n in os.listdir(root):
        if n.lower().endswith(".cpg"):
            with open(os.path.join(root, n), encoding="utf-8", errors="replace") as fh:
                cpgs[fh.read().strip()] += 1
    print(f"\n.cpg encodings   : {dict(cpgs)}")
    if nocpg:
        print(f"! {len(nocpg)} shapefile(s) have no .cpg - non-ASCII attributes")
        print("  will be misread. Affected: " + ", ".join(nocpg[:5]))
    report["crs"] = {"distinct_prj": len(prj), "cpg": dict(cpgs), "missing_cpg": nocpg}


# --------------------------------------------------------------------------- #
# dbf schemas + vocabulary
# --------------------------------------------------------------------------- #
def read_dbf(path):
    """Minimal DBF reader: (fields, rows). No GDAL needed."""
    with open(path, "rb") as fh:
        head = fh.read(32)
        if len(head) < 32:
            return [], []
        nrec = struct.unpack("<I", head[4:8])[0]
        hlen = struct.unpack("<H", head[8:10])[0]
        rlen = struct.unpack("<H", head[10:12])[0]
        fields = []
        for _ in range((hlen - 33) // 32):
            d = fh.read(32)
            if len(d) < 32 or d[0] == 0x0D:
                break
            name = d[:11].split(b"\x00")[0].decode("utf-8", "replace")
            fields.append((name, chr(d[11]), d[16]))
        fh.seek(hlen)
        rows = []
        for _ in range(nrec):
            rec = fh.read(rlen)
            if len(rec) < rlen:
                break
            off, out = 1, {}
            for name, _t, width in fields:
                out[name] = rec[off:off + width].decode("utf-8", "replace").strip()
                off += width
            rows.append(out)
    return fields, rows


def edit_distance(a, b, cap=3):
    """Levenshtein distance, giving up once it exceeds cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def similar(a, b):
    """True when two names look like the same field spelled differently.

    Uses edit distance so a moved letter is caught too - 'floors num' vs
    'foolrs num' is two substitutions, not one, and a distance-1 test misses it.

    Names that differ only in a trailing number are deliberately NOT flagged:
    'box 1' / 'box 2' and 'feeder 24' / 'feeder 96' are real, distinct fields.
    """
    a, b = a.strip().lower(), b.strip().lower()
    if a == b:
        return False
    stem = re.compile(r"^(.*?)[\s_]*\d+$")
    ma, mb = stem.match(a), stem.match(b)
    if ma and mb and ma.group(1) == mb.group(1):
        return False
    limit = 1 if min(len(a), len(b)) < 6 else 2
    return edit_distance(a, b, limit) <= limit


def audit_schemas(root, report):
    hr("ATTRIBUTE SCHEMAS")
    sigs = collections.Counter()
    examples = {}
    allfields = collections.Counter()
    total = 0
    for n in sorted(os.listdir(root)):
        if not n.lower().endswith(".dbf"):
            continue
        try:
            fields, rows = read_dbf(os.path.join(root, n))
        except Exception:
            continue
        total += len(rows)
        sig = tuple((f[0], f[1], f[2]) for f in fields)
        sigs[sig] += 1
        examples.setdefault(sig, []).append(n)
        for f in fields:
            allfields[f[0]] += 1

    print(f"total features        : {total}")
    print(f"distinct field sets   : {len(sigs)}")
    if len(sigs) > 8:
        print("  ! that is far more than the number of logical layer types.")
        print("    Each new file was drawn from whatever the last one looked like.")
    for sig, n in sigs.most_common(6):
        print(f"\n  {n:3d} file(s): {[f[0] for f in sig]}")
        print(f"      e.g. {examples[sig][0]}")

    print("\nALL FIELD NAMES (count = files using it)")
    for name, n in allfields.most_common():
        print(f"  {n:4d}  {name!r}")

    names = list(allfields)
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if similar(a, b):
                pairs.append((a, allfields[a], b, allfields[b]))
    if pairs:
        print("\n! NEAR-DUPLICATE FIELD NAMES - almost certainly typos.")
        print("  A script reading the majority spelling gets NULL on the others,")
        print("  silently, without raising.")
        for a, na, b, nb in sorted(pairs, key=lambda p: -max(p[1], p[3])):
            print(f"    {a!r} ({na}) vs {b!r} ({nb})")

    report["schemas"] = {
        "total_features": total, "distinct_field_sets": len(sigs),
        "fields": dict(allfields),
        "near_duplicates": [[a, b] for a, _, b, _ in pairs],
    }


def audit_vocabulary(root, report, max_distinct=40):
    hr("VOCABULARY CANDIDATES")
    print("Distinct values of every short text field, grouped by field name.")
    print("Use this to draft config/vocabulary.json. Near-identical spellings")
    print("are the ones that split counts.\n")

    by_field = collections.defaultdict(collections.Counter)
    for n in sorted(os.listdir(root)):
        if not n.lower().endswith(".dbf"):
            continue
        try:
            fields, rows = read_dbf(os.path.join(root, n))
        except Exception:
            continue
        text = [f[0] for f in fields if f[1] == "C"]
        for r in rows:
            for f in text:
                v = r.get(f, "")
                if v:
                    by_field[f.strip().lower()][v] += 1

    vocab = {}
    for field, counter in sorted(by_field.items()):
        if len(counter) > max_distinct:
            print(f"--- {field!r}: {len(counter)} distinct values (free text, skipped)")
            continue
        print(f"--- {field!r}: {len(counter)} distinct")
        for v, c in counter.most_common():
            print(f"      {c:7d}  {v}")
        vocab[field] = dict(counter)

        vals = list(counter)
        near = [(a, b) for i, a in enumerate(vals) for b in vals[i + 1:] if similar(a, b)]
        for a, b in near:
            print(f"      ! near-duplicate: {a!r} ({counter[a]}) vs {b!r} ({counter[b]})")
        print()
    report["vocabulary"] = vocab


# --------------------------------------------------------------------------- #
# geometry (needs GDAL)
# --------------------------------------------------------------------------- #
def audit_geometry(root, report):
    hr("GEOMETRY")
    if not HAVE_GDAL:
        print("GDAL not importable - run under the QGIS interpreter for this section:")
        print(r'  "C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" audit_workspace.py')
        return

    import math
    kinds = collections.Counter()
    lengths = collections.Counter()
    open_rings, closed_rings, gaps = 0, 0, []
    degenerate = []
    ring_candidates = collections.defaultdict(
        lambda: {"total": 0, "near": 0, "gaps": []})

    for n in sorted(os.listdir(root)):
        if not n.lower().endswith(".shp"):
            continue
        try:
            ds = ogr.Open(os.path.join(root, n))
            lyr = ds.GetLayer(0)
        except Exception:
            continue
        gt = ogr.GeometryTypeToName(lyr.GetGeomType())
        kinds[gt] += 1
        for feat in lyr:
            g = feat.GetGeometryRef()
            if g is None:
                continue
            if g.GetGeometryName() == "LINESTRING":
                L = g.Length()
                lengths[gt] += L
                if L < 0.5:
                    degenerate.append((n, feat.GetFID(), round(L, 3)))
                pc = g.GetPointCount()
                if pc > 3:
                    x0, y0 = g.GetPoint_2D(0)
                    x1, y1 = g.GetPoint_2D(pc - 1)
                    d = math.hypot(x1 - x0, y1 - y0)
                    if d == 0:
                        closed_rings += 1
                    else:
                        open_rings += 1
                        gaps.append(d)
                    stat = ring_candidates[n]
                    stat["total"] += 1
                    if L > 0 and d / L < 0.01:
                        stat["near"] += 1
                        stat["gaps"].append(d)
        ds = None

    print("layers by geometry type:")
    for k, v in kinds.most_common():
        extra = f"   total length {lengths[k]/1000:.2f} km" if lengths[k] else ""
        print(f"  {v:4d}  {k}{extra}")

    # A cable is a line that goes somewhere; a boundary is a line that comes
    # back to where it started. Judge by how small the gap is relative to the
    # perimeter, so open boundaries are not buried among thousands of cables.
    ring_files = {f: g for f, g in ring_candidates.items()
                  if g["near"] and g["near"] / g["total"] > 0.5}
    if ring_files:
        allgaps = sorted(g for f in ring_files for g in ring_candidates[f]["gaps"])
        print(f"\nRING CANDIDATES: {len(ring_files)} layer(s) whose lines almost close")
        print("  (gap under 1% of perimeter - these read as area boundaries drawn"
              " as lines)")
        if allgaps:
            print(f"  closure gap  min={allgaps[0]:.2f} m"
                  f"  median={allgaps[len(allgaps)//2]:.2f} m"
                  f"  max={allgaps[-1]:.2f} m")
            print("  A gap this small is a drawing slip, not design intent: these can")
            print("  be closed into polygons on a tolerance rather than redrawn, which")
            print("  is what makes area and point-in-area queries possible.")
            worst = sorted(((max(ring_candidates[f]['gaps']), f) for f in ring_files),
                           reverse=True)[:3]
            for g, f in worst:
                print(f"      widest: {f}  {g:.2f} m")
    elif closed_rings:
        print(f"\nline rings: {closed_rings} already closed")

    if degenerate:
        print(f"\n! {len(degenerate)} segment(s) shorter than 0.5 m:")
        for n, fid, L in degenerate[:8]:
            print(f"    {n} fid={fid} len={L} m")

    report["geometry"] = {
        "types": dict(kinds),
        "length_km": {k: round(v / 1000, 3) for k, v in lengths.items()},
        "open_rings": open_rings, "closed_rings": closed_rings,
        "degenerate": len(degenerate),
    }


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", nargs="?", default=".")
    ap.add_argument("--json", help="also write the findings as JSON")
    args = ap.parse_args()

    root = os.path.abspath(args.workspace)
    if not os.path.isdir(root):
        sys.exit(f"not a directory: {root}")

    report = {"workspace": root, "gdal": HAVE_GDAL}
    print(f"workspace: {root}")

    proj, xml = read_project(root)
    if xml:
        print(f"project  : {os.path.basename(proj)}")
        audit_project(xml, report)
        every = audit_paths(xml, root, report)
        audit_files(every, root, report)
    else:
        print("! no .qgz or .qgs found - auditing shapefiles only")
        report["project"] = None

    audit_crs(root, report)
    audit_schemas(root, report)
    audit_vocabulary(root, report)
    audit_geometry(root, report)

    hr("NEXT")
    print("Work through docs/RUNBOOK.md in order. Do not skip the")
    print("baseline commit: every later step assumes one git revert undoes it.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\nJSON written: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
