#!/usr/bin/env python3
"""incorporation_status.py — governed visibility into data-incorporation status (Phase 3).

Single place to see how much of the corpus is actually CONNECTED (A41: all 5 ConnectivityGate signals),
how much has EARNED provenance, and where the backlog / stuck docs are — no ad-hoc SQL. Reads the
read-only views v_incorporation_status / v_doc_connectivity (migrations/deploy_766), whose predicates
MIRROR truth_tests/test_connected_document_count.py, so these numbers reconcile with the A41 truth test.

  python3 scripts/incorporation_status.py                 # phone-friendly snapshot (all matters)
  python3 scripts/incorporation_status.py --matter Paracale-001   # drill into one matter's missing signals
  python3 scripts/incorporation_status.py --log           # append today's snapshot to incorporation_log (trend)
  python3 scripts/incorporation_status.py --check         # assert the view reconciles with A41 (nonzero on drift)

Read-only except --log (one idempotent upsert/day). Creditless, no LLM.
"""
import argparse
import json
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _rows(cur):
    cur.execute("SELECT * FROM v_incorporation_status ORDER BY is_total DESC, total DESC")
    return cur.fetchall()


def _total_row(rows):
    return next((r for r in rows if r["is_total"] == 1), None)


def snapshot(cur):
    """Phone-friendly one-line-per-matter status, TOTAL first, key matters called out."""
    rows = _rows(cur)
    tot = _total_row(rows)
    if not tot:
        print("[incorporation] no data"); return
    print(f"[incorporation] CONNECTED {tot['connected']}/{tot['total']} ({tot['connected_pct']}%) "
          f"· provenance earned {tot['provenance_earned']} · stuck {tot['stuck_flagged']}")
    print("  matter            total  conn   %     prov  text  type  qual  embd  stuck")
    for r in rows:
        if r["is_total"] == 1:
            continue
        print(f"  {r['matter'][:16]:<16} {r['total']:>5} {r['connected']:>5} "
              f"{(str(r['connected_pct'])+'%'):>5} {r['provenance_earned']:>5} "
              f"{r['w_text']:>5} {r['w_type']:>5} {r['w_quality']:>5} {r['w_embedded']:>5} {r['stuck_flagged']:>5}")
    # binding-constraint hint: which signal is the corpus-wide bottleneck among docs that have text
    print(f"  → binding constraint = the lowest column above; provenance is EARNED (A42), "
          f"type needs classification. See --matter <case_file>.")


def matter_detail(cur, matter):
    """For one case_file: how many docs are missing EACH signal (where the backlog is)."""
    cur.execute("""
        SELECT count(*) total,
          count(*) FILTER (WHERE connected)              connected,
          count(*) FILTER (WHERE NOT sig_text)           no_text,
          count(*) FILTER (WHERE NOT sig_quality)        no_quality,
          count(*) FILTER (WHERE NOT sig_type)           no_type,
          count(*) FILTER (WHERE NOT sig_embedded)       no_embedded,
          count(*) FILTER (WHERE NOT sig_provenance)     no_provenance,
          count(*) FILTER (WHERE flagged AND NOT connected) stuck
        FROM v_doc_connectivity WHERE case_file = %s""", (matter,))
    r = cur.fetchone()
    if not r or r["total"] == 0:
        print(f"[incorporation] no docs under case_file '{matter}'"); return
    print(f"[incorporation] {matter}: {r['connected']}/{r['total']} connected · stuck {r['stuck']}")
    print("  docs MISSING each signal (the backlog to close, in gate order):")
    for label, key in [("text", "no_text"), ("quality", "no_quality"), ("document_type", "no_type"),
                       ("embedded", "no_embedded"), ("provenance(model_used)", "no_provenance")]:
        print(f"    {label:<24} {r[key]:>5} missing")


