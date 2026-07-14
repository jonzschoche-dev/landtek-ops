#!/usr/bin/env python3
"""truth_layer_fitness.py — Truth-Layer Fitness Harness v1 (docs/TRUTH_LAYER_FITNESS_SPEC.md, Part I).

Measures whether LandTek's information is available, parsed, grounded, consistent/current, and findable —
across five dimensions whose sub-measurements are kept SEPARATE (no aggregate can hide a critical failure).
Mechanical + $0 (no model on the measurement path). Read-only on facts (runs under `SET ROLE tlfh_harness`),
append-only on its ledger (DB trigger). Writes NO facts, verifies nothing, deploys nothing.

  python3 scripts/truth_layer_fitness.py               # run one cycle over the MWK title spine + scorecard
  python3 scripts/truth_layer_fitness.py --domains     # list domain adapters + instrumented/not_instrumented

Domain-agnostic: the unit is (domain, object_type, object_id) graded via a DomainAdapter. v1 INSTRUMENTS the
legal/title-document adapter (real data); the other seven are defined-interface stubs → 'not_instrumented'
(a domain with no data yields no objects, never false gaps).
"""
import json
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
GRADER_VERSION = "tlfh-v1"
DIMENSIONS = ("availability", "parsing", "grounding", "consistency", "findability")

# MWK title spine = titles reachable in title_chain from the mother title T-4497 (deterministic).
_SPINE_CTE = """WITH RECURSIVE d AS (
    SELECT tct_number FROM titles WHERE tct_number='T-4497'
    UNION SELECT tc.child_title FROM title_chain tc JOIN d ON tc.parent_title=d.tct_number)
  SELECT tct_number FROM d"""


def _rows(cur, sql, args=None):
    cur.execute(sql, args or ())
    return cur.fetchall()


def _one(cur, sql, args=None):
    cur.execute(sql, args or ())
    return cur.fetchone()


# ── retrieval (findability) — VPS-native: the venv embeds the query, THIS cursor does the pgvector search.
# rag_embed_local is a Mac-side tool (it ssh's into the VPS); we do not reuse it here. $0, read-only. ──
import subprocess
EMBED_VENV = os.environ.get("TLFH_EMBED_VENV", "/root/landtek/.venv-tlfh/bin/python")
EMBED_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tlfh_embed.py")


def _semantic_hits(cur, query, k=8, ids=None):
    """Top-k rag_local doc_ids for the query, or None if the embedder isn't provisioned (→ not_tested).
    The venv subprocess ONLY embeds; the ORDER BY embedding <=> query runs on the restricted harness cursor."""
    if not (EMBED_VENV and os.path.exists(EMBED_VENV) and os.path.exists(EMBED_HELPER)):
        return None
    try:
        r = subprocess.run([EMBED_VENV, EMBED_HELPER, query], capture_output=True, text=True, timeout=120)
        qv = (r.stdout or "").strip()
        if not qv.startswith("["):
            return None
        if ids:
            cur.execute("SELECT doc_id FROM rag_local WHERE doc_id = ANY(%s) "
                        "ORDER BY embedding <=> %s::vector LIMIT %s", (list(ids), qv, k))
        else:
            cur.execute("SELECT doc_id FROM rag_local ORDER BY embedding <=> %s::vector LIMIT %s", (qv, k))
        return [str(row["doc_id"]) for row in cur.fetchall()]
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# DomainAdapter contract
# ════════════════════════════════════════════════════════════════════════════════════════════════════
class DomainAdapter:
    domain = "abstract"
    status = "not_instrumented"

    def enumerate_objects(self, cur):
        return []

    def grade(self, cur, object_type, object_id, ctx):
        return []


def _m(dim, sub, value, numeric=None, basis=None, target=None):
    return {"dimension": dim, "submeasure": sub, "value": str(value),
            "numeric": numeric, "basis": basis, "target": target}


