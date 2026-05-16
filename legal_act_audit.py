#!/usr/bin/env python3
"""legal_act_audit — score a doc against the PH validity-component rubric for its act type.

Per [[feedback_legal_act_validity_scrutiny]]: a document titled "Deed of X"
does NOT establish that the act occurred validly. Each legal act has a set of
components PH Civil Code requires; this script runs that rubric over each
legal-act doc and stores the result as an extraction_chunks row of type
'validity_audit'.

Usage:
  python3 legal_act_audit.py --doc 279
  python3 legal_act_audit.py --case MWK-001 --all-unaudited
  python3 legal_act_audit.py --doc 279 --json

Zero LLM cost. Pure pattern matching against extracted_text + structured fields.
Confidence calibration: a component that PASSES (regex found in text) is
"asserted_present"; PH validity components NOT in the document text are
"asserted_missing" — meaning they may exist elsewhere (RD annotation, BIR
records) but are not in THIS doc.
"""
import argparse
import json
import re
import sys
from landtek_core import DSN, db


# Per-act-type rubrics. Each component:
#   - key: short id
#   - test: regex matched against extracted_text + filename + classification
#   - civil_code_basis: short cite for the requirement
#   - external_evidence: True if this component CAN'T be found in the doc itself
#     (e.g., RD registration — requires looking at the source TCT, not this doc)
RUBRICS = {
    "DONATION": [
        ("public_instrument",    r"(?i)deed\s+of\s+donation|donation",                         "Civil Code Art 749 — public instrument", False),
        ("notary_block",         r"(?i)before me|notary public|doc\.?\s*no|series of\s*\d{4}", "Art 749 — public instrument", False),
        ("acceptance_by_donee",  r"(?i)accept|acknowledge|herein\s+receive|hereby\s+receive",  "Art 749 — acceptance must appear in same or separate instrument", False),
        ("acceptance_in_same_instr", r"(?i)accepts? this donation|hereby accept",              "Art 749 — preferred form", False),
        ("donee_capacity_lgu",   r"(?i)resolution\s*(?:no\.?)?\s*\d+|sangguniang|by\s+virtue\s+of",  "Art 745 — donee must have capacity (LGU needs Sangguniang authority)", False),
        ("donor_capacity",       r"(?i)of legal age|filipino|residing at|co-owner|guardian",   "Art 735 — donor must own", False),
        ("signatures",           r"(?i)signature|signed|sgd|sgd\.|nilagdaan",                   "Art 749", False),
        ("witnesses",            r"(?i)witness|in the presence of|witnesseth",                  "Art 805 (analog)", False),
        ("registration",         r"(?i)registered|registry of deeds|entry\s+no\.?|annotation", "Art 709 — binding vs 3rd parties", True),
        ("donors_tax_paid",      r"(?i)donor.{0,5}tax|BIR.{0,30}CAR|certificate.{0,15}authorizing\s+registration", "NIRC 98 + BIR rules", True),
        ("source_title_annotation", r"(?i)annotated\s+on\s+TCT|memo.{0,20}encumbrance", "Property Registration Decree", True),
    ],
    "DEED_OF_SALE": [
        ("public_instrument",    r"(?i)deed\s+of\s+(?:absolute\s+)?sale|sale of real property",  "Civil Code Art 1356, 1358", False),
        ("notary_block",         r"(?i)before me|notary public|doc\.?\s*no|series of\s*\d{4}",  "Art 1358", False),
        ("price_stated",         r"(?i)consideration\s+of|sum of|peso|₱|PHP\s*[\d,]+",          "Art 1458 — sale needs price", False),
        ("seller_capacity",      r"(?i)of legal age|filipino|owner|registered owner",            "Art 1459 — seller must be owner", False),
        ("buyer_personality",    r"(?i)of legal age|filipino|residing",                          "Art 1318 — capacity", False),
        ("if_aif_spa_cited",     r"(?i)attorney.in.fact|attorney-in-fact|by\s+virtue\s+of\s+SPA|special\s+power\s+of\s+attorney", "Art 1878 — if seller via AIF, SPA must authorize", False),
        ("signatures",           r"(?i)signature|signed|sgd|sgd\.",                              "Art 1356", False),
        ("witnesses",            r"(?i)witness|in the presence of",                              "Civil Code", False),
        ("cgt_paid",             r"(?i)capital gains\s+tax|CGT|BIR.{0,30}CAR",                   "NIRC 24(D), 27(D)", True),
        ("dst_paid",             r"(?i)documentary\s+stamp\s+tax|DST",                          "NIRC 196", True),
        ("transfer_tax_local",   r"(?i)transfer\s+tax|local\s+transfer\s+tax",                  "LGC 135", True),
        ("registration_new_tct", r"(?i)registered|new\s+title|TCT\s*No\.?\s*[T-]?\d+",          "PRD — Title transfer requires new TCT", True),
    ],
    "SPA": [
        ("public_instrument",    r"(?i)special\s+power\s+of\s+attorney|SPA",                    "Civil Code Art 1878 — specific powers require SPA", False),
        ("notary_block",         r"(?i)before me|notary public|doc\.?\s*no|series of\s*\d{4}",  "Art 1358", False),
        ("if_executed_abroad_consular",  r"(?i)consul|consulate|apostille|notary public.{0,30}\b(?:USA|US|California|Los Angeles|Washington)", "1923 Hague Convention / consular notarization", False),
        ("principal_identified", r"(?i)principal|hereby\s+appoint|of legal age",                "Art 1318", False),
        ("agent_identified",     r"(?i)attorney.in.fact|agent|hereinafter|hereby\s+designate", "", False),
        ("scope_enumerated",     r"(?i)to\s+sell|to\s+sign|to\s+execute|negotiate|specific power", "Art 1878 — must enumerate powers", False),
        ("signatures",           r"(?i)signature|signed|sgd|sgd\.",                              "", False),
    ],
    "REVOCATION_OF_SPA": [
        ("explicit_revocation",  r"(?i)revoke|revocation|hereby\s+cancel|terminate|rescind",     "Civil Code Art 1920", False),
        ("notarization",         r"(?i)before me|notary public",                                 "Art 1920 (if SPA was notarized, revocation should be)", False),
        ("notice_to_agent",      r"(?i)notice|served|aware|inform.{0,30}revocation",            "Art 1921 — notice to agent binds 3rd parties", False),
        ("references_specific_spa", r"(?i)SPA dated|special power.{0,30}dated|executed on\s+\d", "must identify the SPA being revoked", False),
        ("annotation_on_source", r"(?i)annotat.{0,30}TCT|RD.{0,30}annotation",                  "binding effect", True),
    ],
}


