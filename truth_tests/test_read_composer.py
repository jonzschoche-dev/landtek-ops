#!/usr/bin/env python3
"""test_read_composer.py — mechanical floors for the Read Composer (A86 candidate; docs/READ_CONSENSUS_DIRECTIVE.md).

Floors (all count-independent, negative-tested by construction):
  1. registry_seeded       — consensus_registry carries the four P0 concepts (the authority order
                             lives in the TABLE, never per-surface / scattered in code).
  2. always_answer         — a nonexistent matter yields a MISS envelope with typed gaps; the
                             composer never raises and never refuses on thin data (directive §2.2).
  3. scope_hold            — asking for a matter under the WRONG client returns HOLD (A5 in the
                             query, the composer's only refusal) with a scope_refused gap.
  4. mention_never_answers — no claim's source_table is a mention_only store (document_titles,
                             proposed_facts): mention is not membership, machine-enforced.
  5. audit_written         — every compose_answer call lands a composer_audit row (the emission
                             audit half of §10.1).

Deterministic, creditless; reads governed stores, writes only composer_audit (via the composer).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

from leo_tools.consensus import compose_answer, INTENTS

MENTION_ONLY_STORES = {"document_titles", "proposed_facts"}


def registry_seeded(cur):
    cur.execute("SELECT concept FROM consensus_registry ORDER BY concept")
    have = {r["concept"] for r in cur.fetchall()}
    missing = set(INTENTS) - have
    if missing:
        raise TruthFailure(
            f"consensus_registry missing concepts {sorted(missing)} — the authority order must live in "
            f"the registry table (deploy_939), never per-surface")
    print(f"      [A86] registry seeded: {sorted(have)}")


def always_answer(cur):
    env = compose_answer("matter_status", matter="ZZZ-NO-SUCH-MATTER-XX", caller="truth_test")
    if env["status"] != "miss":
        raise TruthFailure(f"nonexistent matter must yield status='miss', got {env['status']!r}")
    kinds = {g["kind"] for g in env["gaps"]}
    if "unknown_matter" not in kinds:
        raise TruthFailure(f"miss envelope must carry a typed unknown_matter gap, got {sorted(kinds)}")
    env2 = compose_answer("facts", matter="ZZZ-NO-SUCH-MATTER-XX", topic="anything", caller="truth_test")
    if env2["status"] != "miss":
        raise TruthFailure(f"facts on nonexistent matter must be miss, got {env2['status']!r}")
    print("      [A86] always-answer: nonexistent matter -> miss + typed gaps (no raise, no refusal)")


def scope_hold(cur):
    # find any two matters owned by DIFFERENT real clients; ask for one under the other's client
    cur.execute("""SELECT m1.matter_code, m1.client_code AS owner, m2.client_code AS wrong
                   FROM matters m1 JOIN matters m2 ON m2.client_code <> m1.client_code
                   WHERE m1.client_code NOT IN ('Owner','Archive','PENDING_TRIAGE')
                     AND m2.client_code NOT IN ('Owner','Archive','PENDING_TRIAGE')
                   LIMIT 1""")
    pair = cur.fetchone()
    if not pair:
        print("      [A86] scope_hold: <2 real clients present — vacuously green (flagged)")
        return
    env = compose_answer("matter_status", client_code=pair["wrong"],
                         matter=pair["matter_code"], caller="truth_test")
    if env["status"] != "hold":
        raise TruthFailure(
            f"matter {pair['matter_code']} (owner {pair['owner']}) requested as client {pair['wrong']} "
            f"must HOLD (A5 in the query), got {env['status']!r} with {len(env['claims'])} claims")
    if env["claims"]:
        raise TruthFailure("a HOLD envelope must carry ZERO claims — scope refusal is total, never a filtered peek")
    if not any(g["kind"] == "scope_refused" for g in env["gaps"]):
        raise TruthFailure("HOLD must carry the typed scope_refused gap")
    print(f"      [A86] scope: {pair['matter_code']} under wrong client {pair['wrong']} -> hold, 0 claims")


def mention_never_answers(cur):
    # exercise the live paths that touch mention_only stores; assert no claim cites them
    probes = [
        ("title", {"title": "T-4497"}),
        ("matter_status", {"matter": "MWK-GUARDIANSHIP"}),
        ("facts", {"matter": "MWK-GUARDIANSHIP", "topic": "SPA"}),
    ]
    for intent, kw in probes:
        env = compose_answer(intent, caller="truth_test", **kw)
        bad = [c for c in env["claims"] if c["source_table"] in MENTION_ONLY_STORES]
        if bad:
            raise TruthFailure(
                f"{intent}{kw}: {len(bad)} claim(s) cite a mention_only store "
                f"({sorted({c['source_table'] for c in bad})}) — mention is not membership; "
                f"those stores may contribute gaps/leads ONLY")
    print("      [A86] mention_only stores never produced an answer claim across the probe intents")


def audit_written(cur):
    cur.execute("SELECT count(*) AS n FROM composer_audit")
    before = cur.fetchone()["n"]
    compose_answer("deadlines", caller="truth_test_audit")
    cur.execute("SELECT count(*) AS n FROM composer_audit")
    after = cur.fetchone()["n"]
    if after <= before:
        raise TruthFailure(
            f"compose_answer did not write composer_audit ({before} -> {after}) — every envelope must be logged")
    print(f"      [A86] audit: composer_audit {before} -> {after}")


TESTS = [
    ("composer.registry_seeded", registry_seeded),
    ("composer.always_answer", always_answer),
    ("composer.scope_hold", scope_hold),
    ("composer.mention_never_answers", mention_never_answers),
    ("composer.audit_written", audit_written),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
