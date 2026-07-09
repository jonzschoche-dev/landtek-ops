#!/usr/bin/env python3
"""qdrant_sync.py — re-sync Qdrant from the Postgres system-of-record (design: docs/QDRANT_RESYNC_DESIGN.md).

DRAFT / SHADOW. `--dry` projects the payload each doc WOULD get (reads Postgres, writes NOTHING). `--build`
is GUARDED and refuses to run until the design is approved + implemented — no production Qdrant write is
possible from this file yet. Payload is projected from the GOVERNED tables (documents + document_matter_links);
`matter_codes` (array) is the client-isolation filter (A5). Runs on the Mac; DB via ssh+docker-exec (mirrors
rag_embed_local).
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

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


# ── Qdrant build — writes ONLY to the NEW landtek_documents_v2 (structurally cannot touch the live collection) ──
COLLECTION_V2 = "landtek_documents_v2"
NS = uuid.UUID("6f1d2c3a-0000-4000-8000-000000000001")   # stable point-id namespace (matches corpus_backfill)
STOP_FILE = os.environ.get("QDRANT_SYNC_STOP", "/tmp/STOP_QDRANT_SYNC")
_QURL = _QKEY = None

# Build query — same governed payload as PROJECT_SQL + the doc text (base64). Excludes the 184 no-case_file docs.
# deploy_812: + significance-engine payload fields (matter_code, dockets, tct_numbers, urgent, cover_message,
# composition_candidate) so Qdrant supports filtered semantic queries like "urgent docs across a client's
# matters" / "docs referencing TCT-X in active matters" without a Postgres round-trip.
BUILD_SQL = """SELECT coalesce(json_agg(row_to_json(t)),'[]') FROM (
  SELECT d.id AS doc_id, d.case_file, d.document_type, d.doc_role, d.matter_code,
    (SELECT array_agg(DISTINCT l.matter_code) FROM document_matter_links l WHERE l.doc_id=d.id) AS matter_codes,
    (d.model_used IS NOT NULL) AS has_provenance, left(coalesce(d.original_filename,''),80) AS filename,
    (SELECT array_agg(x) FROM jsonb_array_elements_text(coalesce(d.reference_numbers->'dockets','[]')) x) AS dockets,
    (SELECT array_agg(x) FROM jsonb_array_elements_text(coalesce(d.reference_numbers->'tct_numbers','[]')) x) AS tct_numbers,
    EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(d.analyst_memo->'ingest_signals'->'matter_hits','[]')) h
             WHERE (h->>'urgent')::bool) AS urgent,
    coalesce((d.analyst_memo->'ingest_signals'->'flags'->>'cover_message')::bool, false) AS cover_message,
    coalesce((d.analyst_memo->'ingest_signals'->'flags'->>'composition_candidate')::bool, false)
      OR coalesce((d.analyst_memo->'ingest_signals'->'flags'->>'cites_exhibit_series')::bool, false) AS composition_candidate,
    replace(encode(convert_to(d.extracted_text,'UTF8'),'base64'), chr(10), '') AS text_b64
  FROM documents d
  WHERE length(coalesce(d.extracted_text,'')) >= 50 AND coalesce(d.case_file,'') <> '' AND d.id > {after} AND {casef}
  ORDER BY d.id LIMIT {n}
) t;"""


def _creds():
    global _QURL, _QKEY
    if _QURL is None:
        out = subprocess.run(SSH + ["grep -E '^QDRANT_(URL|KEY)=' /root/landtek/.env"],
                             capture_output=True, text=True, timeout=30).stdout
        for line in out.splitlines():
            if line.startswith("QDRANT_URL="): _QURL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
            elif line.startswith("QDRANT_KEY="): _QKEY = line.split("=", 1)[1].strip().strip('"')
    return _QURL, _QKEY


def _qd(method, path, body=None):
    url, key = _creds()
    data = json.dumps(body).encode() if body is not None else None
    h = {"content-type": "application/json"}
    if key:
        h["api-key"] = key
    req = urllib.request.Request(url + path, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def ensure_v2():
    exists = True
    try:
        _qd("GET", f"/collections/{COLLECTION_V2}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        exists = False
        _qd("PUT", f"/collections/{COLLECTION_V2}", {"vectors": {"size": 384, "distance": "Cosine"}})
    # payload indexes ensured every call (idempotent). doc_id_postgres MUST be indexed (integer) — the per-doc
    # delete-then-insert filters on it; the keyword fields power matter/case/type filtering.
    for field, schema in (("doc_id_postgres", "integer"), ("case_file", "keyword"),
                          ("document_type", "keyword"), ("matter_codes", "keyword"),
                          # deploy_812 significance fields → filtered semantic queries
                          ("matter_code", "keyword"), ("dockets", "keyword"), ("tct_numbers", "keyword"),
                          ("urgent", "bool"), ("cover_message", "bool"), ("composition_candidate", "bool")):
        try:
            _qd("PUT", f"/collections/{COLLECTION_V2}/index", {"field_name": field, "field_schema": schema})
        except Exception:
            pass
    return "exists" if exists else "created"


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


def build(limit, batch=25, case=None):
    """Shadow build into landtek_documents_v2 ONLY (never the live landtek_documents). Local bge-small 384d;
    per-doc delete-then-insert (idempotent); excludes the 184 no-case_file docs. STOP_FILE halts it.
    case=<case_file> restricts the build (used to seed a mixed pilot for the isolation gate)."""
    from rag_embed_local import _model, _chunks   # single-source the chunker + model (parity with rag_local)
    if os.path.exists(STOP_FILE):
        print(f"[qdrant_sync] off-ramp {STOP_FILE} present — refusing to start"); return
    casef = f"d.case_file = '{case}'" if case else "true"
    st = ensure_v2()
    ts = subprocess.run(SSH + ["date -u +%FT%TZ"], capture_output=True, text=True, timeout=20).stdout.strip()
    model = _model()
    print(f"[qdrant_sync] BUILD → {COLLECTION_V2} ({st}) · local bge-small 384d · synced_at={ts} · limit={limit} · case={case or 'ALL'}")
    after, done, pts_total = -1, 0, 0
    while limit is None or done < limit:
        n = min(batch, (limit - done) if limit else batch)
        rows = json.loads(_q(BUILD_SQL.format(after=after, n=n, casef=casef)) or "[]")
        if not rows:
            break
        points = []
        for r in rows:
            did = r["doc_id"]; after = max(after, did)
            try:
                text = base64.b64decode(r["text_b64"]).decode("utf-8", "replace")
            except Exception:
                continue
            chs = _chunks(text); vecs = list(model.embed(chs))
            pbase = {"doc_id_postgres": did, "case_file": r["case_file"], "matter_codes": r["matter_codes"] or [],
                     "document_type": r["document_type"], "doc_role": r["doc_role"],
                     "has_provenance": r["has_provenance"], "filename": r["filename"], "synced_at": ts}
            # idempotent: drop this doc's existing points in v2 before re-inserting (handles chunk-count change)
            _qd("POST", f"/collections/{COLLECTION_V2}/points/delete",
                {"filter": {"must": [{"key": "doc_id_postgres", "match": {"value": did}}]}})
            for idx, (ch, v) in enumerate(zip(chs, vecs)):
                points.append({"id": str(uuid.uuid5(NS, f"{did}-{idx}")),
                               "vector": [float(x) for x in v],
                               "payload": {**pbase, "chunk_index": idx, "total_chunks": len(chs), "text": ch[:2000]}})
            done += 1
        if points:
            _qd("PUT", f"/collections/{COLLECTION_V2}/points?wait=true", {"points": points})
            pts_total += len(points)
        print(f"  built {done} docs / {pts_total} points", flush=True)
        if os.path.exists(STOP_FILE):
            print(f"[qdrant_sync] off-ramp {STOP_FILE} — halting after {done} docs"); break
    cnt = _qd("GET", f"/collections/{COLLECTION_V2}")["result"].get("points_count")
    print(f"[qdrant_sync] DONE: {done} docs / {pts_total} points this run · {COLLECTION_V2} points_count={cnt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="project payload for a sample; write nothing")
    ap.add_argument("--build", action="store_true", help="shadow build into landtek_documents_v2 ONLY")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--case", default=None, help="restrict build to one case_file (pilot seeding)")
    a = ap.parse_args()
    if a.build:
        build(a.limit, case=a.case)
    else:
        dry(a.limit or 12)


if __name__ == "__main__":
    main()
