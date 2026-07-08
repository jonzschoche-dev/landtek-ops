#!/usr/bin/env python3
"""qdrant_sync.py — re-sync Qdrant from the Postgres system-of-record (design: docs/QDRANT_RESYNC_DESIGN.md).

DRAFT / SHADOW. `--dry` projects the payload each doc WOULD get (reads Postgres, writes NOTHING). `--build`
is GUARDED and refuses to run until the design is approved + implemented — no production Qdrant write is
possible from this file yet. Payload is projected from the GOVERNED tables (documents + document_matter_links);
`matter_codes` (array) is the client-isolation filter (A5). Runs on the Mac; DB via ssh+docker-exec (mirrors
rag_embed_local).
"""
import argparse
import json
import subprocess
import sys

SSH = ["ssh", "-o", "ConnectTimeout=60", "root@100.85.203.58"]
PSQL = "docker exec -i n8n-postgres-1 psql -U n8n -d n8n -t -A"

# Payload projection — the single source of what each doc's Qdrant payload will look like (dry + build reuse it).
PROJECT_SQL = """SELECT coalesce(json_agg(row_to_json(t)), '[]') FROM (
  SELECT d.id AS doc_id_postgres,
         d.case_file,
         d.document_type,
         d.doc_role,
         (SELECT array_agg(DISTINCT l.matter_code) FROM document_matter_links l WHERE l.doc_id = d.id) AS matter_codes,
         (d.model_used IS NOT NULL) AS has_provenance,
         left(coalesce(d.original_filename, ''), 55) AS filename
  FROM documents d
  WHERE length(coalesce(d.extracted_text, '')) >= 50 AND {where}
  ORDER BY d.id LIMIT {n}
) t;"""


def _q(sql):
    r = subprocess.run(SSH + [PSQL], input=sql, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr[:200])
    return r.stdout.strip()


def project(where, n):
    return json.loads(_q(PROJECT_SQL.format(where=where, n=n)) or "[]")


def dry(limit):
    """Stratified sample so review sees matter_codes resolve on BOTH Paracale and non-Paracale docs."""
    half = max(3, limit // 2)
    par = project("d.case_file = 'Paracale-001'", half)
    other = project("d.case_file <> 'Paracale-001'", limit - half)
    print(f"=== DRY-RUN payload projection (NO writes) — {len(par)} Paracale + {len(other)} non-Paracale ===\n")
    for label, rows in (("PARACALE-001", par), ("NON-PARACALE", other)):
        print(f"----- {label} -----")
        for r in rows:
            print(json.dumps({
                "doc_id_postgres": r["doc_id_postgres"],
                "case_file": r["case_file"],
                "matter_codes": r["matter_codes"],            # ← the isolation filter (A5)
                "document_type": r["document_type"],
                "doc_role": r["doc_role"],
                "has_provenance": r["has_provenance"],
                "filename": r["filename"],
            }, ensure_ascii=False))
        print()
    # coverage of the isolation key across the whole corpus (not just the sample)
    allp = project("true", 100000)
    n = len(allp)
    no_mc = sum(1 for r in allp if not r["matter_codes"])
    no_cf = sum(1 for r in allp if not r["case_file"])
    print(f"[projection coverage] embeddable={n} · missing matter_codes={no_mc} ({100*no_mc//max(n,1)}%) · "
          f"missing case_file={no_cf}")


def build(*a, **k):
    print("[qdrant_sync] --build is GUARDED: the design (docs/QDRANT_RESYNC_DESIGN.md) is not yet approved/"
          "implemented. No production Qdrant write is possible from this file. Run --dry for the projection.")
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="project payload for a sample; write nothing")
    ap.add_argument("--build", action="store_true", help="GUARDED — refuses until approved")
    ap.add_argument("--limit", type=int, default=12)
    a = ap.parse_args()
    if a.build:
        build()
    else:
        dry(a.limit)


if __name__ == "__main__":
    main()
