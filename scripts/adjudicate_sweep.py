#!/usr/bin/env python3
"""adjudicate_sweep.py — mechanical adjudication of proposed_facts (Read Composer P2;
docs/READ_CONSENSUS_DIRECTIVE.md §6 — the drain-or-funeral decision gate's Step 1).

Every pending proposal came from a writer whose VERIFIED insert the DB gate refused at the time
(verify_worker falls through to proposed on gate refusal). Conditions change — re-OCR lands new
text, the verified baseline moves — so this sweep is the A74 re-check for the whole proposal
class: re-test each proposal against the SAME gates, NOW, and close what closes mechanically.

MECHANICAL CLASSES ONLY (deterministic, $0, no LLM — A24):
  quarantined_source — cited doc is quarantined (dup/ghost/nobytes) → status='rejected'
  duplicate          — statement already in matter_facts for the matter → status='rejected'
                       (note 'duplicate_of:<fact_id>'; the knowledge is already in the graph)
  promoted           — owner gate (A77) + contradiction gate (A78) pass AND the gated VERIFIED
                       insert SUCCEEDS (enforce_provenance_facts + V3/V4/V11 arbitrate at the DB;
                       the sweep never asserts verified — the trigger does) → status='promoted'
  contradiction_hold — the A78 gate now conflicts → held (visible, never silent); previously-held
                       proposals whose conflict CLEARED re-enter the promote path (A74 release)
  (residue)          — stays 'pending': not groundable / owner unresolvable. The residue is the
                       measurement the §6 decision gate reads: drain (Option A) vs funeral (B).

NEVER: deletes a proposal · writes verified outside the DB gates · touches accepted/rejected rows.
Every transition stamps adjudicated_at + adjudication_note (+ promoted_fact_id) — the ledger.

  python3 scripts/adjudicate_sweep.py            # DRY: classify + closure-rate report, no writes
  python3 scripts/adjudicate_sweep.py --go       # apply transitions
  python3 scripts/adjudicate_sweep.py --go --limit 50
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contradiction as CONTRA          # A78 gate (deterministic event-date conflict)
import ingest_gate as IG                # A77 owner gate (resolve-or-hold, never guess)

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

WRITER = "adjudicate_sweep"


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _quarantined(cur, doc_id) -> bool:
    if doc_id is None:
        return False
    cur.execute("SELECT ingest_status FROM documents WHERE id=%s", (doc_id,))
    r = cur.fetchone()
    return bool(r) and (r["ingest_status"] or "").startswith("quarantined")


def _duplicate_of(cur, matter, statement):
    cur.execute("SELECT id FROM matter_facts WHERE matter_code=%s AND statement=%s LIMIT 1",
                (matter, statement))
    r = cur.fetchone()
    return r["id"] if r else None


def _try_promote(cur, p):
    """Attempt the gated VERIFIED insert. The DB triggers are the authority
    (enforce_provenance_facts verbatim-excerpt + V3 grounded + V4 isolation + V11 owner);
    the sweep only re-offers the write. Autocommit: a refused INSERT is its own rolled-back
    txn (the verify_worker pattern). Returns fact_id or None."""
    try:
        cur.execute(
            """INSERT INTO matter_facts (matter_code, statement, fact_kind, source_kind, source_id,
                                         excerpt, provenance_level, confidence, created_by, created_at)
               VALUES (%s,%s,'auto_read','doc',%s,%s,'verified',%s,%s,now())
               RETURNING id""",
            (p["matter_code"], p["statement"], str(p["source_doc_id"]), p["excerpt"],
             p["confidence"], WRITER))
        return cur.fetchone()["id"]
    except psycopg2.Error:
        return None


def _close(cur, pid, status, note, fact_id=None, go=False):
    if not go:
        return
    cur.execute("""UPDATE proposed_facts
                   SET status=%s, adjudicated_at=now(), adjudication_note=%s, promoted_fact_id=%s
                   WHERE id=%s""", (status, note, fact_id, pid))


def sweep(cur, go=False, limit=None):
    cur.execute("""SELECT id, matter_code, statement, excerpt, source_doc_id, confidence, status
                   FROM proposed_facts
                   WHERE status IN ('pending','contradiction_hold')
                   ORDER BY status, id""" + (f" LIMIT {int(limit)}" if limit else ""))
    props = cur.fetchall()
    tally = {"promoted": 0, "duplicate": 0, "quarantined_source": 0,
             "contradiction_hold": 0, "hold_released": 0,
             "owner_unresolvable": 0, "not_groundable": 0}
    verified_maps = {}  # matter -> verified event-date map (one fetch per matter)

    for p in props:
        matter = p["matter_code"]

        if _quarantined(cur, p["source_doc_id"]):
            _close(cur, p["id"], "rejected", "quarantined_source", go=go)
            tally["quarantined_source"] += 1
            continue

        dup = _duplicate_of(cur, matter, p["statement"])
        if dup:
            _close(cur, p["id"], "rejected", f"duplicate_of:{dup}", go=go)
            tally["duplicate"] += 1
            continue

        # A77: a fact may only cite an owner-resolvable doc (hold recorded by the gate itself
        # only in --go; dry never writes holes_findings)
        if not IG.owner_gate(cur, matter, p["source_doc_id"], WRITER, record=go):
            tally["owner_unresolvable"] += 1
            continue

        # A78: conflict with the CURRENT verified baseline → (stay) held; cleared → proceed
        if matter not in verified_maps:
            verified_maps[matter] = CONTRA.verified_event_dates(cur, matter)
        conflicts = CONTRA.conflicts_with_verified(
            cur, matter, f"{p['statement']} {p['excerpt'] or ''}", verified_maps[matter])
        if conflicts:
            if p["status"] != "contradiction_hold":
                _close(cur, p["id"], "contradiction_hold",
                       f"A78 conflict: {conflicts[0].get('event','?')}", go=go)
            tally["contradiction_hold"] += 1
            continue
        if p["status"] == "contradiction_hold":
            tally["hold_released"] += 1  # A74: the conflict cleared; falls through to promote

        fid = _try_promote(cur, p) if go else None
        if go and fid:
            _close(cur, p["id"], "promoted", "gate_passed_verbatim", fact_id=fid, go=True)
            tally["promoted"] += 1
        elif go:
            tally["not_groundable"] += 1   # DB gate still refuses — stays pending, honestly
        else:
            # DRY: probe groundability without writing — mirror the trigger's checks read-only
            cur.execute("""SELECT (coalesce(%s,'') <> '') AND EXISTS (
                             SELECT 1 FROM documents d WHERE d.id=%s
                               AND position(%s in coalesce(d.extracted_text,'')) > 0) AS ok""",
                        (p["excerpt"], p["source_doc_id"], p["excerpt"] or ""))
            r = cur.fetchone()
            if r and r["ok"]:
                tally["promoted"] += 1     # would-promote (final authority is still the trigger)
            else:
                tally["not_groundable"] += 1
    return len(props), tally


def main():
    ap = argparse.ArgumentParser(description="mechanical adjudication sweep over proposed_facts (§6)")
    ap.add_argument("--go", action="store_true", help="apply transitions (default: dry report)")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    total, t = sweep(cur, go=a.go, limit=a.limit)
    closed = t["promoted"] + t["duplicate"] + t["quarantined_source"]
    mode = "GO" if a.go else "DRY"
    print(f"[adjudicate_sweep {mode}] {total} proposals examined")
    for k in ("promoted", "duplicate", "quarantined_source", "contradiction_hold",
              "hold_released", "owner_unresolvable", "not_groundable"):
        print(f"  {k:20s} {t[k]}")
    rate = (closed / total * 100) if total else 0.0
    print(f"  mechanical closure: {closed}/{total} = {rate:.0f}%  "
          f"(residue for the §6 A/B decision: {total - closed})")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
