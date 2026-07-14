#!/usr/bin/env python3
"""test_truth_layer_fitness.py — the harness's own guardrails, made physical (docs/TRUTH_LAYER_FITNESS_SPEC.md §9).

Proves the fitness harness is structurally incapable of the trap: it cannot write facts (DB privilege),
its ledger cannot be mutated (trigger), 'grounded' means the provenance gate (not confidence), findability
never demotes grounding, chain provenance is never a validity judgment, an empty domain yields no false gaps,
and every cycle is fingerprinted.
"""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek")
from _harness import run, TruthFailure, DSN
import truth_layer_fitness as TLF


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


class _NullRetriever:
    def retrieve(self, q, k=8, ids=None):
        return []


def harness_writes_no_facts(cur):
    """Under SET ROLE tlfh_harness, any write to a FACT table must be refused by the DB (privilege)."""
    conn, tc = _rb()
    try:
        tc.execute("SET ROLE tlfh_harness")
        try:
            tc.execute("INSERT INTO documents (case_file) VALUES ('__tlfh_probe__')")
        except psycopg2.Error:
            return                                   # refused — correct
        raise TruthFailure("harness role was able to INSERT into a FACT table (documents) — read-only breach.")
    finally:
        conn.rollback(); conn.close()


def ledger_is_append_only(cur):
    """The append-only trigger must reject UPDATE/DELETE on fitness_measurement (tested as owner, not by grant)."""
    conn, tc = _rb()
    try:
        tc.execute("INSERT INTO fitness_cycle (domain) VALUES ('__t__') RETURNING id")
        cyc = tc.fetchone()["id"]
        tc.execute("INSERT INTO fitness_object (domain,object_type,object_id) VALUES ('__t__','t','1') "
                   "ON CONFLICT (domain,object_type,object_id) DO UPDATE SET last_graded=now() RETURNING id")
        opk = tc.fetchone()["id"]
        tc.execute("INSERT INTO fitness_measurement (cycle_id,object_pk,dimension,submeasure,value) "
                   "VALUES (%s,%s,'grounding','grounded','False') RETURNING id", (cyc, opk))
        mid = tc.fetchone()["id"]
        try:
            tc.execute("UPDATE fitness_measurement SET value='True' WHERE id=%s", (mid,))
        except psycopg2.Error:
            return                                   # trigger fired — correct
        raise TruthFailure("fitness_measurement accepted an UPDATE — the append-only guard is not enforced.")
    finally:
        conn.rollback(); conn.close()


def grounded_matches_provenance_gate(cur):
    """'grounded' is True only when provenance_level='verified' — never on inferred/asserted/none."""
    conn, tc = _rb()
    try:
        tc.execute(TLF._SPINE_CTE)
        spine = [r["tct_number"] for r in tc.fetchall()]
        adapter = TLF.LegalTitleAdapter()
        checked = 0
        for tct in spine:
            t = TLF._one(tc, "SELECT provenance_level FROM titles WHERE tct_number=%s", (tct,))
            meas = {m["submeasure"]: m["value"] for m in adapter.grade(tc, "title", tct, {"retriever": None})
                    if m["dimension"] == "grounding"}
            if "grounded" not in meas:
                continue
            checked += 1
            if meas["grounded"] == "True" and t["provenance_level"] != "verified":
                raise TruthFailure(f"{tct} graded grounded=True with provenance_level={t['provenance_level']!r} "
                                   "— grounding was coerced from a non-verified basis.")
        if checked == 0:
            raise TruthFailure("no title grounding submeasures were produced — grader not exercising the gate.")
    finally:
        conn.rollback(); conn.close()


def findability_never_demotes_grounding(cur):
    """A retrieval miss changes ONLY the findability axis; the grounding value is identical with/without it."""
    conn, tc = _rb()
    try:
        tc.execute(TLF._SPINE_CTE)
        spine = [r["tct_number"] for r in tc.fetchall()]
        adapter = TLF.LegalTitleAdapter()
        tct = next((t for t in spine
                    if TLF._one(tc, "SELECT source_doc_id FROM titles WHERE tct_number=%s", (t,))["source_doc_id"]), None)
        if not tct:
            return
        def grounded_of(ctx):
            return {m["submeasure"]: m["value"] for m in adapter.grade(tc, "title", tct, ctx)
                    if m["dimension"] == "grounding"}.get("grounded")
        # grounding must be identical whether the semantic probe is off or forced to 'missed'
        clean = grounded_of({"no_semantic": True})
        forced_miss = grounded_of({"mwk_doc_ids": [-1]})   # scoped to a nonexistent doc → semantic miss
        if clean != forced_miss:
            raise TruthFailure(f"grounding changed with retrieval state ({clean}->{forced_miss}) — findability "
                               "demoted grounding (forbidden).")
    finally:
        conn.rollback(); conn.close()