class LegalTitleAdapter(DomainAdapter):
    """The one instrumented adapter in v1: MWK title spine + the instruments recorded on those titles."""
    domain = "legal"
    status = "instrumented"

    def enumerate_objects(self, cur):
        objs = []
        for r in _rows(cur, _SPINE_CTE):
            objs.append(("title", r["tct_number"], "MWK-001"))
        spine = [r["tct_number"] for r in _rows(cur, _SPINE_CTE)]
        if spine:
            for r in _rows(cur, "SELECT id FROM instruments_on_title WHERE parent_tct_number = ANY(%s)", (spine,)):
                objs.append(("instrument", str(r["id"]), "MWK-001"))
        return objs

    # ---- context shared across objects in a cycle (MWK doc set for scoped retrieval) ----
    def context(self, cur):
        docs = _rows(cur, "SELECT id FROM documents WHERE case_file='MWK-001' OR matter_code='MWK-001'")
        return {"mwk_doc_ids": [d["id"] for d in docs]}

    def grade(self, cur, object_type, object_id, ctx):
        return self._grade_title(cur, object_id, ctx) if object_type == "title" \
            else self._grade_instrument(cur, object_id, ctx)

    # ---------------------------------------------------------------- TITLE
    def _grade_title(self, cur, tct, ctx):
        t = _one(cur, """SELECT tct_number, case_file, registrant_name_raw, registrant_canonical, issued_date,
                                parent_title, source_doc_id, location, area_sqm, provenance_level,
                                provenance_notes, cancelled_by_title, status, lifecycle_status
                           FROM titles WHERE tct_number=%s""", (tct,))
        if not t:
            return []
        out = []
        # 1. Availability & connectivity
        src = t["source_doc_id"]
        doc = _one(cur, "SELECT id, content_hash, sha256, extracted_text, text_length, classification, "
                        "document_type FROM documents WHERE id=%s", (src,)) if src else None
        out.append(_m("availability", "source_doc_present", bool(src),
                      target=None if src else {"action": "retrieve", "what": f"source document for {tct}"}))
        out.append(_m("availability", "bytes_present", bool(doc and (doc["content_hash"] or doc["sha256"])),
                      basis={"doc_id": src}))
        out.append(_m("availability", "custody_hash_ok", "not_tested"))   # binary not reachable from SQL — honest
        out.append(_m("availability", "bound_to_client", bool(t["case_file"]), basis={"case_file": t["case_file"]}))
        out.append(_m("availability", "bound_to_parent", bool(t["parent_title"]) or tct == "T-4497"))
        # 2. Parsing & structural coverage (title face-fields)
        fields = {"registrant": t["registrant_canonical"] or t["registrant_name_raw"], "issued_date": t["issued_date"],
                  "location": t["location"], "area_sqm": t["area_sqm"], "parent_title": t["parent_title"]}
        present = sum(1 for v in fields.values() if v not in (None, ""))
        pct = round(100.0 * present / len(fields), 1)
        out.append(_m("parsing", "title_fields_pct", f"{pct}%", numeric=pct,
                      basis={"present": present, "of": len(fields)},
                      target=None if pct == 100 else {"action": "parse", "what": f"missing title fields on {tct}"}))
        out.append(_m("parsing", "classified", bool(doc and (doc["classification"] or doc["document_type"])),
                      basis={"classification": doc["classification"] if doc else None}))
        readable = bool(doc and (doc["text_length"] or 0) >= 50)
        out.append(_m("parsing", "readable", readable,
                      target=None if readable else {"action": "reocr", "what": f"doc:{src}"} if src else None))
        # 3. Grounding & provenance (NB: a recorded title is not a validity judgment)
        prov = t["provenance_level"]
        out.append(_m("grounding", "provenance_level", prov or "none", basis={"provenance_notes": t["provenance_notes"]}))
        grounded = prov == "verified" and bool(src)
        out.append(_m("grounding", "grounded", grounded,
                      target=None if grounded else {"action": "verification_pass",
                                                    "what": f"{tct} provenance={prov or 'none'}"}))
        # 4. Consistency & freshness
        holes = _one(cur, "SELECT count(*) n FROM holes_findings WHERE status='open' AND doc_id=%s", (src,)) if src else None
        no_contra = not (holes and holes["n"])
        out.append(_m("consistency", "no_open_contradiction", no_contra,
                      target=None if no_contra else {"action": "adjudicate", "what": f"open holes on doc:{src}"}))
        superseded = bool(t["cancelled_by_title"])
        out.append(_m("consistency", "not_superseded", not superseded,
                      basis={"cancelled_by_title": t["cancelled_by_title"]}))
        # 5. Findability & answerability (NEVER demotes grounding — its own axis)
        out.extend(self._findability(cur, tct, src, f"title {tct} registrant issued status chain", ctx))
        return [o for o in out if o]

    # ---------------------------------------------------------------- INSTRUMENT
    def _grade_instrument(self, cur, iid, ctx):
        r = _one(cur, """SELECT id, doc_id, parent_tct_number, instrument_type, executor_full_name, authority_basis,
                                notary_name, consideration_amount, provenance_level, source_quote_full
                           FROM instruments_on_title WHERE id=%s""", (iid,))
        if not r:
            return []
        out = []
        src = r["doc_id"]
        out.append(_m("availability", "source_doc_present", bool(src),
                      target=None if src else {"action": "retrieve", "what": f"source doc for instrument {iid}"}))
        out.append(_m("availability", "bound_to_title", bool(r["parent_tct_number"]),
                      basis={"parent_tct": r["parent_tct_number"]}))
        fields = {"instrument_type": r["instrument_type"], "executor": r["executor_full_name"],
                  "authority_basis": r["authority_basis"], "notary": r["notary_name"],
                  "consideration": r["consideration_amount"]}
        present = sum(1 for v in fields.values() if v not in (None, ""))
        pct = round(100.0 * present / len(fields), 1)
        out.append(_m("parsing", "instrument_fields_pct", f"{pct}%", numeric=pct,
                      basis={"present": present, "of": len(fields)},
                      target=None if pct == 100 else {"action": "parse", "what": f"missing instrument fields on {iid}"}))
        prov = r["provenance_level"]
        out.append(_m("grounding", "provenance_level", prov or "none"))
        out.append(_m("grounding", "source_quote_present", bool(r["source_quote_full"])))
        grounded = prov == "verified" and bool(r["source_quote_full"])
        out.append(_m("grounding", "grounded", grounded,
                      target=None if grounded else {"action": "verification_pass", "what": f"instrument {iid}"}))
        # consistency: contradiction only (validity/authority is a SEPARATE, human-reviewed question — never here)
        holes = _one(cur, "SELECT count(*) n FROM holes_findings WHERE status='open' AND doc_id=%s", (src,)) if src else None
        no_contra = not (holes and holes["n"])
        out.append(_m("consistency", "no_open_contradiction", no_contra))
        out.extend(self._findability(cur, iid, src, f"instrument {r['instrument_type'] or ''} {r['executor_full_name'] or ''}", ctx))
        return [o for o in out if o]

    # ---------------------------------------------------------------- findability (shared) — returns a LIST
    def _findability(self, cur, obj_id, src, question, ctx):
        """Two sub-measures, kept separate: `indexed` (first-order, deterministic, $0 — is the grounding doc
        embedded at all? a doc absent from rag_local is unretrievable by construction) and `semantic_recall`
        (second-order — does it rank for a natural query; needs the Mac-side query embedder, deferred here)."""
        if not src:
            return [_m("findability", "indexed", "not_tested", basis={"reason": "no source doc"}),
                    _m("findability", "semantic_recall", "not_tested", basis={"reason": "no source doc"})]
        out = []
        n = _one(cur, "SELECT count(*) n FROM rag_local WHERE doc_id=%s", (src,))["n"]
        if n:
            out.append(_m("findability", "indexed", "True", numeric=n, basis={"chunks": n}))
        else:
            out.append(_m("findability", "indexed", "False",
                          target={"action": "embed", "what": f"doc:{src} absent from rag_local — unretrievable"}))
        if ctx.get("no_semantic"):        # tests/fast path: skip the second-order probe
            out.append(_m("findability", "semantic_recall", "not_tested", basis={"reason": "semantic probe disabled"}))
            return out
        hits = _semantic_hits(cur, question, 8, ctx.get("mwk_doc_ids") or None)
        if hits is None:
            out.append(_m("findability", "semantic_recall", "not_tested", basis={"reason": "embedder not provisioned"}))
        elif str(src) in hits:
            out.append(_m("findability", "semantic_recall", "found", numeric=hits.index(str(src)) + 1,
                          basis={"rank": hits.index(str(src)) + 1}))
        else:
            out.append(_m("findability", "semantic_recall", "missed",
                          target={"action": "reembed_or_query_fix", "what": f"doc:{src} not in top-8 for its object"}))
        return out


