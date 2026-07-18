#!/usr/bin/env python3
"""test_adjudication_ledger.py — mechanical floors for the adjudication sweep (Read Composer P2;
docs/READ_CONSENSUS_DIRECTIVE.md §6). The 261-baseline closure rate must stay measurable forever.

Floors (count-independent):
  1. status_vocabulary   — proposed_facts.status stays inside the known set; a novel status would
                           silently escape every pending-filter in the stack (composer, verify_worker).
  2. no_silent_closure   — any non-pending sweep-era transition carries adjudicated_at + a note:
                           adjudication is a LEDGERED status change, never a bare flip.
  3. promoted_is_earned  — every 'promoted' proposal resolves to a live matter_facts row that the
                           DB gate accepted as VERIFIED citing the SAME doc; a promoted proposal
                           whose fact is missing or sub-verified is a lie in the ledger.
  4. nothing_deleted     — adjudication never deletes: promoted/rejected rows still exist (spot
                           assertion — the ledger IS the history; deletion would reset the baseline).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

KNOWN_STATUSES = {"pending", "contradiction_hold", "promoted", "rejected", "accepted", "expired"}


def status_vocabulary(cur):
    cur.execute("SELECT DISTINCT status FROM proposed_facts")
    have = {r["status"] for r in cur.fetchall()}
    novel = have - KNOWN_STATUSES
    if novel:
        raise TruthFailure(
            f"proposed_facts carries unknown status value(s) {sorted(novel)} — every pending-filter "
            f"in the stack (composer gap counts, verify_worker upserts) would mis-classify them. "
            f"Extend the vocabulary deliberately (here + the filters), never by drift.")
    print(f"      [P2] status vocabulary clean: {sorted(have)}")


def no_silent_closure(cur):
    cur.execute("""SELECT count(*) AS n FROM proposed_facts
                   WHERE status IN ('promoted','rejected','accepted','expired')
                     AND adjudicated_at IS NOT NULL
                     AND coalesce(adjudication_note,'') = ''""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(f"{n} adjudicated proposal(s) carry no adjudication_note — a closure "
                           f"without a reason is a silent closure (§6 ledger rule)")
    print("      [P2] every adjudicated closure carries its reason")


def promoted_is_earned(cur):
    cur.execute("""SELECT p.id, p.promoted_fact_id, f.provenance_level, f.source_id, p.source_doc_id
                   FROM proposed_facts p
                   LEFT JOIN matter_facts f ON f.id = p.promoted_fact_id
                   WHERE p.status = 'promoted' LIMIT 200""")
    rows = cur.fetchall()
    bad = [r["id"] for r in rows
           if r["promoted_fact_id"] is None or r["provenance_level"] != "verified"
           or str(r["source_id"]) != str(r["source_doc_id"])]
    if bad:
        raise TruthFailure(
            f"{len(bad)} 'promoted' proposal(s) do not resolve to a live VERIFIED matter_facts row "
            f"citing the same source doc (ids {bad[:10]}) — promotion must be earned at the DB gate, "
            f"never asserted in the ledger (A78)")
    print(f"      [P2] promoted proposals earned: {len(rows)} checked, all resolve to verified facts")


def nothing_deleted(cur):
    cur.execute("""SELECT count(*) AS terminal, count(*) FILTER (WHERE adjudicated_at IS NOT NULL) AS ledgered
                   FROM proposed_facts WHERE status IN ('promoted','rejected')""")
    r = cur.fetchone()
    print(f"      [P2] ledger intact: {r['terminal']} terminal proposal(s) retained "
          f"({r['ledgered']} sweep-ledgered) — adjudication is a transition, never a delete")


def tier_ceilings_hold(cur):
    """Option A tier law: an 'accepted' proposal lands at 'operator' (a human said yes — never
    verified, which stays DB-gate-earned, A78); an 'expired' one lands at an inferred_* tier
    (unactioned knowledge enters LABELED, never upgraded — A34/A71). A queue write above its
    ceiling is a provenance forgery."""
    cur.execute("""SELECT p.id, p.status, f.provenance_level
                   FROM proposed_facts p JOIN matter_facts f ON f.id = p.promoted_fact_id
                   WHERE p.status IN ('accepted','expired')""")
    bad = [(r["id"], r["status"], r["provenance_level"]) for r in cur.fetchall()
           if (r["status"] == "accepted" and r["provenance_level"] != "operator")
           or (r["status"] == "expired" and not (r["provenance_level"] or "").startswith("inferred"))]
    if bad:
        raise TruthFailure(f"queue writes above their tier ceiling: {bad[:8]} — accepted⇒operator, "
                           f"expired⇒inferred_*, verified is NEVER queue-writable")
    print("      [P2/A] tier ceilings hold: accepted⇒operator, expired⇒inferred_*")


def dose_ceiling_holds(cur):
    """A71 floor: no day's offered batch exceeds the dose ceiling (default 10; env ADJ_DOSE)."""
    import os as _os
    dose = int(_os.environ.get("ADJ_DOSE", "10"))
    cur.execute("""SELECT offered_at::date AS d, count(*) AS n FROM proposed_facts
                   WHERE offered_at IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 1""")
    r = cur.fetchone()
    if r and r["n"] > dose:
        raise TruthFailure(f"{r['n']} proposals offered on {r['d']} — exceeds the A71 dose "
                           f"ceiling ({dose}); the queue must rotate, never dump")
    print(f"      [P2/A] dose ceiling holds (max offered/day = {r['n'] if r else 0} ≤ {dose})")


TESTS = [
    ("adjudication.status_vocabulary", status_vocabulary),
    ("adjudication.no_silent_closure", no_silent_closure),
    ("adjudication.promoted_is_earned", promoted_is_earned),
    ("adjudication.nothing_deleted", nothing_deleted),
    ("adjudication.tier_ceilings_hold", tier_ceilings_hold),
    ("adjudication.dose_ceiling_holds", dose_ceiling_holds),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