def chain_provenance_is_not_validity(cur):
    """No instrument/title submeasure may ever assert legal validity/non-void — that is human-reviewed only."""
    conn, tc = _rb()
    try:
        adapter = TLF.LegalTitleAdapter()
        inst = TLF._one(tc, "SELECT id FROM instruments_on_title WHERE parent_tct_number IN "
                            "(SELECT tct_number FROM titles WHERE case_file='MWK-001') LIMIT 1")
        if not inst:
            return
        subs = [m["submeasure"].lower() for m in adapter.grade(tc, "instrument", str(inst["id"]), {"retriever": None})]
        bad = [s for s in subs if "valid" in s or "void" in s or "authoriz" in s]
        if bad:
            raise TruthFailure(f"grader emitted a validity/authority judgment {bad} — that is a legal conclusion "
                               "the data cannot support; must stay human-reviewed.")
    finally:
        conn.rollback(); conn.close()


def empty_domain_yields_no_gaps(cur):
    """A not_instrumented domain enumerates zero objects (never manufactures false gaps)."""
    conn, tc = _rb()
    try:
        for d in ("tenants", "mining", "accounting"):
            a = TLF.ADAPTERS[d]
            if a.status != "not_instrumented" or a.enumerate_objects(tc) != []:
                raise TruthFailure(f"domain {d} should be not_instrumented with zero objects.")
        tc.execute("SET ROLE tlfh_harness")
        res = TLF.run_cycle(tc, domain="tenants", print_card=False)
        if res.get("status") != "not_instrumented":
            raise TruthFailure("run_cycle on an empty domain did not return not_instrumented.")
    finally:
        conn.rollback(); conn.close()


def cycle_is_fingerprinted(cur):
    """Every cycle records a reproducibility fingerprint (grader version + source snapshot)."""
    conn, tc = _rb()
    orig = TLF.EMBED_VENV
    TLF.EMBED_VENV = None                            # keep the test fast + deterministic (no embedding calls)
    try:
        tc.execute("SET ROLE tlfh_harness")
        res = TLF.run_cycle(tc, domain="legal", print_card=False)
        fp = TLF._one(tc, "SELECT fingerprint FROM fitness_cycle WHERE id=%s", (res["cycle_id"],))["fingerprint"]
        if not fp or fp.get("grader_version") != TLF.GRADER_VERSION or "source_snapshot" not in fp:
            raise TruthFailure(f"cycle fingerprint missing/incomplete: {fp}")
        if (res.get("n_objects") or 0) < 1:
            raise TruthFailure("legal cycle graded zero objects — the spine did not enumerate.")
    finally:
        TLF.EMBED_VENV = orig
        conn.rollback(); conn.close()


def remediation_writes_no_facts(cur):
    """Shadow remediation may write ONLY the dedicated candidate lane — never matter_facts / proposed_facts."""
    conn, tc = _rb()
    try:
        tc.execute("SET ROLE tlfh_harness")
        before = (TLF._one(tc, "SELECT count(*) n FROM matter_facts")["n"],
                  TLF._one(tc, "SELECT count(*) n FROM proposed_facts")["n"])
        TLF.remediate(tc, print_report=False)
        after = (TLF._one(tc, "SELECT count(*) n FROM matter_facts")["n"],
                 TLF._one(tc, "SELECT count(*) n FROM proposed_facts")["n"])
        if after != before:
            raise TruthFailure("remediation touched a fact/governed lane (matter_facts/proposed_facts) — forbidden.")
        if (TLF._one(tc, "SELECT count(*) n FROM fitness_remediation_candidate")["n"] or 0) < 1:
            raise TruthFailure("remediation produced zero candidates despite an open gap queue.")
    finally:
        conn.rollback(); conn.close()


def mapping_adapter_instrumented(cur):
    """The second domain adapter grades real geometry objects across dimensions (domain-agnostic proof)."""
    conn, tc = _rb()
    try:
        a = TLF.ADAPTERS["mapping"]
        if a.status != "instrumented":
            raise TruthFailure("mapping adapter should be instrumented.")
        objs = a.enumerate_objects(tc)
        if objs:
            meas = a.grade(tc, objs[0][0], objs[0][1], {})
            if not {m["dimension"] for m in meas}:
                raise TruthFailure("mapping grade produced no measurements for a real parcel.")
    finally:
        conn.rollback(); conn.close()


def trend_view_populated(cur):
    """The cycle-over-cycle trend view carries real grounding coverage."""
    conn, tc = _rb()
    try:
        r = TLF._one(tc, "SELECT count(*) n, max(grounded_total) g FROM v_fitness_trend")
        if (r["n"] or 0) < 1 or (r["g"] or 0) < 1:
            raise TruthFailure("v_fitness_trend has no rows / no grounding measurements.")
    finally:
        conn.rollback(); conn.close()


TESTS = [
    ("tlfh.harness_writes_no_facts", harness_writes_no_facts),
    ("tlfh.remediation_writes_no_facts", remediation_writes_no_facts),
    ("tlfh.mapping_adapter_instrumented", mapping_adapter_instrumented),
    ("tlfh.trend_view_populated", trend_view_populated),
    ("tlfh.ledger_is_append_only", ledger_is_append_only),
    ("tlfh.grounded_matches_provenance_gate", grounded_matches_provenance_gate),
    ("tlfh.findability_never_demotes_grounding", findability_never_demotes_grounding),
    ("tlfh.chain_provenance_is_not_validity", chain_provenance_is_not_validity),
    ("tlfh.empty_domain_yields_no_gaps", empty_domain_yields_no_gaps),
    ("tlfh.cycle_is_fingerprinted", cycle_is_fingerprinted),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