class MappingAdapter(DomainAdapter):
    """Second instrumented adapter (proves domain-agnostic on non-legal data). Grades whatever real parcels
    exist in map_parcels — currently a nascent corpus (n≈1); it scales automatically as parcels are plotted."""
    domain = "mapping"
    status = "instrumented"

    def enumerate_objects(self, cur):
        return [("parcel", str(r["id"]), r["client_code"]) for r in _rows(cur, "SELECT id, client_code FROM map_parcels")]

    def grade(self, cur, object_type, object_id, ctx):
        r = _one(cur, "SELECT * FROM map_parcels WHERE id=%s", (object_id,))
        if not r:
            return []
        out = []
        out.append(_m("availability", "geometry_present", bool(r["geom_geojson"]),
                      target=None if r["geom_geojson"] else {"action": "plot", "what": f"parcel {object_id} has no geometry"}))
        out.append(_m("availability", "bound_to_client", bool(r["client_code"])))
        out.append(_m("availability", "bound_to_title", bool(r["title_no"])))
        out.append(_m("parsing", "area_computed", bool(r["area_sqm"]),
                      numeric=float(r["area_sqm"]) if r["area_sqm"] else None))
        out.append(_m("parsing", "centroid_present", bool(r["centroid_lat"] and r["centroid_lng"])))
        tier = r["accuracy_tier"]
        grounded = tier in ("survey", "orthomosaic", "ortho") and bool(r["source_note"])
        out.append(_m("grounding", "accuracy_tier", tier or "none"))
        out.append(_m("grounding", "survey_grade", grounded,             # approximate/satellite is NOT truth-grade
                      target=None if grounded else {"action": "survey_or_source",
                                                    "what": f"parcel {object_id} tier={tier or 'none'} not survey-grade/cited"}))
        out.append(_m("consistency", "area_agrees", not bool(r["area_flag"]),
                      basis={"stated": str(r["stated_area_sqm"]), "computed": str(r["area_sqm"])},
                      target={"action": "reconcile_area", "what": f"parcel {object_id} plot-vs-title area flagged"}
                      if r["area_flag"] else None))
        out.append(_m("findability", "indexed", "not_tested", basis={"reason": "parcel has no direct source-doc link"}))
        return out


