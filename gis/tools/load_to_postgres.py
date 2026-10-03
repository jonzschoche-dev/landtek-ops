#!/usr/bin/env python3
"""Load a LandTek GIS tie point dataset into Postgres.

    python3 tools/load_to_postgres.py                       # dry run, prints counts
    python3 tools/load_to_postgres.py --apply
    python3 tools/load_to_postgres.py --apply --dsn "$PG_DSN"

Runs sql/001_gis_tiepoints.sql first (idempotent), then upserts on gp_id.

The upsert never touches provenance_level or the verified_* columns, so a
re-harvest cannot demote a row somebody already verified against a certified
monument description.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DDL = ROOT / "sql" / "001_gis_tiepoints.sql"
DEFAULT_CSV = ROOT / "datasets" / "ph-tiepoints-camarines-norte" / "exports" / "cn_tiepoints.csv"

COLUMNS = [
    "gp_id", "pointref", "lgu", "psgc_code", "source_locality", "municipality",
    "province", "province_psgc", "mon_type", "mon_type_label", "mon_no",
    "survey_project", "barrio", "variant", "prs92_lat", "prs92_lon",
    "wgs84_lat", "wgs84_lon", "ptm_zone", "ptm_east", "ptm_north",
    "ptm_check_resid_m", "source", "retrieved", "dataset_version", "legal_status",
]
UPDATABLE = [c for c in COLUMNS if c != "gp_id"]


def rows_from(path: Path) -> list[tuple]:
    out = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out.append(tuple((r[c] if r[c] != "" else None) for c in COLUMNS))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--dsn", default=os.environ.get("PG_DSN"))
    ap.add_argument("--apply", action="store_true", help="actually write; default is a dry run")
    ap.add_argument("--skip-ddl", action="store_true")
    a = ap.parse_args()

    rows = rows_from(a.csv)
    print(f"{a.csv}: {len(rows)} records", file=sys.stderr)
    if not a.apply:
        print("dry run - nothing written. Re-run with --apply.", file=sys.stderr)
        return 0
    if not a.dsn:
        print("no DSN. Pass --dsn or set PG_DSN.", file=sys.stderr)
        return 2

    import psycopg2
    from psycopg2.extras import execute_values

    sql = (
        f"INSERT INTO gis_tiepoints ({', '.join(COLUMNS)}) VALUES %s "
        f"ON CONFLICT (gp_id) DO UPDATE SET "
        + ", ".join(f"{c} = EXCLUDED.{c}" for c in UPDATABLE)
        + ", updated_at = now()"
    )

    with psycopg2.connect(a.dsn) as conn, conn.cursor() as cur:
        if not a.skip_ddl:
            cur.execute(DDL.read_text())
            print("DDL applied", file=sys.stderr)
        execute_values(cur, sql, rows, page_size=500)
        cur.execute("SELECT count(*), count(*) FILTER (WHERE provenance_level = 'verified') "
                    "FROM gis_tiepoints")
        total, verified = cur.fetchone()
    print(f"gis_tiepoints: {total} rows, {verified} verified "
          f"({total - verified} PENDING VERIFICATION)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
