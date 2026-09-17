"""Offline adversarial guards plus read-only live routing checks for the Hunter.

Run --unit without database dependencies. TESTS is discovered by the existing truth suite.
"""
import contextlib
import io
import inspect
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
import ombudsman_hunter as hunter


class Cursor:
    def __init__(self, rows=(), one=(1,)):
        self.rows, self.one, self.calls = list(rows), one, []
        self.rowcount = 1

    def execute(self, query, params=()):
        self.calls.append((query, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Connection(Cursor):
    def __init__(self, cur):
        self.cur, self.closed = cur, False

    def cursor(self, **kwargs):
        return self.cur

    def close(self):
        self.closed = True


class HunterGuards(unittest.TestCase):
    def setUp(self):
        hunter.set_client("MWK")

    def tearDown(self):
        hunter.set_client("MWK")

    def test_canonical_aliases(self):
        for key, expected in (("MWK", "MWK-001"), ("MWK-001", "MWK-001"),
                              ("PAR", "Paracale-001"), ("Paracale", "Paracale-001"),
                              ("NIBDC", "NIBDC-001")):
            hunter.set_client(key)
            self.assertEqual(hunter._client_code(), expected)

    def test_no_wildcard_clients(self):
        for key in ("%", "MWK%", "MWK_001", "", "MWK'; SELECT 1"):
            with self.assertRaises(ValueError):
                hunter.set_client(key)

    def test_unknown_client_connection_fails_closed(self):
        hunter.set_client("UNREGISTERED-001")
        conn = Connection(Cursor(one=None))
        pg = types.SimpleNamespace(connect=lambda dsn: conn)
        with patch.object(hunter, "_load_pg"), patch.object(hunter, "psycopg2", pg):
            with self.assertRaises(ValueError):
                hunter._conn()
        self.assertTrue(conn.closed)

    def test_foreign_matter_connection_fails_closed(self):
        hunter._MATTER[0] = "PAR-OTHER"
        cur = Cursor()
        cur.fetchone = lambda: (1,) if len(cur.calls) == 1 else None
        conn = Connection(cur)
        with patch.object(hunter, "_load_pg"), patch.object(hunter, "psycopg2", types.SimpleNamespace(connect=lambda _: conn)):
            with self.assertRaises(ValueError):
                hunter._conn()

    def test_paracale_has_no_mwk_seed_or_exclusion(self):
        hunter.set_client("PAR")
        self.assertEqual(hunter.active_roster(), [])
        self.assertNotIn("zschoche", hunter.active_ourside())
        self.assertEqual(hunter.THEORY_HINTS, {})

    def test_names_do_not_imply_political_favor(self):
        self.assertNotIn("political_favor", hunter._scan_signals("Tony Teope wrote a letter"))

    def test_generic_mayor_is_not_pajarillo(self):
        self.assertFalse(hunter._match_official("Mayor Someone visited Mercedes", ["Mayor", "Pajarillo"]))
        self.assertTrue(hunter._match_official("Pajarillo received a letter", ["Mayor", "Pajarillo"]))

    def test_assistant_is_not_elective_mayor(self):
        self.assertEqual(hunter._classify_capacity("Assistant to the Municipal Mayor"), "unknown")

    def test_missing_provenance_is_not_grounded(self):
        roster = [("Target", "Office", "unknown", ["Target"], "", "seed")]
        profiles = hunter.cull_and_profile([(1, "MWK-X", "Target refused", "5", None)], roster)
        self.assertEqual(profiles["Target"]["incidents"], [])

    def test_shared_projection_receives_owned_cte(self):
        cur = Cursor(rows=[(1, "MWK-X", "statement", "2", "verified", "excerpt")])
        facts = hunter._fetch_facts(cur, rx="Teope")
        query, params = cur.calls[-1]
        self.assertIn("WITH matter_facts AS", query)
        self.assertIn("JOIN matters", query)
        self.assertIn("f.source_kind='doc'", query)
        self.assertIn("draft|reconstructed", query)
        self.assertIn("owner.client_code IS DISTINCT FROM", query)
        self.assertEqual(params, ("MWK-001", "Teope", "Teope", "MWK-001", "%"))
        self.assertEqual(facts[0], (1, "MWK-X", "statement", "2", "verified"))
        self.assertIn("project_fact_slice", inspect.getsource(hunter._fetch_facts))

    def test_document_search_has_no_global_fallback(self):
        cur = Cursor()
        hunter.set_client("PAR")
        hunter._scoped_docs(cur, "Teope")
        query, params = cur.calls[-1]
        self.assertIn("m.client_code=%s", query)
        self.assertIn("d.case_file=%s", query)
        self.assertIn("owner.client_code IS DISTINCT FROM", query)
        self.assertEqual(params[1:5], ("Paracale-001",) * 4)
        with patch.object(cur, "execute", side_effect=RuntimeError("missing ownership table")):
            with self.assertRaises(RuntimeError):
                hunter._scoped_docs(cur, ".")

    def test_officer_discovery_is_document_owned(self):
        cur = Cursor()
        hunter.discover_officers(cur)
        query, params = cur.calls[-1]
        self.assertIn("doc_entities_safe", query)
        self.assertIn("m.client_code=%s", query)
        self.assertEqual(params[0], "MWK-001")

    def test_agency_actor_survives_empty_entity_graph(self):
        cur = Cursor(rows=[("Tony Teope", "Assistant to Mayor", "unknown", ["MWK-ARTA-1212"])])
        with patch.object(hunter, "discover_officers", return_value=[]), \
             patch.object(hunter, "active_roster", return_value=[]), \
             patch.object(hunter, "_table_exists", return_value=True), \
             patch.object(hunter, "_validate_candidate_matters"):
            roster = hunter.build_roster(cur)
        self.assertEqual(roster[0][0], "Tony Teope")
        self.assertEqual(roster[0][2], "unknown")
        self.assertEqual(roster[0][5], "agency_referral")

    def test_partial_scan_cannot_overwrite_client_candidates(self):
        hunter._MATTER[0] = "MWK-ARTA-1212"
        with self.assertRaises(ValueError):
            hunter.cmd_scan()

    def test_element_evidence_stays_in_candidate_matter(self):
        with patch.object(hunter, "_fetch_facts", return_value=[]) as facts, \
             patch.object(hunter, "_scoped_docs", return_value=[]) as docs:
            hunter._gather_element_evidence(Cursor(), ["Teope"], ["material_interest"], matter="MWK-ARTA-1212")
        self.assertEqual(facts.call_args.kwargs["scope"], "MWK-ARTA-1212")
        self.assertEqual(docs.call_args.kwargs["scope"], "MWK-ARTA-1212")

    def test_candidate_unknown_or_foreign_matter_rejected(self):
        for matters in ([], ["MWK%"], ["MWK-X", "PAR-X"], ["MWK-001"]):
            with self.assertRaises(ValueError):
                hunter._validate_candidate_matters(Cursor(rows=[("MWK-X",)]), matters)

    def test_candidate_owned_matter_accepted(self):
        hunter._validate_candidate_matters(Cursor(rows=[("MWK-X",)]), ["MWK-X"])

    def test_no_empty_element_automatically_proven(self):
        report, strength = hunter._element_gate(hunter.VIOLATIONS["ra6713_unspecified"], {})
        self.assertEqual(strength, 0)
        self.assertEqual(report["provision_and_elements"]["state"], "missing")

    def test_3i_is_covered_but_not_auto_ripe(self):
        template = hunter.VIOLATIONS["ra3019_3i"]
        self.assertEqual(len(template["elements"]), 4)
        signals = {s: True for e in template["elements"].values() for s in e["needs"]}
        profile = {"Target": {"office": "Office", "capacity": "appointive", "matters": {"MWK-X"},
                   "incidents": [(1, "doc:1", signals, "MWK-X"), (2, "doc:2", signals, "MWK-X")]}}
        row = next(c for c in hunter.build_candidates(profile) if c["violation_code"] == "ra3019_3i")
        self.assertEqual(row["status"], "building")

    def test_referral_alone_does_not_prove_3i(self):
        signals = {s: "doc:3754" for s in hunter._scan_signals("ARTA refers Tony Teope, Assistant to the Municipal Mayor, for alleged Section 3(i) of RA3019 violation")}
        report, _ = hunter._element_gate(hunter.VIOLATIONS["ra3019_3i"], signals)
        self.assertEqual(report["discretionary_approval"]["state"], "missing")
        self.assertEqual(report["personal_material_interest"]["state"], "missing")

    def test_legacy_operator_label_not_human_verified(self):
        label = hunter._review_label({"status": "held_for_filing", "provenance": "operator", "signals": {}})
        self.assertIn("human review not established", label)

    def test_ai_cannot_self_approve(self):
        row = {"id": 1, "official": "Target", "office": "Office", "capacity": "appointive",
               "matters": ["MWK-X"], "violation_code": "ra3019_3i", "statute": "RA3019 Sec.3(i)",
               "forum": "OMBUDSMAN", "leverage": 3,
               "elements": {k: {"label": e["label"], "state": "thin"} for k, e in hunter.VIOLATIONS["ra3019_3i"]["elements"].items()}}
        cur = Cursor(rows=[row])
        with patch.object(hunter, "_conn", return_value=Connection(cur)), \
             patch.object(hunter, "psycopg2", types.SimpleNamespace(extras=types.SimpleNamespace(DictCursor=object))), \
             patch.object(hunter, "_table_exists", return_value=True), \
             patch.object(hunter, "_validate_candidate_matters"), \
             patch.object(hunter, "_official_tokens", return_value=["Target"]), \
             patch.object(hunter, "_gather_element_evidence", return_value=[("doc:1", "source assertion")]), \
             patch.object(hunter, "_ollama", return_value='{"verdict":"have","why":"test"}'), \
             contextlib.redirect_stdout(io.StringIO()):
            hunter.cmd_verify("1")
        update, params = next((q, p) for q, p in cur.calls if "UPDATE ombudsman_candidates" in q)
        self.assertIn("provenance='inferred_strong'", update)
        self.assertEqual(params[1], "building")
        self.assertIn("NOT human-verified", params[5])

    def test_scan_preserves_agency_referrals_and_resets_machine_provenance(self):
        source = inspect.getsource(hunter.upsert)
        self.assertIn("? 'agency_referral'", source)
        self.assertIn("provenance=EXCLUDED.provenance", source)
        self.assertIn("_validate_candidate_matters", source)

    def test_mail_is_client_scoped_and_drafts_excluded(self):
        cur = Cursor()
        with contextlib.redirect_stdout(io.StringIO()):
            hunter._show_referrals(cur)
        query, params = cur.calls[-1]
        self.assertIn("g.client_code=%s", query)
        self.assertIn("'DRAFT'=ANY", query)
        self.assertEqual(params[0], "MWK-001")

    def test_playbook_keeps_incorporation_gate_and_client_output(self):
        source = inspect.getsource(hunter.cmd_playbook)
        self.assertIn("require_incorporation", source)
        self.assertIn('"matter": _client_code()', source)
        self.assertIn('UNVERIFIED REVIEW DRAFT', source)
        self.assertNotIn('or ["MWK%"]', source)


def unit_guards(_cur=None):
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream).run(unittest.defaultTestLoader.loadTestsFromTestCase(HunterGuards))
    if not result.wasSuccessful():
        raise AssertionError(stream.getvalue())
    print(f"      {result.testsRun} Hunter adversarial unit guards passed")


def referral_routing(cur):
    cur.execute("""SELECT count(*) AS n FROM truth_audit_log
                   WHERE table_name='ombudsman_referral_reconciliation'
                     AND row_pk->>'action'='ombudsman_referrals_20260907'""")
    assert cur.fetchone()["n"] == 1, "Reconciliation snapshot must use the canonical audit ledger"
    cur.execute("""SELECT count(*) AS n FROM matter_facts WHERE source_kind='doc' AND source_id='7697'
                   AND matter_code IS DISTINCT FROM 'MWK-OMB-IC-OC-JUL-26-1214'""")
    assert cur.fetchone()["n"] == 0, "Ombudsman forwarding facts drifted into another matter"
    cur.execute("""SELECT count(*) AS n FROM document_matter_links WHERE doc_id=7697
                   AND matter_code='MWK-CV26360'""")
    assert cur.fetchone()["n"] == 0, "Name-based civil-case autolinking has re-contaminated the indorsement"
    cur.execute("""SELECT count(*) AS n FROM matters WHERE client_code='MWK-001'
                   AND matter_code='MWK-OMB-IC-OC-JUL-26-1214'
                   AND docket_number='IC-OC-JUL-26-1214'""")
    assert cur.fetchone()["n"] == 1, "Exact Ombudsman reference is not tracked"
    cur.execute("""SELECT count(*) AS n FROM ombudsman_candidates WHERE client_code='MWK-001'
                   AND official='Tony Teope' AND violation_code='ra3019_3i'
                   AND signals ? 'agency_referral' AND status <> 'held_for_filing'""")
    assert cur.fetchone()["n"] == 1, "Agency-referred Teope lead is missing or was auto-promoted"


TESTS = [("ombudsman.unit_guards", unit_guards), ("ombudsman.referral_routing", referral_routing)]

if __name__ == "__main__":
    if "--unit" in sys.argv:
        unit_guards()
    else:
        from _harness import run
        passed, failed = run(TESTS)
        sys.exit(bool(failed))