def detect_act_type(doc):
    """Map doc.classification + filename to one of the rubric keys."""
    cls = (doc.get("classification") or "").lower()
    fn = (doc.get("smart_filename") or "").lower()
    blob = cls + " " + fn
    if "donation" in blob: return "DONATION"
    if re.search(r"revocation|cancel.{0,15}spa|cancel.{0,15}power", blob): return "REVOCATION_OF_SPA"
    if "deed" in cls and ("sale" in blob or "absolute" in blob): return "DEED_OF_SALE"
    if "deed" in cls: return "DEED_OF_SALE"  # default deeds → sale
    if "spa" in blob or "special power" in blob or "power of attorney" in blob:
        return "SPA"
    return None


def audit_doc(doc):
    """Return validity report dict for a single doc."""
    act_type = detect_act_type(doc)
    if not act_type:
        return {"doc_id": doc["id"], "act_type": None,
                "error": "No matching rubric — doc classification/filename does not look like a legal act"}
    text = (doc.get("extracted_text") or "")
    components = []
    for key, pattern, basis, external in RUBRICS[act_type]:
        matched = bool(re.search(pattern, text))
        components.append({
            "component": key,
            "status": "asserted_present" if matched else ("external" if external else "asserted_missing"),
            "civil_code_basis": basis,
            "external_evidence_required": external,
        })
    n_internal = sum(1 for c in components if not c["external_evidence_required"])
    n_present_internal = sum(1 for c in components if c["status"] == "asserted_present"
                             and not c["external_evidence_required"])
    n_external_open = sum(1 for c in components if c["status"] == "external")
    return {
        "doc_id": doc["id"],
        "act_type": act_type,
        "components": components,
        "internal_components_present": f"{n_present_internal}/{n_internal}",
        "external_components_needed": n_external_open,
        "validity_summary": (
            "PARTIALLY_VERIFIED_internal_components_present_external_evidence_required"
            if n_present_internal >= max(1, n_internal - 1) and n_external_open > 0 else
            "ASSERTED_BUT_INCOMPLETE_internal_components_missing"
            if n_present_internal < n_internal else
            "FULLY_INTERNAL_VERIFIED_external_still_required"
        ),
    }


