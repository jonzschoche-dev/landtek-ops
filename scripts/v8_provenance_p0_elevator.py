#!/usr/bin/env python3
"""v8_provenance_p0_elevator.py — arm the pilot-time V8→P0 alert (governance-owned escalation).

WHY. The V8 ontology_validator (deploy_769) logs `ONTOLOGY_PROVENANCE_UNEARNED` to holes_findings the
instant a `documents.model_used` stamp lacks a completed `extraction_runs` row — the A42 "provenance must be
EARNED" tripwire, and the O-pathway corruption signal during the `--stamp` pilot. BUT `ontology_reject`
writes every finding at severity='info', and `holes.p0_pusher` only Telegram-pushes severity='P0'. So a V8
finding would sit SILENT. This elevator closes that: it promotes any open V8 finding info→P0 so the existing
5-min p0_pusher pages Jonathan, and drops a PAUSE-THE-PILOT note into notifications/pending.txt as a belt-and-
suspenders (surfaced at session start even if Telegram is down).

Boundary: this does NOT touch the V8 trigger or ontology_reject (ontology desk owns those). It only
re-classifies the finding's escalation severity — governance's lane per the deploy_772 directive. A V8
finding is ALWAYS a genuine A42 corruption (only possible when a stamp is written without a run), so
elevating it to P0 is correct at all times; the check is naturally DORMANT (0 rows) until --stamp is on and
something actually stamps unearned. Idempotent, read-mostly, creditless.

  python3 scripts/v8_provenance_p0_elevator.py          # elevate + note any open V8 findings (timer-run)
  python3 scripts/v8_provenance_p0_elevator.py --status # read-only: how many open V8 findings, at what severity
"""
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
HOLE = "ONTOLOGY_PROVENANCE_UNEARNED"
PENDING = "/root/landtek/notifications/pending.txt"


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def status(cur):
    cur.execute("SELECT severity, count(*) FROM holes_findings WHERE hole_type=%s AND status='open' GROUP BY 1", (HOLE,))
    rows = cur.fetchall()
    if not rows:
        print(f"[v8-elevator] 0 open {HOLE} findings — dormant (as expected while --stamp is off / no unearned stamp)")
        return
    for r in rows:
        print(f"[v8-elevator] {r['count']} open {HOLE} finding(s) at severity={r['severity']}")


def elevate(cur):
    cur.execute("""UPDATE holes_findings SET severity='P0'
                   WHERE hole_type=%s AND status='open' AND severity <> 'P0'
                   RETURNING id, doc_id, description""", (HOLE,))
    hit = cur.fetchall()
    if not hit:
        print(f"[v8-elevator] nothing to elevate (0 open non-P0 {HOLE} findings)")
        return 0
    docs = sorted({str(r["doc_id"]) for r in hit if r["doc_id"] is not None})
    msg = (f"[P0][v8-provenance] PAUSE THE --stamp PILOT. V8 flagged {len(hit)} ONTOLOGY_PROVENANCE_UNEARNED "
           f"finding(s) — a documents.model_used stamp with NO completed extraction_runs row (A42: provenance "
           f"fabricated / stamped-before-run). Affected doc(s): {', '.join(docs) or '?'}. Halt --stamp, "
           f"investigate the write path, do NOT expand the pilot until resolved. (elevated info->P0; p0_pusher will page.)")
    try:
        os.makedirs(os.path.dirname(PENDING), exist_ok=True)
        with open(PENDING, "a") as fh:
            fh.write(msg + "\n")
    except Exception as e:
        print(f"[v8-elevator] WARN could not write pending.txt: {e}")
    print(f"[v8-elevator] ELEVATED {len(hit)} finding(s) info->P0 (docs {docs}); p0_pusher will Telegram-push within 5 min")
    print("  " + msg)
    return len(hit)


def main():
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if "--status" in sys.argv:
            status(cur)
        else:
            elevate(cur)
    finally:
        cur.close(); c.close()


if __name__ == "__main__":
    main()