# The remaining not-yet-instrumented domains (defined interface, zero objects → zero false gaps).
class StubAdapter(DomainAdapter):
    def __init__(self, domain):
        self.domain = domain


ADAPTERS = {"legal": LegalTitleAdapter(), "mapping": MappingAdapter()}
for _d in ("tenants", "mining", "accounting", "property", "communications", "business"):
    ADAPTERS[_d] = StubAdapter(_d)


# ════════════════════════════════════════════════════════════════════════════════════════════════════
def _prev_value(cur, object_pk, dim, sub):
    r = _one(cur, "SELECT value FROM fitness_measurement WHERE object_pk=%s AND dimension=%s AND submeasure=%s "
                  "ORDER BY id DESC LIMIT 1", (object_pk, dim, sub))
    return r["value"] if r else None


def _fingerprint(cur):
    snap = {t: _one(cur, f"SELECT count(*) n FROM {t}")["n"]
            for t in ("titles", "title_chain", "instruments_on_title", "matter_facts", "documents")}
    return {"grader_version": GRADER_VERSION, "schema_version": "tlfh-1",
            "code_git_sha": os.environ.get("LANDTEK_GIT_SHA", "unknown"),
            "ontology_version": os.environ.get("LANDTEK_ONTOLOGY_VERSION", "n/a"),
            "source_snapshot": snap}