def store_audit(cur, doc_id, audit):
    """Write the audit as an extraction_chunks row of type 'validity_audit'."""
    cur.execute("""
        INSERT INTO extraction_chunks
          (doc_id, chunk_type, field_name, field_status, structured_value, provenance_level)
        VALUES (%s, 'validity_audit', 'validity_components', 'extracted', %s::jsonb, 'inferred_strong')
        ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
          SET structured_value = EXCLUDED.structured_value
    """, (doc_id, json.dumps(audit)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", type=int)
    ap.add_argument("--case", default=None)
    ap.add_argument("--all-unaudited", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", action="store_true", help="Write the audit to extraction_chunks")
    args = ap.parse_args()

    with db() as cur:
        if args.doc:
            cur.execute("""
                SELECT id, smart_filename, classification, execution_status, extracted_text
                  FROM documents WHERE id = %s
            """, (args.doc,))
            docs = cur.fetchall()
        elif args.all_unaudited:
            case_filter = "AND case_file = %s" if args.case else ""
            params = (args.case,) if args.case else ()
            cur.execute(f"""
                SELECT id, smart_filename, classification, execution_status, extracted_text
                  FROM documents
                 WHERE execution_status IN ('executed_filed','executed_notarized','government_issued')
                   AND (classification ILIKE '%deed%' OR classification ILIKE '%donation%'
                        OR classification ILIKE '%power of attorney%' OR classification ILIKE '%spa%'
                        OR smart_filename ILIKE '%deed%' OR smart_filename ILIKE '%donation%'
                        OR smart_filename ILIKE '%spa%' OR smart_filename ILIKE '%revocation%')
                   {case_filter}
                   AND NOT EXISTS (
                     SELECT 1 FROM extraction_chunks ec
                      WHERE ec.doc_id = documents.id AND ec.chunk_type='validity_audit'
                   )
                 LIMIT 100
            """, params)
            docs = cur.fetchall()
        else:
            sys.exit("Usage: --doc N | --all-unaudited [--case MWK-001]")

        results = []
        for d in docs:
            audit = audit_doc(d)
            results.append(audit)
            if args.apply and audit.get("act_type"):
                store_audit(cur, d["id"], audit)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        for r in results:
            if not r.get("act_type"):
                print(f"doc#{r['doc_id']}  {r.get('error','no rubric')}")
                continue
            print(f"\n══ doc#{r['doc_id']}  ACT: {r['act_type']}")
            print(f"   Summary: {r['validity_summary']}")
            print(f"   Internal: {r['internal_components_present']}  External pending: {r['external_components_needed']}")
            for c in r["components"]:
                icon = {"asserted_present":"✓", "asserted_missing":"✗", "external":"○"}[c["status"]]
                kind = " [EXT]" if c["external_evidence_required"] else ""
                print(f"   {icon} {c['component']:30s}  {c['civil_code_basis']}{kind}")


if __name__ == "__main__":
    main()
