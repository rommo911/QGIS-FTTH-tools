r"""
Repoint every layer in the QGIS project from its shapefile to the GeoPackage.

After this the 820 shapefiles are dead weight and can be deleted, leaving the
project, the GeoPackage and the tools.

What has to be rewritten, and why each matters
----------------------------------------------
1. **The datasource.** `./thawra_b01_sites.shp` becomes
   `./idlib_ftth.gpkg|layername=site` plus a subset filter restricting it to
   that block, so the sector/block group tree and its per-layer styling survive
   intact. One file, same 172 layers, same map.

2. **Field references inside the styling.** The migration renamed columns, so
   every reference to an old name has to move with it or the layer renders
   with a default symbol and no labels. Three places carry them:
   `attr="..."` on categorized renderers (49 of them), `fieldName="..."` on
   labeling (39), and `filter="..."` on rule-based renderers (387). The values
   inside those filters are unchanged, because `type_raw` holds the original
   string byte-for-byte.

3. **Boundary geometry.** `block` is a polygon, but the boundary layers are
   styled with line symbols. They are pointed at `block_line`, which keeps the
   boundary exactly as drawn, so the outlines look identical.

Nothing about feature data changes; this only edits the project container.

Usage
-----
    python tools/cutover_to_gpkg.py [--dry-run]

Verify with tools/validate_project.py, which must still report every layer
valid and the same feature count, before deleting any shapefile.
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
import zipfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Which GeoPackage table each migrated layer type lives in.
TABLE_OF = {
    "sites": "site",
    "cables": "cable",
    "cablecount": "cable_count",
    "boundary": "block_line",   # line geometry, to keep line symbology
    "cabinet": "cabinet",
}

# Layers with no sector/block that still came from a shapefile.
TABLE_BY_ID = {
    "idlib_feeder_main": "feeder_main",
}

# Old shapefile column -> GeoPackage column, for references inside styling.
# Built from config/vocabulary.json field_aliases, plus the id we preserved.
EXTRA_FIELD_MAP = {"id": "legacy_id"}


SECTOR_CODE = {}


def load_sector_codes():
    with open(os.path.join(ROOT, "config", "vocabulary.json"), encoding="utf-8") as fh:
        for spec in json.load(fh)["sectors"]:
            SECTOR_CODE[spec["slug"]] = spec["sector_code"]


def load_field_maps():
    """table -> {old column: new column}.

    Deliberately NOT merged into one dict: cable_count maps "type" to
    count_raw while site and cable map it to type_raw, so a merged map
    silently rewrites every site layer to a column that does not exist there.
    """
    with open(os.path.join(ROOT, "config", "vocabulary.json"), encoding="utf-8") as fh:
        vocab = json.load(fh)
    maps = {}
    for table, aliases in vocab["field_aliases"].items():
        m = dict(EXTRA_FIELD_MAP)
        m.update(aliases)
        maps[table] = m
    for table in ("block_line", "cabinet", "feeder_main"):
        maps.setdefault(table, dict(EXTRA_FIELD_MAP))
    return maps


def load_manifest():
    """layer_id -> (sector, block, layer_type) from the rename manifest."""
    path = os.path.join(ROOT, "docs", "layers.csv")
    if not os.path.exists(path):
        sys.exit("docs/layers.csv not found - run tools/rename_to_ascii.py first")
    out = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["layer_id"]] = row
    return out


def remap_fields(fragment, field_map):
    """Rewrite old column names inside style attributes of one <maplayer>.

    Lookup is case-insensitive, matching QGIS itself: the project labels two
    cable-count layers on "Type" where the shapefile column is "type", and
    QGIS resolved that happily. A case-sensitive remap would silently turn
    those two labels off while their ten siblings kept theirs.
    """
    field_map = {k.lower(): v for k, v in field_map.items()}
    n = 0

    def sub_attr(m):
        nonlocal n
        old = m.group(2)
        new = field_map.get(old.lower())
        if new and new != old:
            n += 1
            return f'{m.group(1)}="{new}"'
        return m.group(0)

    fragment = re.sub(r'\b(attr|fieldName)="([^"]*)"', sub_attr, fragment)

    # Rule filters reference columns either as &quot;name&quot; or bare. Value
    # literals are single-quoted and must never be touched, so those are cut
    # out first and stitched back afterwards.
    def sub_filter(m):
        nonlocal n
        body = m.group(1)
        parts = re.split(r"('(?:[^']|'')*')", body)   # odd indices are literals

        for i in range(0, len(parts), 2):
            seg = parts[i]

            def quoted(mm):
                nonlocal n
                new = field_map.get(mm.group(1).lower())
                if new and new != mm.group(1):
                    n += 1
                    return f"&quot;{new}&quot;"
                return mm.group(0)

            seg = re.sub(r"&quot;([^&]+)&quot;", quoted, seg)

            for old in sorted(field_map, key=len, reverse=True):
                new = field_map[old]
                if new == old or not re.fullmatch(r"\w+", old):
                    continue

                def bare(mm, _new=new):
                    nonlocal n
                    n += 1
                    return _new

                seg, k = re.subn(rf"(?<![\w&;]){re.escape(old)}(?![\w;])", bare, seg,
                                 flags=re.IGNORECASE)
            parts[i] = seg

        return 'filter="' + "".join(parts) + '"'

    fragment = re.sub(r'filter="([^"]*)"', sub_filter, fragment)
    return fragment, n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    qgz = next(iter(sorted(glob.glob(os.path.join(ROOT, "*.qgz")))), None)
    gpkg = next(iter(sorted(glob.glob(os.path.join(ROOT, "*.gpkg")))), None)
    if not qgz or not gpkg:
        sys.exit("need both a .qgz and a .gpkg in the workspace")
    gpkg_name = os.path.basename(gpkg)

    with zipfile.ZipFile(qgz) as z:
        member = [n for n in z.namelist() if n.lower().endswith(".qgs")][0]
        xml = z.read(member).decode("utf-8")
        others = [(n, z.read(n)) for n in z.namelist() if n != member]

    load_sector_codes()
    manifest = load_manifest()
    field_maps = load_field_maps()

    stats = Counter()
    skipped = []

    def convert(m):
        block = m.group(0)
        lid = re.search(r"<id>([^<]+)</id>", block)
        if not lid:
            return block
        lid = lid.group(1)
        row = manifest.get(lid)
        old_file = (row or {}).get("old_name_file") or (row or {}).get("old_file") or ""
        if row is None or not old_file:
            # Basemaps and KMZ reference layers were never shapefiles and stay
            # exactly as they are.
            stats["left_alone"] += 1
            return block

        table = TABLE_OF.get(row["layer_type"]) or TABLE_BY_ID.get(lid)
        if table is None:
            skipped.append((lid, row["layer_type"]))
            return block

        # Scope the layer back to its own block or sector, so the group tree
        # and its per-layer styling keep meaning exactly what they meant when
        # each layer was a separate file. QGIS stores this inline in the URI.
        code = SECTOR_CODE.get(row["sector"])
        if row["block"] and code:
            subset = f"\"block_id\" = '{code}-B{int(row['block']):02d}'"
        elif code:
            subset = f"\"sector_code\" = '{code}'"
        else:
            subset = None

        uri = f"./{gpkg_name}|layername={table}"
        if subset:
            uri += f"|subset={subset}"
        # The URI lands in an XML text node and in an attribute, so quote it.
        esc = uri.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        attr_esc = esc.replace('"', "&quot;")

        block = re.sub(r"<datasource>.*?</datasource>",
                       lambda _m: f"<datasource>{esc}</datasource>", block, flags=re.S)
        block = re.sub(r'(\bsource=")[^"]*(")',
                       lambda _m: f'source="{attr_esc}"', block)

        block, nfields = remap_fields(block, field_maps.get(table, EXTRA_FIELD_MAP))
        stats["repointed"] += 1
        stats["fields_remapped"] += nfields
        return block

    new_xml = re.sub(r"<maplayer\b.*?</maplayer>", convert, xml, flags=re.S)

    print(f"project        : {os.path.basename(qgz)}")
    print(f"geopackage     : {gpkg_name}")
    print(f"layers repointed: {stats['repointed']}")
    print(f"left alone      : {stats['left_alone']}  (basemaps, KMZ reference)")
    print(f"field refs remapped: {stats['fields_remapped']}")
    if skipped:
        print(f"\n! {len(skipped)} layer(s) had no table mapping:")
        for lid, t in skipped[:10]:
            print(f"    {lid}  type={t}")
        return 1

    if args.dry_run:
        print("\ndry-run: nothing written")
        return 0

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(qgz, f"{qgz}.{stamp}.bak")
    tmp = qgz + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, new_xml.encode("utf-8"))
        for n, d in others:
            z.writestr(n, d)
    os.replace(tmp, qgz)
    print(f"\nwritten        : {os.path.basename(qgz)}")
    print("Now run tools/validate_project.py before deleting any shapefile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