def run_cycle(cur, domain="legal", cohort="mwk_spine", print_card=True):
    """One grading cycle for a domain. Read-only on facts (SET ROLE), append-only to the ledger."""
    adapter = ADAPTERS[domain]
    if adapter.status != "instrumented":
        if print_card:
            print(f"[tlfh] domain '{domain}' is not_instrumented — no objects, no gaps (by design).")
        return {"status": "not_instrumented", "domain": domain}
    ctx = adapter.context(cur) if hasattr(adapter, "context") else {}
    objs = adapter.enumerate_objects(cur)

    # Pass 1: grade every object into memory (upsert the registry, gather measurements + the rollup). We
    # compute the rollup BEFORE inserting the cycle row so the restricted role never needs UPDATE on it.
    graded = []                      # [(opk, [measurement, ...])]
    tally = {d: {} for d in DIMENSIONS}
    n_targets = 0
    for object_type, object_id, client in objs:
        cur.execute("""INSERT INTO fitness_object (domain, object_type, object_id, client_code, last_graded)
                       VALUES (%s,%s,%s,%s, now())
                       ON CONFLICT (domain, object_type, object_id)
                       DO UPDATE SET last_graded=now(), client_code=EXCLUDED.client_code RETURNING id""",
                    (domain, object_type, object_id, client))
        opk = cur.fetchone()["id"]
        meas = adapter.grade(cur, object_type, object_id, ctx)
        graded.append((opk, meas))
        for m in meas:
            tally[m["dimension"]][f"{m['submeasure']}={m['value']}"] = \
                tally[m["dimension"]].get(f"{m['submeasure']}={m['value']}", 0) + 1
            if m["target"]:
                n_targets += 1

    # Insert the cycle row (with the rollup already known), then the measurements FK to it.
    fp = _fingerprint(cur)
    kc = {"n_objects": len(objs), "n_weakness_targets": n_targets}
    cur.execute("INSERT INTO fitness_cycle (domain, cohort, n_objects, per_dimension, fingerprint, kill_criteria) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (domain, cohort, len(objs), json.dumps(tally), json.dumps(fp), json.dumps(kc)))
    cycle_id = cur.fetchone()["id"]
    for opk, meas in graded:
        for m in meas:
            prev = _prev_value(cur, opk, m["dimension"], m["submeasure"])
            cur.execute("""INSERT INTO fitness_measurement
                            (cycle_id, object_pk, dimension, submeasure, value, numeric_val, basis, weakness_target, prev_value)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (cycle_id, opk, m["dimension"], m["submeasure"], m["value"], m["numeric"],
                         json.dumps(m["basis"]) if m["basis"] else None,
                         json.dumps(m["target"]) if m["target"] else None, prev))
    if print_card:
        _scorecard(domain, cohort, len(objs), n_targets, tally, cycle_id)
    return {"status": "ok", "cycle_id": cycle_id, "n_objects": len(objs), "per_dimension": tally}


def _scorecard(domain, cohort, n, n_targets, tally, cycle_id):
    print(f"\n{'='*70}\nTRUTH-LAYER FITNESS — domain={domain} cohort={cohort} objects={n} (cycle #{cycle_id})\n{'='*70}")
    for dim in DIMENSIONS:
        print(f"\n[{dim}]")
        for k, v in sorted(tally[dim].items(), key=lambda x: -x[1]):
            print(f"   {v:4d}  {k}")
    print(f"\n>> {n_targets} named remediation targets emitted (the actionable weakness queue).")
    print(f">> ledger: fitness_measurement (cycle_id={cycle_id}); no facts written; nothing deployed.\n")


# deterministic weakness → matched remediation (a DESCRIPTION; never executed by the harness)
_REMEDIATION_ACTION = {
    "verification_pass": "Queue a human/governed verification of this object's grounding through the A77/A78 "
                         "path (source doc + verify step). The harness NEVER sets provenance='verified'.",
    "parse": "Re-run the domain parser to fill the missing structured fields; re-graded next cycle.",
    "embed": "Embed the source document into rag_local so the object becomes retrievable.",
    "reocr": "Re-OCR the source document (readability below threshold).",
    "reembed_or_query_fix": "Re-embed the doc or fix the retrieval query — grounding is unchanged.",
    "adjudicate": "Route the open contradiction to A78 for human adjudication.",
    "reconcile_area": "Reconcile plotted geometry against the title's stated area (surveyor/human).",
    "survey_or_source": "Obtain a survey-grade plot or cite the geometry's source.",
    "retrieve": "Retrieve the missing source binary.",
    "plot": "Plot the parcel geometry.",
}


def remediate(cur, only=None, print_report=True):
    """SHADOW remediation: turn each open weakness into a CANDIDATE (with its matched, human-readable action)
    in the dedicated candidate lane. Writes NO facts, sets nothing verified, executes nothing. A human/
    governed step promotes candidates onward. Idempotent (one candidate per weakness)."""
    q = "SELECT g.*, o.id AS opk FROM v_fitness_gaps g JOIN fitness_object o " \
        "ON o.domain=g.domain AND o.object_type=g.object_type AND o.object_id=g.object_id"
    args = ()
    if only:
        q += " WHERE g.remediation=%s"; args = (only,)
    rows = _rows(cur, q, args)
    n = 0
    for g in rows:
        action = _REMEDIATION_ACTION.get(g["remediation"], f"Manual review: {g['remediation']}")
        cur.execute("""INSERT INTO fitness_remediation_candidate
            (object_pk, domain, object_type, object_id, client_code, dimension, submeasure, remediation, target, proposed_action)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (object_pk, dimension, submeasure) DO NOTHING""",
            (g["opk"], g["domain"], g["object_type"], g["object_id"], g["client_code"], g["dimension"],
             g["submeasure"], g["remediation"], json.dumps(g["target"]) if g["target"] else None, action))
        n += cur.rowcount
    if print_report:
        print(f"[remediate] {len(rows)} open weaknesses → {n} new candidate(s) queued (shadow; no facts written).")
        for r in _rows(cur, "SELECT remediation, count(*) n FROM fitness_remediation_candidate "
                            "WHERE status='candidate' GROUP BY remediation ORDER BY n DESC"):
            print(f"   {r['n']:>4}  {r['remediation']}")
    return {"open": len(rows), "queued": n}


def trend_report(cur):
    rows = _rows(cur, "SELECT * FROM v_fitness_trend WHERE domain='legal'")
    print(f"\n{'='*70}\nFITNESS TREND (legal) — grounding coverage cycle-over-cycle\n{'='*70}")
    print(f"{'cycle':>6}{'objects':>9}{'grounded':>18}{'coverage':>11}{'Δ':>8}{'targets':>9}")
    prev = None
    for r in rows:
        gt, g = r["grounded_total"] or 0, r["grounded"] or 0
        pct = 100.0 * g / gt if gt else 0.0
        delta = "" if prev is None else f"{pct - prev:+.1f}"
        print(f"{r['cycle_id']:>6}{r['n_objects'] or 0:>9}{f'{g}/{gt}':>18}{f'{pct:.1f}%':>11}{delta:>8}{r['open_targets'] or 0:>9}")
        prev = pct
    regr = _one(cur, "SELECT count(*) n FROM v_fitness_gaps WHERE regressed")
    print(f"\n>> regressions currently open (grounded→worse): {regr['n']}\n")


def gaps_report(cur, limit=12):
    """The prioritized weakness queue (v_fitness_gaps) — what the remediation loop acts on. Read-only."""
    rows = _rows(cur, "SELECT remediation, dimension, count(*) n, sum(regressed::int) regressed "
                      "FROM v_fitness_gaps GROUP BY remediation, dimension ORDER BY n DESC")
    total = _one(cur, "SELECT count(*) n, sum(regressed::int) r FROM v_fitness_gaps")
    print(f"\n{'='*70}\nFITNESS GAP QUEUE — {total['n']} open weaknesses "
          f"({total['r'] or 0} regressions)\n{'='*70}")
    print(f"{'remediation':<22}{'dimension':<16}{'count':>7}{'regressed':>11}")
    for r in rows:
        print(f"{(r['remediation'] or '?'):<22}{r['dimension']:<16}{r['n']:>7}{r['regressed'] or 0:>11}")
    print("\ntop objects awaiting the most remediations:")
    for r in _rows(cur, "SELECT object_type, object_id, count(*) n FROM v_fitness_gaps "
                        "GROUP BY object_type, object_id ORDER BY n DESC LIMIT %s", (limit,)):
        print(f"   {r['n']:>3}  {r['object_type']}:{r['object_id']}")
    print()


def main():
    if "--domains" in sys.argv:
        for d, a in ADAPTERS.items():
            print(f"  {d:15s} {a.status}")
        return
    for flag, fn in (("--gaps", gaps_report), ("--trend", trend_report), ("--remediate", remediate)):
        if flag in sys.argv:
            conn = psycopg2.connect(DSN); conn.autocommit = (flag != "--remediate")
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute("SET ROLE tlfh_harness")
                fn(cur)
                if flag == "--remediate":
                    conn.commit()
            finally:
                cur.close(); conn.close()
            return
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SET ROLE tlfh_harness")   # read-only on facts, append-only on ledger — enforced by DB
        run_cycle(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
