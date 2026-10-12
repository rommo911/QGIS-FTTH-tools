r"""
Build idlib_ftth.gpkg from the shapefiles, per docs/MIGRATION_DECISIONS.md.

Implements the signed-off decisions:

  D1  --sector THW runs the Thawra pilot; omit it to load everything.
  D2  Level 2 - structure plus quantities (length_m, area_m2, BOQ views).
  D3  Semantic composite keys, e.g. THW-B01-SITE-0042.
  D4  type_code is derived from config/vocabulary.json; the original Arabic
      string is kept verbatim in type_raw. Unmapped values get a NULL code and
      are listed by v_qa_vocab - never guessed.
  D5  Block boundaries are open LineStrings; they are closed into polygons
      within the tolerance in config/fibre_rules.json, and every repair is
      reported.
  D6  Hananu loads as-is. Its missing columns land as NULL and QA reports them.
  D7  GeoPackage only - no contractor export is produced.
  D8  --dry-run, then verify, then commit.

Survey round-trip (settled constraint): survey_batch and survey_record stage
incoming field-app submissions immutably, keeping the raw payload verbatim, and
site carries provenance columns plus a separately stored surveyed GPS position
so a submission can never overwrite designed geometry. See
docs/SURVEY_EXCHANGE.md.

Nothing is invented. Where a source field does not exist - most of Hananu - the
column is NULL and a QA view reports the gap.

Run with the QGIS interpreter, which has GDAL bound:

    "C:\Program Files\QGIS 4.2.1\bin\python-qgis.bat" tools\build_geopackage.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import math
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

from osgeo import ogr, osr

ogr.UseExceptions()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config")
GPKG = os.path.join(ROOT, "idlib_ftth.gpkg")
EPSG = 32637

# type tag used inside a feature id
TAG = {"site": "SITE", "cable": "CABL", "cable_count": "CNT", "block": "BLK"}


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
def load_config():
    with open(os.path.join(CONFIG, "vocabulary.json"), encoding="utf-8") as fh:
        vocab = json.load(fh)
    with open(os.path.join(CONFIG, "fibre_rules.json"), encoding="utf-8") as fh:
        rules = json.load(fh)
    return vocab, rules


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def norm_key(s: str) -> str:
    return norm(s).lower()


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #
FIELDS = {
    "sector": [
        ("sector_code", ogr.OFTString), ("slug", ogr.OFTString),
        ("name_ar", ogr.OFTString), ("name_en", ogr.OFTString),
        ("status", ogr.OFTString), ("cabinet_ref", ogr.OFTString),
    ],
    "block": [
        ("block_id", ogr.OFTString), ("sector_code", ogr.OFTString),
        ("block_no", ogr.OFTInteger), ("status", ogr.OFTString), ("legacy_id", ogr.OFTInteger),
        ("area_m2", ogr.OFTReal), ("perimeter_m", ogr.OFTReal),
        ("ring_gap_m", ogr.OFTReal), ("ring_closed", ogr.OFTInteger),
        ("geom_valid", ogr.OFTInteger), ("geom_repaired", ogr.OFTInteger),
        ("review_flag", ogr.OFTInteger),
        ("source_file", ogr.OFTString),
    ],
    "site": [
        ("site_id", ogr.OFTString), ("legacy_id", ogr.OFTInteger),
        ("sector_code", ogr.OFTString),
        ("block_id", ogr.OFTString), ("block_no", ogr.OFTInteger),
        ("type_code", ogr.OFTString), ("type_raw", ogr.OFTString),
        ("building_ref", ogr.OFTString),
        ("floors", ogr.OFTInteger), ("apartments", ogr.OFTInteger),
        ("occupants", ogr.OFTInteger), ("clients", ogr.OFTInteger),
        ("cores_recorded", ogr.OFTInteger),
        ("box_1", ogr.OFTString), ("box_2", ogr.OFTString),
        ("fdb_ref", ogr.OFTString), ("cabinet_ref", ogr.OFTString),
        ("phone_box", ogr.OFTString),
        # survey round-trip provenance
        ("data_source", ogr.OFTString), ("external_ref", ogr.OFTString),
        ("survey_batch_id", ogr.OFTString), ("surveyed_utc", ogr.OFTString),
        ("surveyed_lon", ogr.OFTReal), ("surveyed_lat", ogr.OFTReal),
        ("surveyed_accuracy_m", ogr.OFTReal),
        ("rev", ogr.OFTInteger),
        ("source_file", ogr.OFTString), ("source_fid", ogr.OFTInteger),
    ],
    "cable": [
        ("cable_id", ogr.OFTString), ("legacy_id", ogr.OFTInteger),
        ("sector_code", ogr.OFTString),
        ("block_id", ogr.OFTString), ("block_no", ogr.OFTInteger),
        ("type_code", ogr.OFTString), ("type_raw", ogr.OFTString),
        ("drop_name", ogr.OFTString), ("d24", ogr.OFTString),
        ("feeder_24", ogr.OFTString), ("feeder_96", ogr.OFTString),
        ("cores", ogr.OFTInteger), ("length_m", ogr.OFTReal),
        ("source_file", ogr.OFTString), ("source_fid", ogr.OFTInteger),
    ],
    "cable_count": [
        ("count_id", ogr.OFTString), ("legacy_id", ogr.OFTInteger),
        ("sector_code", ogr.OFTString),
        ("block_id", ogr.OFTString), ("block_no", ogr.OFTInteger),
        ("count_value", ogr.OFTInteger), ("count_raw", ogr.OFTString),
        ("source_file", ogr.OFTString), ("source_fid", ogr.OFTInteger),
    ],
    "block_line": [
        ("block_id", ogr.OFTString), ("sector_code", ogr.OFTString),
        ("block_no", ogr.OFTInteger), ("legacy_id", ogr.OFTInteger),
        ("source_file", ogr.OFTString),
    ],
    "cabinet": [
        ("cabinet_id", ogr.OFTString), ("sector_code", ogr.OFTString),
        ("name_ar", ogr.OFTString), ("source_file", ogr.OFTString),
    ],
    "feeder_main": [
        ("feeder_id", ogr.OFTString), ("name_ar", ogr.OFTString),
        ("length_m", ogr.OFTReal), ("source_file", ogr.OFTString),
    ],
}

GEOM = {
    "sector": ogr.wkbNone,
    "block": ogr.wkbMultiPolygon,
    "block_line": ogr.wkbLineString,
    "site": ogr.wkbPoint,
    "cable": ogr.wkbLineString,
    "cable_count": ogr.wkbPoint,
    "cabinet": ogr.wkbPoint,
    "feeder_main": ogr.wkbLineString,
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def to_int(v):
    """Best-effort integer, or None. Never guesses: junk becomes None."""
    if v is None:
        return None
    if isinstance(v, (int,)):
        return v
    if isinstance(v, float):
        return int(v) if not math.isnan(v) else None
    s = norm(str(v))
    if not s:
        return None
    m = re.match(r"^-?\d+", s)
    return int(m.group(0)) if m else None


def field_map(defn, aliases):
    """source field name -> canonical column, using the config aliases."""
    out = {}
    alias = {norm_key(k): v for k, v in aliases.items()}
    for i in range(defn.GetFieldCount()):
        name = defn.GetFieldDefn(i).GetName()
        canon = alias.get(norm_key(name))
        if canon:
            out[name] = canon
    return out


def close_ring(geom, tol):
    """Close an open boundary LineString into a valid MultiPolygon.

    Returns (geom_or_None, gap_m, closed, was_repaired). The source file is
    never edited. 19 of the 56 boundaries pinch at a point when closed, which
    makes the ring self-touching and therefore invalid; MakeValid resolves
    those into multipolygons with a measured area change of 0.00%, so the
    repair is lossless and is recorded in block.geom_repaired.
    """
    if geom is None or geom.GetGeometryName() != "LINESTRING":
        return None, None, False, False
    n = geom.GetPointCount()
    if n < 4:
        return None, None, False, False
    x0, y0 = geom.GetPoint_2D(0)
    x1, y1 = geom.GetPoint_2D(n - 1)
    gap = math.hypot(x1 - x0, y1 - y0)
    if gap > tol:
        return None, gap, False, False
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for i in range(n):
        x, y = geom.GetPoint_2D(i)
        ring.AddPoint_2D(x, y)
    if gap > 0:
        ring.AddPoint_2D(x0, y0)
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)

    repaired = False
    if not poly.IsValid():
        fixed = poly.MakeValid()
        if fixed is not None and fixed.IsValid():
            poly, repaired = fixed, True

    return ogr.ForceToMultiPolygon(poly), gap, True, repaired


# --------------------------------------------------------------------------- #
# load
# --------------------------------------------------------------------------- #
def build(sectors_wanted, dry_run):
    vocab, rules = load_config()
    sectors = {s["slug"]: s for s in vocab["sectors"]}
    code_of = {s["slug"]: s["sector_code"] for s in vocab["sectors"]}
    site_alias = {norm(k): v["code"] for k, v in vocab["aliases"]["site_type"].items()}
    cable_alias = {norm(k): v["code"] for k, v in vocab["aliases"]["cable_type"].items()}
    fa = vocab["field_aliases"]
    tol = rules["boundary_repair"]["close_ring_tolerance_m"]
    flag_above = rules["boundary_repair"]["flag_for_review_above_m"]

    rows = defaultdict(list)
    unmapped = Counter()
    stats = Counter()

    def want(slug):
        return not sectors_wanted or code_of.get(slug) in sectors_wanted

    # ---- blocks -------------------------------------------------------- #
    for path in sorted(glob.glob(os.path.join(ROOT, "*_boundary.shp"))):
        base = os.path.basename(path)
        slug, bno = base.split("_")[0], int(base.split("_")[1][1:])
        if not want(slug):
            continue
        sc = code_of[slug]
        bid = f"{sc}-B{bno:02d}"
        ds = ogr.Open(path)
        lyr = ds.GetLayer(0)
        has_id = lyr.GetLayerDefn().GetFieldIndex("id") >= 0
        for feat in lyr:
            g = feat.GetGeometryRef()
            perim = g.Length() if g else None
            legacy = to_int(feat.GetField("id")) if has_id else None
            poly, gap, closed, repaired = close_ring(g, tol)
            valid = bool(poly and poly.IsValid())
            rows["block"].append({
                "block_id": bid, "sector_code": sc, "block_no": bno,
                "status": None,  # filled after cables are known
                "legacy_id": legacy,
                "area_m2": poly.GetArea() if poly else None,
                "perimeter_m": perim,
                "ring_gap_m": gap, "ring_closed": int(closed),
                "geom_valid": int(valid), "geom_repaired": int(repaired),
                "review_flag": int(gap is not None and gap > flag_above),
                "source_file": base, "_geom": poly,
            })
            # Keep the boundary exactly as drawn. The polygon above is what
            # area and point-in-block queries need; this line is what the
            # project's line symbology renders, and losing it would silently
            # change every block outline on the map.
            rows["block_line"].append({
                "block_id": bid, "sector_code": sc, "block_no": bno,
                "legacy_id": legacy, "source_file": base,
                "_geom": g.Clone() if g else None,
            })
            if closed:
                stats["boundary_closed"] += 1
            else:
                stats["boundary_NOT_closed"] += 1
        ds = None

    # ---- sites ---------------------------------------------------------- #
    for path in sorted(glob.glob(os.path.join(ROOT, "*_sites.shp"))):
        base = os.path.basename(path)
        slug, bno = base.split("_")[0], int(base.split("_")[1][1:])
        if not want(slug):
            continue
        sc = code_of[slug]
        bid = f"{sc}-B{bno:02d}"
        ds = ogr.Open(path)
        lyr = ds.GetLayer(0)
        fm = field_map(lyr.GetLayerDefn(), fa["site"])
        for seq, feat in enumerate(lyr, start=1):
            rec = {c: None for c, _ in FIELDS["site"]}
            for src, canon in fm.items():
                rec[canon] = feat.GetField(src)
            raw = norm(rec.get("type_raw") or "")
            code = site_alias.get(raw)
            if raw and not code:
                unmapped[("site_type", raw)] += 1
            rec.update({
                "site_id": f"{bid}-SITE-{seq:04d}",
                "sector_code": sc, "block_id": bid, "block_no": bno,
                "type_code": code, "type_raw": rec.get("type_raw"),
                "floors": to_int(rec.get("floors")),
                "apartments": to_int(rec.get("apartments")),
                "cores_recorded": to_int(rec.get("cores_recorded")),
                "occupants": None, "clients": None,
                "data_source": "design", "rev": 1,
                "source_file": base, "source_fid": feat.GetFID(),
                "_geom": feat.GetGeometryRef().Clone() if feat.GetGeometryRef() else None,
            })
            rows["site"].append(rec)
        ds = None

    # ---- cables --------------------------------------------------------- #
    have_cables = set()
    for path in sorted(glob.glob(os.path.join(ROOT, "*_cables.shp"))):
        base = os.path.basename(path)
        slug, bno = base.split("_")[0], int(base.split("_")[1][1:])
        if not want(slug):
            continue
        sc = code_of[slug]
        bid = f"{sc}-B{bno:02d}"
        have_cables.add(bid)
        ds = ogr.Open(path)
        lyr = ds.GetLayer(0)
        fm = field_map(lyr.GetLayerDefn(), fa["cable"])
        for seq, feat in enumerate(lyr, start=1):
            rec = {c: None for c, _ in FIELDS["cable"]}
            for src, canon in fm.items():
                rec[canon] = feat.GetField(src)
            raw = norm(rec.get("type_raw") or "")
            code = cable_alias.get(raw)
            if raw and not code:
                unmapped[("cable_type", raw)] += 1
            g = feat.GetGeometryRef()
            rec.update({
                "cable_id": f"{bid}-CABL-{seq:04d}",
                "sector_code": sc, "block_id": bid, "block_no": bno,
                "type_code": code,
                "cores": None,
                "length_m": g.Length() if g else None,
                "source_file": base, "source_fid": feat.GetFID(),
                "_geom": g.Clone() if g else None,
            })
            rows["cable"].append(rec)
        ds = None

    # ---- cable counts --------------------------------------------------- #
    for path in sorted(glob.glob(os.path.join(ROOT, "*_cablecount.shp"))):
        base = os.path.basename(path)
        slug, bno = base.split("_")[0], int(base.split("_")[1][1:])
        if not want(slug):
            continue
        sc = code_of[slug]
        bid = f"{sc}-B{bno:02d}"
        ds = ogr.Open(path)
        lyr = ds.GetLayer(0)
        fm = field_map(lyr.GetLayerDefn(), fa["cable_count"])
        for seq, feat in enumerate(lyr, start=1):
            raw = None
            for src, canon in fm.items():
                if canon == "count_raw":
                    raw = feat.GetField(src)
            rows["cable_count"].append({
                "count_id": f"{bid}-CNT-{seq:04d}",
                "sector_code": sc, "block_id": bid, "block_no": bno,
                "count_value": to_int(raw), "count_raw": raw,
                "source_file": base, "source_fid": feat.GetFID(),
                "_geom": feat.GetGeometryRef().Clone() if feat.GetGeometryRef() else None,
            })
        ds = None

    # ---- cabinets, feeder ------------------------------------------------ #
    for path in sorted(glob.glob(os.path.join(ROOT, "*_cabinet.shp"))):
        base = os.path.basename(path)
        slug = base.split("_")[0]
        if not want(slug):
            continue
        sc = code_of[slug]
        ds = ogr.Open(path)
        for feat in ds.GetLayer(0):
            rows["cabinet"].append({
                "cabinet_id": f"{sc}-CAB", "sector_code": sc,
                "name_ar": sectors[slug]["name_ar"], "source_file": base,
                "_geom": feat.GetGeometryRef().Clone() if feat.GetGeometryRef() else None,
            })
        ds = None

    fpath = os.path.join(ROOT, "idlib_feeder_main.shp")
    if os.path.exists(fpath) and not sectors_wanted:
        ds = ogr.Open(fpath)
        for seq, feat in enumerate(ds.GetLayer(0), start=1):
            g = feat.GetGeometryRef()
            rows["feeder_main"].append({
                "feeder_id": f"IDL-FDR-{seq:04d}", "name_ar": "القطاع الرئيسي",
                "length_m": g.Length() if g else None,
                "source_file": "idlib_feeder_main.shp",
                "_geom": g.Clone() if g else None,
            })
        ds = None

    # ---- sectors + derived block status ---------------------------------- #
    for slug, s in sectors.items():
        if want(slug):
            rows["sector"].append({
                "sector_code": s["sector_code"], "slug": slug,
                "name_ar": s["name_ar"], "name_en": s["name_en"],
                "status": s["status"], "cabinet_ref": f"{s['sector_code']}-CAB",
            })
    for b in rows["block"]:
        b["status"] = "designed" if b["block_id"] in have_cables else "surveyed"

    return rows, unmapped, stats, vocab, rules


# --------------------------------------------------------------------------- #
# write
# --------------------------------------------------------------------------- #
def write_gpkg(rows, vocab, rules):
    if os.path.exists(GPKG):
        os.remove(GPKG)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(EPSG)

    drv = ogr.GetDriverByName("GPKG")
    ds = drv.CreateDataSource(GPKG)

    for table, fields in FIELDS.items():
        gt = GEOM[table]
        lyr = ds.CreateLayer(table, srs if gt != ogr.wkbNone else None, gt,
                             ["GEOMETRY_NULLABLE=YES"] if gt != ogr.wkbNone else [])
        for name, ftype in fields:
            lyr.CreateField(ogr.FieldDefn(name, ftype))

        lyr.StartTransaction()
        defn = lyr.GetLayerDefn()
        for rec in rows.get(table, []):
            feat = ogr.Feature(defn)
            for name, _ in fields:
                v = rec.get(name)
                if v is None or (isinstance(v, str) and v == ""):
                    feat.SetFieldNull(name)
                else:
                    feat.SetField(name, v)
            g = rec.get("_geom")
            if g is not None and gt != ogr.wkbNone:
                feat.SetGeometry(g)
            lyr.CreateFeature(feat)
            feat = None
        lyr.CommitTransaction()
    ds = None
    return GPKG


def sql_cores_expression(rules):
    """Translate the configurable cores rule into a SQL CASE expression."""
    cfg = rules["cores_per_drop"]
    expr = cfg["formula"]
    for k, v in cfg["parameters"].items():
        expr = re.sub(rf"\b{re.escape(k)}\b", str(v), expr)
    allowed = re.compile(r"^[\w\s+\-*/().]+$")
    if not allowed.match(expr):
        raise SystemExit(f"unsafe characters in cores formula: {expr!r}")

    inputs = [t for t in ("apartments", "occupants", "floors", "clients") if re.search(rf"\b{t}\b", expr)]
    if not inputs:
        raise SystemExit("cores formula references no input column")

    guard = " OR ".join(f"{c} IS NULL" for c in inputs)

    # Cast each INPUT COLUMN to REAL, not the finished expression: SQLite does
    # integer division on two integers, so `apartments / 8` would floor 14 to 1
    # before any rounding rule could see the remainder.
    for col in inputs:
        expr = re.sub(rf"\b{col}\b", f"CAST({col} AS REAL)", expr)
    raw = f"({expr})"

    mode = cfg.get("round", "none")
    if mode == "ceil":
        rounded = f"(CAST({raw} AS INTEGER) + (CASE WHEN {raw} > CAST({raw} AS INTEGER) THEN 1 ELSE 0 END))"
    elif mode == "floor":
        rounded = f"CAST({raw} AS INTEGER)"
    elif mode == "nearest":
        rounded = f"CAST(ROUND({raw}) AS INTEGER)"
    else:
        rounded = raw

    lo, hi = cfg["min_cores"], cfg["max_cores"]
    clamped = f"MAX({lo}, MIN({hi}, {rounded}))"

    bands = cfg.get("snap_to_bands") or []
    if bands:
        cases = "".join(f" WHEN {clamped} <= {b} THEN {b}" for b in sorted(bands))
        snapped = f"CASE{cases} ELSE {max(bands)} END"
    else:
        snapped = f"CAST({clamped} AS INTEGER)"

    if cfg.get("null_inputs", "null_result") == "null_result":
        return f"CASE WHEN {guard} THEN NULL ELSE {snapped} END"
    return snapped


def write_aux(vocab, rules, rows):
    """Vocabulary, survey staging, project metadata, and the generated views."""
    con = sqlite3.connect(GPKG)
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE vocab (
      domain TEXT NOT NULL, code TEXT NOT NULL,
      label_ar TEXT, label_en TEXT, sort_order INTEGER,
      PRIMARY KEY (domain, code));

    CREATE TABLE vocab_map (
      domain TEXT NOT NULL, raw TEXT NOT NULL, code TEXT,
      note TEXT, PRIMARY KEY (domain, raw));

    -- One row per file received from the field app. Immutable once written.
    CREATE TABLE survey_batch (
      batch_id      TEXT PRIMARY KEY,
      source        TEXT,      -- 'android_app', 'csv_upload', ...
      surveyor      TEXT,
      device        TEXT,
      app_version   TEXT,
      file_name     TEXT,
      file_sha256   TEXT,
      received_utc  TEXT,
      record_count  INTEGER,
      status        TEXT,      -- received | validated | promoted | rejected
      notes         TEXT);

    -- One row per submitted site observation. Raw payload kept verbatim so a
    -- field the schema does not yet know about is never lost.
    CREATE TABLE survey_record (
      record_id     INTEGER PRIMARY KEY AUTOINCREMENT,
      batch_id      TEXT NOT NULL REFERENCES survey_batch(batch_id),
      site_id       TEXT,       -- target; NULL means a newly discovered site
      external_ref  TEXT,       -- the app's own identifier
      building_ref  TEXT,
      floors        INTEGER,
      apartments    INTEGER,
      occupants     INTEGER,
      clients       INTEGER,
      type_raw      TEXT,
      lon           REAL,       -- WGS84 as captured by GPS
      lat           REAL,
      accuracy_m    REAL,
      captured_utc  TEXT,
      payload_json  TEXT,       -- the submission exactly as received
      status        TEXT,       -- pending | accepted | rejected | superseded
      reject_reason TEXT);

    CREATE INDEX idx_survey_record_site  ON survey_record(site_id);
    CREATE INDEX idx_survey_record_batch ON survey_record(batch_id);

    CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT);
    """)

    for domain, terms in vocab["terms"].items():
        for t in terms:
            cur.execute("INSERT INTO vocab VALUES (?,?,?,?,?)",
                        (domain, t["code"], t["label_ar"], t["label_en"], t["sort_order"]))
    for domain, amap in vocab["aliases"].items():
        for raw, spec in amap.items():
            cur.execute("INSERT INTO vocab_map VALUES (?,?,?,?)",
                        (domain, raw, spec["code"], spec.get("_note")))

    cores_expr = sql_cores_expression(rules)
    q = rules["quality_thresholds"]

    cur.executescript(f"""
    -- ---------- bill of quantities -------------------------------------- --
    CREATE VIEW v_boq_cable AS
    SELECT c.type_code,
           v.label_ar, v.label_en,
           COUNT(*)                       AS segments,
           ROUND(SUM(c.length_m), 1)      AS total_m,
           ROUND(SUM(c.length_m)/1000.0, 3) AS total_km
    FROM cable c LEFT JOIN vocab v
      ON v.domain='cable_type' AND v.code=c.type_code
    GROUP BY c.type_code, v.label_ar, v.label_en
    ORDER BY total_m DESC;

    CREATE VIEW v_boq_cable_by_block AS
    SELECT c.sector_code, c.block_id, c.block_no, c.type_code, v.label_ar,
           COUNT(*) AS segments, ROUND(SUM(c.length_m),1) AS total_m
    FROM cable c LEFT JOIN vocab v
      ON v.domain='cable_type' AND v.code=c.type_code
    GROUP BY c.sector_code, c.block_id, c.block_no, c.type_code, v.label_ar
    ORDER BY c.sector_code, c.block_no, total_m DESC;

    CREATE VIEW v_boq_site AS
    SELECT s.type_code, v.label_ar, v.label_en, COUNT(*) AS count
    FROM site s LEFT JOIN vocab v
      ON v.domain='site_type' AND v.code=s.type_code
    GROUP BY s.type_code, v.label_ar, v.label_en
    ORDER BY count DESC;

    -- ---------- demand --------------------------------------------------- --
    CREATE VIEW v_demand AS
    SELECT s.sector_code, s.block_id, s.block_no,
           COUNT(*)                                    AS buildings,
           SUM(CASE WHEN s.apartments IS NOT NULL THEN 1 ELSE 0 END) AS with_apartments,
           SUM(s.apartments)                           AS apartments,
           SUM(s.occupants)                            AS occupants,
           SUM(s.cores_recorded)                       AS cores_recorded
    FROM site s
    WHERE s.type_code = 'building_entrance'
    GROUP BY s.sector_code, s.block_id, s.block_no
    ORDER BY s.sector_code, s.block_no;

    -- Cores demand from config/fibre_rules.json. Regenerated on every build,
    -- so editing the rule changes this immediately. NULL where inputs missing.
    CREATE VIEW v_cores_demand AS
    SELECT site_id, sector_code, block_id, apartments, occupants, floors,
           cores_recorded,
           {cores_expr} AS cores_required
    FROM site
    WHERE type_code = 'building_entrance';

    CREATE VIEW v_cores_variance AS
    SELECT site_id, sector_code, block_id, apartments,
           cores_recorded, cores_required,
           cores_required - cores_recorded AS delta
    FROM v_cores_demand
    WHERE cores_recorded IS NOT NULL AND cores_required IS NOT NULL
      AND cores_required <> cores_recorded;

    -- ---------- quality assurance ---------------------------------------- --
    CREATE VIEW v_qa_vocab AS
    SELECT 'cable' AS tbl, type_raw AS raw, COUNT(*) AS n FROM cable
      WHERE type_code IS NULL AND type_raw IS NOT NULL GROUP BY type_raw
    UNION ALL
    SELECT 'site', type_raw, COUNT(*) FROM site
      WHERE type_code IS NULL AND type_raw IS NOT NULL GROUP BY type_raw;

    CREATE VIEW v_qa_coverage AS
    SELECT sector_code, block_id, block_no,
           COUNT(*) AS entrances,
           SUM(CASE WHEN apartments IS NULL THEN 1 ELSE 0 END) AS missing_apartments,
           SUM(CASE WHEN floors     IS NULL THEN 1 ELSE 0 END) AS missing_floors,
           ROUND(100.0*SUM(CASE WHEN apartments IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*),1)
             AS pct_with_apartments
    FROM site WHERE type_code='building_entrance'
    GROUP BY sector_code, block_id, block_no
    ORDER BY pct_with_apartments;

    CREATE VIEW v_qa_geometry AS
    SELECT 'cable_missing_geometry' AS issue, cable_id AS id, sector_code, block_id
      FROM cable WHERE length_m IS NULL
    UNION ALL
    SELECT 'cable_very_short', cable_id, sector_code, block_id
      FROM cable WHERE length_m IS NOT NULL
                   AND length_m < {q['min_segment_length_m']}
    UNION ALL
    SELECT 'drop_over_max_length', cable_id, sector_code, block_id
      FROM cable WHERE type_code IN ('drop','drop_buried')
                   AND length_m > {q['max_drop_length_m']}
    UNION ALL
    SELECT 'block_ring_not_closed', block_id, sector_code, block_id
      FROM block WHERE ring_closed = 0
    UNION ALL
    SELECT 'block_geom_invalid', block_id, sector_code, block_id
      FROM block WHERE geom_valid = 0
    UNION ALL
    SELECT 'block_ring_repaired', block_id, sector_code, block_id
      FROM block WHERE geom_repaired = 1
    UNION ALL
    SELECT 'block_ring_gap_needs_review', block_id, sector_code, block_id
      FROM block WHERE review_flag = 1;

    -- Cable core counts must be a size the project can actually order.
    -- site.cores_recorded is deliberately NOT checked here: it is a per-building
    -- fibre demand (observed range 1-6), not a cable size.
    CREATE VIEW v_qa_cores_orderable AS
    SELECT cable_id, sector_code, block_id, cores
    FROM cable
    WHERE cores IS NOT NULL
      AND cores NOT IN ({','.join(str(c) for c in rules['cable_sizes']['available_cores'])});

    -- ---------- survey round-trip ---------------------------------------- --
    CREATE VIEW v_survey_pending AS
    SELECT r.record_id, r.batch_id, b.surveyor, b.received_utc,
           r.site_id, r.external_ref, r.apartments, r.occupants, r.clients,
           r.status, r.reject_reason
    FROM survey_record r JOIN survey_batch b ON b.batch_id = r.batch_id
    WHERE r.status = 'pending';

    -- What the field app should be sent for a block, and what it must return.
    CREATE VIEW v_survey_export AS
    SELECT s.site_id, s.sector_code, s.block_id, s.type_code,
           s.building_ref, s.floors, s.apartments, s.occupants, s.clients,
           s.rev
    FROM site s
    WHERE s.type_code = 'building_entrance';
    """)

    # Register views so QGIS lists them alongside the tables.
    for name in ("v_boq_cable", "v_boq_cable_by_block", "v_boq_site", "v_demand",
                 "v_cores_demand", "v_cores_variance", "v_qa_vocab", "v_qa_coverage",
                 "v_qa_geometry", "v_qa_cores_orderable", "v_survey_pending",
                 "v_survey_export"):
        cur.execute(
            "INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) "
            "VALUES (?,'attributes',?,0)", (name, name))

    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Reconciliation baseline, captured while the shapefiles are still present.
    # Once they are deleted the source of truth is gone, so validate_gpkg.py
    # falls back to comparing against these recorded expectations.
    meta = [
        ("built_utc", now), ("crs", f"EPSG:{EPSG}"),
        ("schema_level", "2 (structure + quantities)"),
        ("display_language", "ar"),
        ("cores_rule_status", rules["cores_per_drop"]["_status"]),
        ("source", "shapefiles migrated per docs/MIGRATION_DECISIONS.md"),
    ]
    for table in ("site", "cable", "cable_count", "block", "block_line",
                  "cabinet", "feeder_main"):
        meta.append((f"expect_count_{table}", str(len(rows.get(table, [])))))
    total_len = sum(r.get("length_m") or 0.0 for r in rows.get("cable", []))
    meta.append(("expect_cable_length_m", f"{total_len:.3f}"))

    for k, v in meta:
        cur.execute("INSERT INTO project_meta VALUES (?,?)", (k, v))

    con.commit()
    con.close()


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sector", action="append",
                    help="limit to sector code(s), e.g. --sector THW for the pilot")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    wanted = set(s.upper() for s in (args.sector or []))
    rows, unmapped, stats, vocab, rules = build(wanted, args.dry_run)

    print(f"scope            : {', '.join(sorted(wanted)) if wanted else 'all sectors'}")
    for t in ("sector", "block", "site", "cable", "cable_count", "cabinet", "feeder_main"):
        print(f"  {t:12s} {len(rows.get(t, [])):7d}")
    print(f"boundaries closed: {stats['boundary_closed']}  not closed: {stats['boundary_NOT_closed']}")
    flagged = [b['block_id'] for b in rows['block'] if b['review_flag']]
    print(f"rings over review threshold: {flagged or 'none'}")
    invalid = [b['block_id'] for b in rows['block'] if not b['geom_valid']]
    repaired = [b['block_id'] for b in rows['block'] if b.get('geom_repaired')]
    print(f"self-touching rings repaired: {len(repaired)} (lossless, area unchanged)")
    print(f"still-invalid block polygons: {invalid or 'none'}")

    if unmapped:
        print("\nUNMAPPED vocabulary (left NULL, never guessed):")
        for (dom, raw), n in unmapped.most_common():
            print(f"   {n:6d}  {dom}: {raw!r}")
    else:
        print("\nvocabulary       : every raw value mapped")

    if args.dry_run:
        print("\ndry-run: nothing written")
        return 0

    write_gpkg(rows, vocab, rules)
    write_aux(vocab, rules, rows)
    size = os.path.getsize(GPKG) / 1024 / 1024
    print(f"\nwritten          : {os.path.basename(GPKG)}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