def check_consistency(cur):
    """Assert the view's corpus-wide `connected` equals the A41 predicate computed independently.
    Guards the view against silently drifting from truth_tests/test_connected_document_count.py."""
    cur.execute("SELECT connected, provenance_earned, total FROM v_incorporation_status WHERE is_total = 1")
    v = cur.fetchone()
    # independent recomputation of the EXACT A41 signals (not via the view)
    cur.execute("""
        SELECT count(*) FILTER (WHERE txt AND prov AND typ AND qual AND emb) AS connected,
               count(*) FILTER (WHERE prov)                                  AS provenance,
               count(*)                                                      AS total
        FROM (
          SELECT (coalesce(length(d.extracted_text),0) >= 50) txt, (d.model_used IS NOT NULL) prov,
                 (d.document_type IS NOT NULL) typ,
                 EXISTS(SELECT 1 FROM ocr_quality q WHERE q.doc_id=d.id) qual,
                 EXISTS(SELECT 1 FROM corpus_backfill_state c WHERE c.doc_id=d.id AND c.embedded IS TRUE) emb
          FROM documents d) s""")
    a = cur.fetchone()
    ok = (v["connected"] == a["connected"] and v["provenance_earned"] == a["provenance"] and v["total"] == a["total"])
    status = "CONSISTENT" if ok else "DRIFT"
    print(f"[incorporation] A41 consistency: {status} — "
          f"view(connected={v['connected']},prov={v['provenance_earned']},total={v['total']}) "
          f"vs A41(connected={a['connected']},prov={a['provenance']},total={a['total']})")
    return ok


def log_snapshot(cur):
    """Idempotently upsert TODAY's snapshot into incorporation_log; report the high-water mark."""
    rows = _rows(cur)
    tot = _total_row(rows)
    per = {r["matter"]: {"total": r["total"], "connected": r["connected"], "prov": r["provenance_earned"]}
           for r in rows if r["is_total"] != 1}
    cur.execute("""INSERT INTO incorporation_log (snapshot_date, total, connected, provenance, stuck, per_matter)
                   VALUES (CURRENT_DATE, %s, %s, %s, %s, %s)
                   ON CONFLICT (snapshot_date) DO UPDATE SET total=EXCLUDED.total, connected=EXCLUDED.connected,
                     provenance=EXCLUDED.provenance, stuck=EXCLUDED.stuck, per_matter=EXCLUDED.per_matter,
                     logged_at=now()""",
                (tot["total"], tot["connected"], tot["provenance_earned"], tot["stuck_flagged"], json.dumps(per)))
    cur.execute("SELECT max(connected) hw, (SELECT connected FROM incorporation_log ORDER BY snapshot_date DESC LIMIT 1) cur FROM incorporation_log")
    r = cur.fetchone()
    print(f"[incorporation] logged {tot['connected']}/{tot['total']} connected · high-water {r['hw']} (today {r['cur']})")


def check_regression(cur):
    """Fail-closed rollout guard: alert if the corpus-wide connected count fell BELOW the historical
    high-water mark — that means a connectivity signal was un-set (a regression), which the A41/A42
    consistency tests do NOT catch (they check consistency, not a drop). Exit 1 on regression."""
    cur.execute("SELECT connected FROM v_incorporation_status WHERE is_total = 1")
    now = cur.fetchone()["connected"]
    cur.execute("SELECT coalesce(max(connected), 0) AS hw FROM incorporation_log")
    hw = cur.fetchone()["hw"]
    if now < hw:
        print(f"[incorporation] REGRESSION: connected {now} < high-water {hw} — a connectivity signal was "
              f"un-set since the peak. Investigate before enabling/continuing rollout.")
        return False
    print(f"[incorporation] no regression: connected {now} >= high-water {hw}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", help="drill into one case_file's missing-signal backlog")
    ap.add_argument("--log", action="store_true", help="append today's snapshot to incorporation_log")
    ap.add_argument("--check", action="store_true", help="assert the view reconciles with A41 (exit 1 on drift)")
    ap.add_argument("--check-regression", action="store_true", dest="check_regression",
                    help="exit 1 if connected count fell below the high-water mark (rollout guard)")
    a = ap.parse_args()
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if a.check:
            sys.exit(0 if check_consistency(cur) else 1)
        if a.check_regression:
            sys.exit(0 if check_regression(cur) else 1)
        if a.matter:
            matter_detail(cur, a.matter); return
        snapshot(cur)
        if a.log:
            log_snapshot(cur)
    finally:
        cur.close(); c.close()


if __name__ == "__main__":
    main()
