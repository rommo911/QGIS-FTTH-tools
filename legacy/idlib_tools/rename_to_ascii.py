r"""
Migrate the Idlib FTTH project from Arabic filenames to ASCII identifiers.

Why
---
QGIS derives a layer's ID from its *name* by stripping non-ASCII characters.
Arabic layer names therefore collapse to IDs like `_______224320d5_2763_45f2...`
and `________10_67814c24...`, which carry no meaning and cannot be told apart.
On top of that the layer names themselves are duplicated - `المواقع` appears 29
times, and five names differ only by leading/trailing whitespace. The result is
that no script can address a layer by either ID or name.

What this does
--------------
1. Renames every shapefile sidecar (.shp/.shx/.dbf/.prj/.cpg/.qmd/...) to a
   deterministic ASCII basename:  <sector>_b<NN>_<type>
   e.g.  جامعة الكبلات 10  ->  jamaa_b10_cables
2. Rewrites each <maplayer><id> to that same ASCII string, so PyQGIS can do
   QgsProject.instance().mapLayer("jamaa_b10_cables").
3. Trims whitespace from layer names, collapsing the five whitespace-only
   variants. Names stay in Arabic: the legend still reads Arabic for the
   engineers, while scripts address layers by the new stable ID.
4. Writes docs/layers.csv - the machine-readable manifest tying id, Arabic
   name, sector, block, layer type, geometry and file together.

Layer IDs appear in six or seven places each (<maplayer><id>, layer-tree-layer,
layerorder, snapping-settings, the legacy <legend> block, and
ProjectGpsSettings). Rather than enumerate them, every old ID is replaced
throughout the document in a single regex pass, so no reference site can be
missed. The pass is single-shot with an alternation so a new ID can never be
re-matched as if it were an old one.

Usage
-----
    python tools/rename_to_ascii.py --dry-run     # print the plan, touch nothing
    python tools/rename_to_ascii.py               # apply

Always re-run tools/validate_project.py afterwards.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import re
import shutil
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SECTORS = {
    "قطاع الثورة": "thawra",
    "قطاع الجامعة": "jamaa",
    "قطاع هنانو": "hananu",
}

# Layers not tied to a sector/block get an explicit name.
STANDALONE = {
    "القطاع الرئيسي": "idlib_feeder_main",
    "الخزانات 7": "unused_cabinets_07",
}

# KMZ source files, and the sublayers drawn from them.
KMZ_FILES = {
    "قساطل وغرف تفتيش ادلب.kmz": "idlib_ducts_manholes.kmz",
    "غرف وقساطل جديدة-إدلب ftth.kmz": "idlib_ftth_new.kmz",
}


def layer_kind(basename: str) -> str | None:
    """Classify a shapefile basename into a logical layer type."""
    if "عدد الكبلات" in basename:
        return "cablecount"
    if "الكبلات" in basename:
        return "cables"
    if "المواقع" in basename or "مواقع" in basename:
        return "sites"
    if "حدود" in basename:
        return "boundary"
    if "مقسم" in basename:
        return "cabinet"
    return None


def kmz_layer_id(datasource: str, geometry: str | None) -> str:
    """Stable ASCII id for one sublayer of a KMZ."""
    src = datasource.split("|")[0]
    stem = "idlib_ftth_new" if "جديدة" in src else "idlib_ducts_manholes"
    sub = ""
    m = re.search(r"layername=([^|]*)", datasource)
    if m and "المياه" in m.group(1):
        sub = "_water"
    geo = {"Point": "pt", "Line": "ln", "Polygon": "pg"}.get(geometry or "", "nogeom")
    return f"{stem}{sub}_{geo}"


def build_plan(qgs_text: str):
    """Return (id_map, file_map, rows) without touching anything."""
    root = ET.fromstring(qgs_text)

    layers = {}
    for m in root.iter("maplayer"):
        layers[m.findtext("id")] = {
            "name": m.findtext("layername") or "",
            "datasource": (m.findtext("datasource") or ""),
            "geometry": m.get("geometry"),
            "provider": m.findtext("provider") or "",
        }

    # Walk the tree so each layer learns its sector and block.
    context: dict[str, list[str]] = {}

    def walk(node, path):
        for child in node:
            if child.tag == "layer-tree-group":
                walk(child, path + [child.get("name") or ""])
            elif child.tag == "layer-tree-layer":
                context[child.get("id")] = path

    walk(root.find("layer-tree-group"), [])

    id_map: dict[str, str] = {}
    file_map: dict[str, str] = {}
    rows: list[dict] = []

    for lid, info in layers.items():
        ds = info["datasource"]
        path = context.get(lid, [])
        sector = block = kind = None
        new_id = None
        old_base = None

        if info["provider"] == "wms":
            new_id = "basemap_" + re.sub(r"\W+", "_", info["name"]).strip("_").lower()
        elif ds.lower().split("|")[0].endswith(".kmz"):
            new_id = kmz_layer_id(ds, info["geometry"])
        else:
            # The basename exactly as it exists on disk today. One layer points
            # at a '<name> repaired' rebuild because its corrupt original could
            # not be overwritten; that rebuild is the file to rename, and the
            # corrupt original must be left alone as an orphan.
            old_base = ds.split("|")[0].rsplit("/", 1)[-1]
            old_base = old_base[:-4] if old_base.lower().endswith(".shp") else old_base
            kind = layer_kind(re.sub(r" repaired$", "", old_base))
            sector = SECTORS.get(path[1]) if len(path) > 1 else None
            if len(path) > 2:
                m = re.search(r"(\d+)", path[2])
                block = int(m.group(1)) if m else None

            plain = re.sub(r" repaired$", "", old_base)
            if plain in STANDALONE:
                new_id = STANDALONE[plain]
            elif sector and block and kind:
                new_id = f"{sector}_b{block:02d}_{kind}"
            elif sector and kind == "cabinet":
                new_id = f"{sector}_cabinet"

            if new_id is None:
                raise SystemExit(f"no rule for layer {info['name']!r} (source {ds!r})")
            file_map[old_base] = new_id

        id_map[lid] = new_id
        rows.append(
            {
                "layer_id": new_id,
                "name_ar": info["name"].strip(),
                "sector": sector or "",
                "block": block if block is not None else "",
                "layer_type": kind or ("basemap" if info["provider"] == "wms" else "reference"),
                "geometry": info["geometry"] or "",
                "file": f"{new_id}.shp" if old_base else ds.split("|")[0].lstrip("./"),
                "old_name_file": old_base or "",
                "old_layer_id": lid,
            }
        )

    dupes = {v for v in id_map.values() if list(id_map.values()).count(v) > 1}
    if dupes:
        raise SystemExit(f"id collision: {sorted(dupes)}")

    return id_map, file_map, rows


def rewrite_xml(text: str, id_map: dict[str, str], file_map: dict[str, str]) -> str:
    # 1. Layer IDs, single pass so a new id is never re-matched as an old one.
    pattern = re.compile("|".join(re.escape(k) for k in sorted(id_map, key=len, reverse=True)))
    text = pattern.sub(lambda m: id_map[m.group(0)], text)

    # 2. Datasource basenames. Longest first so 'الكبلات 1' cannot shadow
    #    'الكبلات 10'.
    for old in sorted(file_map, key=len, reverse=True):
        new = file_map[old]
        text = text.replace(f"./{old}.shp", f"./{new}.shp")

    # 2b. A shapefile's internal layer name follows its filename, so a
    #     '|layername=<arabic>' left over from before the rename no longer
    #     matches and the layer fails to open. KMZ sublayers genuinely need
    #     their layername= and are deliberately untouched.
    text = re.sub(
        r"\./([A-Za-z0-9_]+)\.shp\|layername=[^|<\"]*",
        lambda m: f"./{m.group(1)}.shp|layername={m.group(1)}",
        text,
    )

    for old_kmz, new_kmz in KMZ_FILES.items():
        text = text.replace(f"./{old_kmz}", f"./{new_kmz}")

    # 3. Trim whitespace-only variants of layer names.
    text = re.sub(
        r"<layername>(.*?)</layername>",
        lambda m: f"<layername>{m.group(1).strip()}</layername>",
        text,
        flags=re.S,
    )
    text = re.sub(
        r'(<layer-tree-layer\b[^>]*?\bname=")([^"]*)(")',
        lambda m: m.group(1) + m.group(2).strip() + m.group(3),
        text,
    )
    return text


def rename_files(file_map: dict[str, str], dry: bool) -> tuple[int, list[str]]:
    """Rename every sidecar of each shapefile. Returns (count, failures)."""
    moved, failed = 0, []
    on_disk = {unicodedata.normalize("NFC", p.name): p for p in ROOT.iterdir() if p.is_file()}

    for old, new in file_map.items():
        for name, path in list(on_disk.items()):
            stem, ext = os.path.splitext(name)
            if unicodedata.normalize("NFC", stem) != unicodedata.normalize("NFC", old):
                continue
            target = ROOT / f"{new}{ext}"
            if target.exists():
                failed.append(f"{name}: {target.name} already exists")
                continue
            if dry:
                moved += 1
                continue
            try:
                path.rename(target)
                moved += 1
            except OSError as exc:
                failed.append(f"{name}: {exc.strerror or exc}")

    for old_kmz, new_kmz in KMZ_FILES.items():
        src = ROOT / old_kmz
        if not src.exists():
            for name, path in on_disk.items():
                if unicodedata.normalize("NFC", name) == unicodedata.normalize("NFC", old_kmz):
                    src = path
                    break
        if src.exists() and not (ROOT / new_kmz).exists():
            if dry:
                moved += 1
            else:
                try:
                    src.rename(ROOT / new_kmz)
                    moved += 1
                except OSError as exc:
                    failed.append(f"{old_kmz}: {exc.strerror or exc}")

    return moved, failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    qgz = next(iter(sorted(ROOT.glob("*.qgz"))), None)
    if qgz is None:
        sys.exit("no .qgz found")

    with zipfile.ZipFile(qgz) as z:
        qgs_name = [n for n in z.namelist() if n.lower().endswith(".qgs")][0]
        text = z.read(qgs_name).decode("utf-8")
        others = [(n, z.read(n)) for n in z.namelist() if n != qgs_name]

    id_map, file_map, rows = build_plan(text)

    print(f"layers          : {len(id_map)}")
    print(f"shapefiles      : {len(file_map)}")
    print(f"id collisions   : none")
    print("\nsample mapping:")
    for r in sorted(rows, key=lambda r: r["layer_id"])[:8]:
        print(f"   {r['old_name_file'] or '(kmz/xyz)':32s} -> {r['layer_id']}")

    moved, failed = rename_files(file_map, args.dry_run)
    print(f"\nfiles renamed   : {moved}")
    if failed:
        print("failures:")
        for f in failed:
            print(f"   ! {f}")

    if args.dry_run:
        print("\ndry-run: nothing written")
        return 0

    new_text = rewrite_xml(text, id_map, file_map)

    leftover = [o for o in id_map if o in new_text]
    if leftover:
        print(f"\n! {len(leftover)} old id(s) still present, aborting")
        return 1

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(qgz, qgz.with_suffix(f".qgz.{stamp}.bak"))
    tmp = qgz.with_suffix(".qgz.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(qgs_name, new_text.encode("utf-8"))
        for n, d in others:
            z.writestr(n, d)
    tmp.replace(qgz)

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    with open(docs / "layers.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["layer_id"]))

    print(f"\nproject written : {qgz.name}")
    print(f"manifest        : docs/layers.csv ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
