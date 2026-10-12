r"""
Migrate a QGIS project from non-ASCII filenames to ASCII identifiers.

Why this matters more than it looks
-----------------------------------
QGIS derives a layer's ID from its NAME by stripping non-ASCII characters. A
project whose layers are named in Arabic (or Cyrillic, Greek, Chinese...) ends
up with IDs like `_______224320d5_2763_45f2_...` - the semantic part is gone.
Layer names are usually duplicated as well. The result is that no script can
address a layer by either ID or name, and the only unique key left is the file
path.

This rewrites filenames AND layer IDs to a deterministic ASCII scheme, while
leaving layer NAMES in their original language so the legend still reads
naturally to the people using it.

Configuration
-------------
All the language-specific matching lives in a naming config (default
config/naming.json next to the workspace). Nothing is hard-coded, so the same
script works for a project in any language. See templates/naming.template.json.

Usage
-----
    python rename_to_ascii.py [--config naming.json] [--dry-run]

Layer IDs appear in six or seven places each (<maplayer><id>, layer-tree-layer,
layerorder, snapping-settings, the legacy <legend> block, ProjectGpsSettings).
Rather than enumerate them, every old ID is replaced document-wide in one regex
pass, so no reference site can be missed.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import glob
import json
import os
import re
import shutil
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def load_config(root, explicit):
    path = explicit or os.path.join(root, "config", "naming.json")
    if not os.path.exists(path):
        sys.exit(f"naming config not found: {path}\n"
                 "Copy templates/naming.template.json and fill it in - the audit "
                 "report's group tree and filenames tell you what to put there.")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def classify(basename, types):
    """First matching layer type wins, so order the config most-specific first."""
    for spec in types:
        for needle in spec["match"]:
            if needle in basename:
                return spec["code"]
    return None


def build_plan(xml, cfg):
    root_el = ET.fromstring(xml)
    sectors = cfg["sectors"]
    types = cfg["layer_types"]
    standalone = cfg.get("standalone", {})
    kmz = cfg.get("kmz_files", {})
    block_re = re.compile(cfg.get("block_group_regex", r"(\d+)"))

    layers = {}
    for m in root_el.iter("maplayer"):
        layers[m.findtext("id")] = {
            "name": m.findtext("layername") or "",
            "ds": m.findtext("datasource") or "",
            "geom": m.get("geometry"),
            "provider": m.findtext("provider") or "",
        }

    context = {}

    def walk(node, path):
        for child in node:
            if child.tag == "layer-tree-group":
                walk(child, path + [child.get("name") or ""])
            elif child.tag == "layer-tree-layer":
                context[child.get("id")] = path

    tree = root_el.find("layer-tree-group")
    if tree is not None:
        walk(tree, [])

    id_map, file_map, rows, unresolved = {}, {}, [], []

    for lid, info in layers.items():
        ds, path = info["ds"], context.get(lid, [])
        head = ds.split("|")[0]
        sector = block = kind = None
        old_base = None
        new_id = None

        if info["provider"] == "wms" or head.startswith("crs="):
            new_id = "basemap_" + re.sub(r"\W+", "_", info["name"]).strip("_").lower()
        elif head.lower().endswith(".kmz"):
            stem = kmz.get(nfc(os.path.basename(head)), {}).get("id_stem", "reference")
            sub = re.search(r"layername=([^|]*)", ds)
            geo = {"Point": "pt", "Line": "ln", "Polygon": "pg"}.get(info["geom"] or "", "nogeom")
            tag = ""
            for needle, suffix in (cfg.get("kmz_sublayers") or {}).items():
                if sub and needle in sub.group(1):
                    tag = "_" + suffix
            new_id = f"{stem}{tag}_{geo}"
        else:
            old_base = os.path.basename(head)
            old_base = old_base[:-4] if old_base.lower().endswith((".shp", ".shx")) else old_base
            plain = re.sub(r"\s+\S+$", "", old_base) if old_base in standalone else old_base
            kind = classify(old_base, types)
            for group_name, slug in sectors.items():
                if len(path) > 1 and group_name in path[1]:
                    sector = slug
            if len(path) > 2:
                m = block_re.search(path[2])
                block = int(m.group(1)) if m else None

            if old_base in standalone:
                new_id = standalone[old_base]
            elif plain in standalone:
                new_id = standalone[plain]
            elif sector and block and kind:
                new_id = cfg["pattern_block"].format(sector=sector, block=block, type=kind)
            elif sector and kind:
                new_id = cfg["pattern_sector"].format(sector=sector, type=kind)

            if new_id is None:
                unresolved.append((info["name"], head, path))
                continue
            file_map[old_base] = new_id

        id_map[lid] = new_id
        rows.append({
            "layer_id": new_id, "name_original": info["name"].strip(),
            "sector": sector or "", "block": block if block is not None else "",
            "layer_type": kind or ("basemap" if info["provider"] == "wms" else "reference"),
            "geometry": info["geom"] or "",
            "file": f"{new_id}.shp" if old_base else os.path.basename(head),
            "old_file": old_base or "", "old_layer_id": lid,
        })

    dupes = [v for v in set(id_map.values()) if list(id_map.values()).count(v) > 1]
    return id_map, file_map, rows, unresolved, dupes


def rewrite_xml(xml, id_map, file_map, kmz):
    if id_map:
        pat = re.compile("|".join(re.escape(k) for k in sorted(id_map, key=len, reverse=True)))
        xml = pat.sub(lambda m: id_map[m.group(0)], xml)

    for old in sorted(file_map, key=len, reverse=True):
        new = file_map[old]
        for ext in (".shp", ".shx"):
            xml = xml.replace(f"./{old}{ext}", f"./{new}.shp")

    # A shapefile's internal layer name follows its filename, so a stale
    # |layername= left on a renamed .shp stops the layer opening. KMZ sublayers
    # legitimately keep theirs.
    xml = re.sub(r"\./([A-Za-z0-9_]+)\.shp\|layername=[^|<\"]*",
                 lambda m: f"./{m.group(1)}.shp|layername={m.group(1)}", xml)

    for old_kmz, spec in kmz.items():
        xml = xml.replace(f"./{old_kmz}", f"./{spec['new_name']}")

    # Collapse whitespace-only variants of layer names; the language is kept.
    xml = re.sub(r"<layername>(.*?)</layername>",
                 lambda m: f"<layername>{m.group(1).strip()}</layername>", xml, flags=re.S)
    xml = re.sub(r'(<layer-tree-layer\b[^>]*?\bname=")([^"]*)(")',
                 lambda m: m.group(1) + m.group(2).strip() + m.group(3), xml)
    return xml


def rename_files(root, file_map, kmz, dry):
    moved, failed = 0, []
    disk = {nfc(n): n for n in os.listdir(root) if os.path.isfile(os.path.join(root, n))}
    for old, new in file_map.items():
        for name in list(disk):
            stem, ext = os.path.splitext(name)
            if nfc(stem) != nfc(old):
                continue
            target = os.path.join(root, new + ext)
            if os.path.exists(target):
                failed.append(f"{name}: {new}{ext} already exists")
                continue
            if dry:
                moved += 1
                continue
            try:
                os.rename(os.path.join(root, disk[name]), target)
                moved += 1
            except OSError as exc:
                failed.append(f"{name}: {exc.strerror or exc}")
    for old_kmz, spec in kmz.items():
        src = os.path.join(root, disk.get(nfc(old_kmz), old_kmz))
        dst = os.path.join(root, spec["new_name"])
        if os.path.exists(src) and not os.path.exists(dst):
            if dry:
                moved += 1
            else:
                try:
                    os.rename(src, dst)
                    moved += 1
                except OSError as exc:
                    failed.append(f"{old_kmz}: {exc.strerror or exc}")
    return moved, failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = os.path.abspath(args.workspace)
    cfg = load_config(root, args.config)

    found = sorted(glob.glob(os.path.join(root, "*.qgz")))
    if not found:
        sys.exit("no .qgz found")
    qgz = found[0]
    with zipfile.ZipFile(qgz) as z:
        member = [n for n in z.namelist() if n.lower().endswith(".qgs")][0]
        xml = z.read(member).decode("utf-8")
        others = [(n, z.read(n)) for n in z.namelist() if n != member]

    id_map, file_map, rows, unresolved, dupes = build_plan(xml, cfg)

    print(f"layers          : {len(id_map)}")
    print(f"shapefiles      : {len(file_map)}")
    if dupes:
        print(f"\n! ID COLLISION - refusing to run: {sorted(dupes)}")
        print("  Two layers map to the same name. Add a rule to naming.json.")
        return 1
    if unresolved:
        print(f"\n! {len(unresolved)} layer(s) match no rule - refusing to run:")
        for name, head, path in unresolved[:10]:
            print(f"    {name!r}  group={path}  src={head}")
        print("  Add them to 'standalone' or extend 'layer_types' in naming.json.")
        return 1
    print("id collisions   : none")
    for r in sorted(rows, key=lambda r: r["layer_id"])[:6]:
        print(f"   {r['old_file'] or '(kmz/xyz)':34s} -> {r['layer_id']}")

    moved, failed = rename_files(root, file_map, cfg.get("kmz_files", {}), args.dry_run)
    print(f"\nfiles renamed   : {moved}")
    for f in failed:
        print(f"   ! {f}")

    if args.dry_run:
        print("\ndry-run: nothing written")
        return 0

    new_xml = rewrite_xml(xml, id_map, file_map, cfg.get("kmz_files", {}))
    leftover = [o for o in id_map if o in new_xml]
    if leftover:
        print(f"\n! {len(leftover)} old id(s) still present - aborting")
        return 1

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(qgz, f"{qgz}.{stamp}.bak")
    tmp = qgz + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, new_xml.encode("utf-8"))
        for n, d in others:
            z.writestr(n, d)
    os.replace(tmp, qgz)

    docs = os.path.join(root, "docs")
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "layers.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["layer_id"]))

    print(f"\nproject written : {os.path.basename(qgz)}")
    print(f"manifest        : docs/layers.csv ({len(rows)} rows)")
    print("\nNow re-run validate_project.py before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
