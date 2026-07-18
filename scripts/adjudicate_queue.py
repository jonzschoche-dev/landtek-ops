#!/usr/bin/env python3
"""adjudicate_queue.py — the dose-capped operator batch queue (Read Composer P2 §6 OPTION A,
chosen 2026-07-18 on the sweep's evidence: mechanical closure 7%, residue 242).

The drain, honestly sized to the operator (A71 — feed to metabolizable capacity):
  * Each day the timer offers a batch of ≤ADJ_DOSE (10) pending proposals — breadth-fair
    rotation (least-offered first, MWK matters first per §6B W5), stamped offered_at/offer_count.
  * The operator one-taps each item: --accept (fact enters at 'operator' tier, source cited)
    or --reject --reason. Accepting NEVER writes 'verified' — verified stays DB-gate-earned (A78).
  * An item offered ADJ_MAX_OFFERS (3) times without action EXPIRES: the knowledge enters
    matter_facts as a LABELED 'inferred_strong' row (same tier its writer would have used) and
    the proposal closes status='expired' — never silently dropped, never upgraded, never lingers.
  * Every write passes the SAME gates as every other writer: owner_gate (A77) + contradiction
    gate (A78) + the DB triggers. A gate refusal holds the item, visibly.

  python3 scripts/adjudicate_queue.py --offer            # timer entry: expire past-horizon, offer today's batch
  python3 scripts/adjudicate_queue.py --list             # show today's batch (ids + grounds)
  python3 scripts/adjudicate_queue.py --accept 123 [--note "..."]
  python3 scripts/adjudicate_queue.py --reject 123 --reason "wrong date"
  python3 scripts/adjudicate_queue.py --status           # queue counts + drain trend
  python3 scripts/adjudicate_queue.py --digest-line      # one S14-safe line for the daily digest
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contradiction as CONTRA
import ingest_gate as IG

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
DOSE = int(os.environ.get("ADJ_DOSE", "10"))            # A71 daily ceiling
MAX_OFFERS = int(os.environ.get("ADJ_MAX_OFFERS", "3"))  # offers before expiry-to-inferred
WRITER = "adjudicate_queue"


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _get(cur, pid):
    cur.execute("SELECT * FROM proposed_facts WHERE id=%s", (pid,))
    return cur.fetchone()


def _dup(cur, matter, statement):
    cur.execute("SELECT id FROM matter_facts WHERE matter_code=%s AND statement=%s LIMIT 1",
                (matter, statement))
    r = cur.fetchone()
    return r["id"] if r else None


def _gated_insert(cur, p, provenance, created_by):
    """One write path for accept + expiry — same gates as every other writer (A77/A78/DB).
    Returns (fact_id, reason): fact_id None => held/refused with reason."""
    dup = _dup(cur, p["matter_code"], p["statement"])
    if dup:
        return None, f"duplicate_of:{dup}"
    if not IG.owner_gate(cur, p["matter_code"], p["source_doc_id"], WRITER, record=True):
        return None, "owner_unresolvable"
    conflicts = CONTRA.conflicts_with_verified(
        cur, p["matter_code"], f"{p['statement']} {p['excerpt'] or ''}")
    if conflicts:
        return None, f"A78_conflict:{conflicts[0].get('event', '?')}"
    try:
        cur.execute(
            """INSERT INTO matter_facts (matter_code, statement, fact_kind, source_kind, source_id,
                                         excerpt, provenance_level, confidence, created_by, created_at)
               VALUES (%s,%s,'auto_read','doc',%s,%s,%s,%s,%s,now()) RETURNING id""",
            (p["matter_code"], p["statement"], str(p["source_doc_id"]), p["excerpt"],
             provenance, p["confidence"], created_by))
        return cur.fetchone()["id"], "ok"
    except psycopg2.Error as e:
        return None, f"db_gate:{str(e).splitlines()[0][:120]}"


def cmd_offer(cur):
    # 1) Expire past-horizon items (offered MAX_OFFERS times, unactioned) → labeled inferred
    cur.execute("""SELECT * FROM proposed_facts
                   WHERE status='pending' AND offer_count >= %s
                     AND offered_at::date < CURRENT_DATE ORDER BY id""", (MAX_OFFERS,))
    expired = held = 0
    for p in cur.fetchall():
        fid, why = _gated_insert(cur, p, "inferred_strong", f"{WRITER}_expiry")
        if fid or why.startswith("duplicate_of"):
            cur.execute("""UPDATE proposed_facts SET status='expired', adjudicated_at=now(),
                           adjudication_note=%s, promoted_fact_id=%s WHERE id=%s""",
                        (f"expired_to_inferred after {p['offer_count']} offers ({why})", fid, p["id"]))
            expired += 1
        elif why.startswith("A78_conflict"):
            cur.execute("""UPDATE proposed_facts SET status='contradiction_hold',
                           adjudication_note=%s WHERE id=%s""", (why, p["id"]))
            held += 1
        else:
            held += 1  # owner/db gate refused — stays pending, gate recorded the hold

    # 2) Offer today's batch — skip if already offered today (idempotent per day, no double-dose)
    cur.execute("""SELECT count(*) AS n FROM proposed_facts
                   WHERE status='pending' AND offered_at::date = CURRENT_DATE""")
    already = cur.fetchone()["n"]
    offered = 0
    if already < DOSE:
        cur.execute("""UPDATE proposed_facts SET offered_at=now(), offer_count=offer_count+1
                       WHERE id IN (
                         SELECT id FROM proposed_facts
                         WHERE status='pending'
                           AND (offered_at IS NULL OR offered_at::date < CURRENT_DATE)
                         ORDER BY offer_count ASC,
                                  CASE WHEN matter_code LIKE 'MWK%%' THEN 0 ELSE 1 END, id
                         LIMIT %s) RETURNING id""", (DOSE - already,))
        offered = len(cur.fetchall())
    print(f"[queue offer] expired_to_inferred={expired} gate_held={held} "
          f"offered_today={already + offered} (dose {DOSE}, horizon {MAX_OFFERS} offers)")


def cmd_list(cur):
    cur.execute("SELECT * FROM v_adjudication_queue")
    rows = cur.fetchall()
    if not rows:
        print("queue empty today — run --offer (timer does this daily)")
        return
    print(f"Today's batch ({len(rows)}/{DOSE}) — accept N | reject N --reason '…':")
    for r in rows:
        exc = (r["excerpt"] or "")[:100].replace("\n", " ")
        print(f"  [{r['id']}] {r['matter_code']} (doc {r['source_doc_id']}, offer {r['offer_count']}/{MAX_OFFERS})\n"
              f"        {r['statement'][:160]}\n"
              f"        excerpt: {exc!r}")


def cmd_accept(cur, pid, note):
    p = _get(cur, pid)
    if not p or p["status"] != "pending":
        print(f"[accept] proposal {pid} not pending ({(p or {}).get('status')})")
        return 1
    fid, why = _gated_insert(cur, p, "operator", WRITER)
    if not fid:
        if why.startswith("duplicate_of"):
            cur.execute("""UPDATE proposed_facts SET status='rejected', adjudicated_at=now(),
                           adjudication_note=%s WHERE id=%s""", (why, pid))
            print(f"[accept] {pid}: already in the graph ({why}) — closed as duplicate")
            return 0
        print(f"[accept] {pid} HELD: {why}")
        return 1
    cur.execute("""UPDATE proposed_facts SET status='accepted', adjudicated_at=now(),
                   adjudication_note=%s, promoted_fact_id=%s WHERE id=%s""",
                (note or "operator_accept", fid, pid))
    print(f"[accept] {pid} → matter_facts {fid} at 'operator' tier (verified stays gate-earned)")
    return 0


def cmd_reject(cur, pid, reason):
    p = _get(cur, pid)
    if not p or p["status"] not in ("pending", "contradiction_hold"):
        print(f"[reject] proposal {pid} not open ({(p or {}).get('status')})")
        return 1
    cur.execute("""UPDATE proposed_facts SET status='rejected', adjudicated_at=now(),
                   adjudication_note=%s WHERE id=%s""", (f"operator_reject: {reason}", pid))
    print(f"[reject] {pid} closed: {reason}")
    return 0


def _counts(cur):
    cur.execute("""SELECT status, count(*) AS n FROM proposed_facts GROUP BY status""")
    return {r["status"]: r["n"] for r in cur.fetchall()}


def cmd_status(cur):
    c = _counts(cur)
    cur.execute("SELECT count(*) AS n FROM v_adjudication_queue")
    today = cur.fetchone()["n"]
    print(f"open: pending={c.get('pending', 0)} contradiction_hold={c.get('contradiction_hold', 0)} "
          f"| today's batch: {today}/{DOSE}")
    print(f"closed: accepted={c.get('accepted', 0)} promoted={c.get('promoted', 0)} "
          f"rejected={c.get('rejected', 0)} expired={c.get('expired', 0)}")


def cmd_digest_line(cur):
    c = _counts(cur)
    cur.execute("SELECT count(*) AS n FROM v_adjudication_queue")
    today = cur.fetchone()["n"]
    if today:
        print(f"Fact queue: {today} items ready for your yes/no today, "
              f"{c.get('pending', 0)} waiting overall.")
    # no line when the batch is empty — one point per message, no filler (S14)


def main():
    ap = argparse.ArgumentParser(description="dose-capped operator adjudication queue (§6 Option A)")
    ap.add_argument("--offer", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--accept", type=int)
    ap.add_argument("--reject", type=int)
    ap.add_argument("--reason")
    ap.add_argument("--note")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--digest-line", action="store_true")
    a = ap.parse_args()

    conn, cur = _conn()
    try:
        if a.offer:
            cmd_offer(cur)
        elif a.list:
            cmd_list(cur)
        elif a.accept is not None:
            return cmd_accept(cur, a.accept, a.note)
        elif a.reject is not None:
            if not a.reason:
                print("--reject requires --reason (a closure without a reason is a silent closure)")
                return 1
            return cmd_reject(cur, a.reject, a.reason)
        elif a.digest_line:
            cmd_digest_line(cur)
        else:
            cmd_status(cur)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
