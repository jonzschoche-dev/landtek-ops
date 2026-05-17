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
    "AFFIDAVIT": [
        ("affiant_identified",   r"(?i)I,?\s+[A-Z][A-Z\s\.,]+|affiant|of legal age|filipino|american citizen", "Civil Code / Rules of Court — affiant capacity", False),
        ("affiant_address",      r"(?i)residing at|with residence at|presently residing",        "identification req", False),
        ("under_oath",           r"(?i)under oath|sworn to|after having been duly sworn|do hereby state under oath", "Rules of Court Rule 41 — oath required", False),
        ("jurat_block",          r"(?i)subscribed and sworn|sworn before me|in my presence",     "Rules on Notarial Practice 2004 Sec. 6 (jurat)", False),
        ("notarization",         r"(?i)before me|notary public|doc\.?\s*no|page\s*no|book\s*no", "Rules on Notarial Practice", False),
        ("id_presented_at_jurat",r"(?i)passport|driver.{0,5}license|TIN|SSS|Philippine ID|PhilSys|UMID|government[\s-]issued", "Notarial Rules — competent evidence of identity", False),
        ("signature",            r"(?i)signature|signed|sgd|nilagdaan",                          "Rules", False),
    ],
    "JUDICIAL_AFFIDAVIT": [
        ("case_caption",         r"(?i)civil case no|crim(inal)?\s+case|sp\.\s*proc|case no\.?\s*\d", "JA Rule — case caption", False),
        ("qa_format",            r"(?i)Q\d|Q:\d|S\d|A\d|^Q\s|^A\s",                              "JA Rule Sec. 3 — Q&A direct examination format", False),
        ("affiant_identified",   r"(?i)I,?\s+[A-Z][A-Z\s\.,]+|of legal age",                    "JA Rule", False),
        ("under_oath",           r"(?i)under oath|sworn",                                        "JA Rule", False),
        ("jurat_block",          r"(?i)subscribed and sworn|sworn before me",                    "JA Rule + Notarial Rules", False),
        ("counsel_certification",r"(?i)attorney|atty\.?|counsel for|undersigned counsel",        "JA Rule Sec. 4 — counsel must certify", False),
        ("notarization",         r"(?i)before me|notary public|doc\.?\s*no",                    "Notarial Rules", False),
    ],
    "COURT_ORDER": [
        ("court_header",         r"(?i)regional trial court|RTC|municipal trial court|MTC|court of appeals|supreme court|branch\s+\d", "Court identifies itself", False),
        ("case_caption",         r"(?i)civil case no|crim(inal)?\s+case|G\.R\.\s+No|case no\.?", "Identification of case", False),
        ("operative_clause",     r"(?i)WHEREFORE|IT IS SO ORDERED|SO ORDERED|IT IS HEREBY|the court hereby",  "Disposition language", False),
        ("judge_signature_block",r"(?i)judge|presiding|hon\.?\s+|honorable",                    "Signed by adjudicating judge", False),
        ("date",                 r"(?i)\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)|date.{0,3}\d{4}", "Issuance date", False),
        ("served_on_parties",    r"(?i)copy furnished|cf:|served on|registered mail|personally served", "Rule 13 service requirements", True),
    ],
    "NOTICE": [
        ("issuer_header",        r"(?i)regional trial court|RTC|MTC|ARTA|registry of deeds|department of|bureau of|office of", "Issuer identification", False),
        ("case_or_matter_ref",   r"(?i)civil case|crim(inal)?\s+case|CTN SL|case no|matter|re:|in re", "What this notice is about", False),
        ("addressee",            r"(?i)to:\s|dear\s|notice (?:is hereby )?given to|attention", "Who is being notified", False),
        ("date_of_event",        r"(?i)(?:on|at|by)\s+\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)|\bset for\b|scheduled", "When the event occurs", False),
        ("authorized_signature", r"(?i)clerk of court|sheriff|deputy|in charge|atty\.|hon\.|by order of", "Authority issuing", False),
        ("proof_of_service",     r"(?i)by\s+(?:registered|personal)|copy furnished|served on|delivery", "Rule 13 / agency service requirement", True),
    ],
    "PLEADING": [
        ("caption",              r"(?i)republic of the philippines|RTC|MTC|civil case|case no|in re|for:\s",  "Rule 7 — caption required", False),
        ("body_of_allegations",  r"(?i)plaintiff(?:'s)?|defendant(?:'s)?|petitioner|respondent|allege",  "Substantive content", False),
        ("prayer",               r"(?i)WHEREFORE|premises considered|prays|relief|grant",       "Rule 7 Sec. 2 — prayer required", False),
        ("verification",         r"(?i)verification|verified|under oath|I,?\s+[A-Z][A-Z\s\.]+,?.{0,80}affirm",  "Rule 7 Sec. 4 — verification (for required pleadings)", False),
        ("counsel_signature",    r"(?i)atty\.?\s+[A-Z]|counsel for|undersigned|roll no|IBP|PTR",  "Rule 7 Sec. 3 — counsel signs", False),
        ("certification_non_forum_shopping", r"(?i)non.forum.shopping|certification of non.forum",  "Rule 7 Sec. 5 — required for initiatory pleadings", False),
        ("filed_stamp",          r"(?i)received|filed|filing\s+stamp|date filed",                "Rule 13 — court receiving", True),
        ("proof_of_service",     r"(?i)copy furnished|cf:|registered mail|personal service",    "Rule 13", True),
    ],
    "TITLE": [
        ("title_number",         r"(?i)transfer certificate of title|original certificate of title|TCT\s*(?:No\.?)?\s*[T-]?\s*\d+|OCT", "PRD — title identification", False),
        ("registry_header",      r"(?i)registry of deeds|register of deeds",                    "Land Registration Authority", False),
        ("registered_owner",     r"(?i)is registered in the name of|name of|registered to",     "PRD — ownership", False),
        ("technical_description",r"(?i)parcel of land|lot \d+|psd|psu|bcs|bearings|hectares|sqm|square meters", "PRD — technical description", False),
        ("date_original_registration", r"(?i)originally registered|originally issued|registered\s+on", "Provenance to OCT", False),
        ("rd_signature",         r"(?i)register of deeds|registrar|signed.{0,30}registry|sealed|(R\. ?of\.? ?D\.?)", "Authority", False),
        ("no_cancellation",      r"(?i)cancelled by virtue|this certificate is cancelled",      "Currency check — INVERTED — match means TITLE IS CANCELLED", True),
    ],
    "TAX_DOCUMENT": [
        ("arp_or_taxdec_number", r"(?i)ARP\s*no\.?|tax\s+dec(laration)?\s+no\.?|tax dec\.?\s*no",  "LGC — identifier", False),
        ("year_or_effectivity",  r"(?i)effectivity|for the year|tax year|FY\s+\d{4}|series",      "year ARP applies", False),
        ("owner_name",           r"(?i)declared owner|owner|in the name of",                      "owner identification", False),
        ("property_description", r"(?i)lot\s+\d|area|sqm|hectares|barangay|brgy",                 "subject property", False),
        ("assessed_value",       r"(?i)assessed value|assessed\s+at|₱|PHP|peso",                 "valuation present", False),
        ("assessor_signature",   r"(?i)assessor|provincial assessor|municipal assessor",         "issuing authority", False),
    ],
    "RECEIPT": [
        ("receipt_number",       r"(?i)O\.?\s*R\.?\s*(?:no\.?)?\s*\d|official receipt|receipt no", "OR identification", False),
        ("date",                 r"(?i)date\s*:|or\s+date\s*:|\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\b\d{4}-\d{2}-\d{2}", "OR date", False),
        ("amount",               r"(?i)amount|₱|PHP|peso|\b\d+\.\d{2}\b",                       "amount paid", False),
        ("payor_or_payee",       r"(?i)received from|payor|payee|paid by|in payment of",        "parties", False),
        ("purpose",              r"(?i)nature|in payment of|particulars|description",          "what was paid for", False),
    ],
    "RESOLUTION_LGU": [
        ("resolution_number",    r"(?i)resolution\s*no\.?\s*\d|kapasiyahan",                    "Sanggunian Resolution numbering", False),
        ("series",               r"(?i)series of\s*\d{4}|s\.\s*\d{4}",                          "Year",  False),
        ("body_name",            r"(?i)sangguniang|sb|municipal council|barangay council|provincial board", "Issuing body", False),
        ("operative_clause",     r"(?i)RESOLVED|BE IT RESOLVED|IT IS HEREBY RESOLVED|kapasiyahan", "Disposition", False),
        ("date_adopted",         r"(?i)adopted|approved on|enacted on",                          "When passed", False),
    ],
    "LETTER": [
        ("date",                 r"(?i)\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)|\b\d{4}-\d{2}-\d{2}", "letter date", False),
        ("addressee",            r"(?i)to:|dear\s+|attention:",                                  "recipient identification", False),
        ("subject_or_re",        r"(?i)re:\s|subject:\s|reference:",                            "topic", False),
        ("body",                 r"(?i)[A-Z].{40,}",                                             "substantive content", False),
        ("signature_block",      r"(?i)sincerely|respectfully|very truly|signed|sgd",            "sender signature", False),
        ("demand_specifics",     r"(?i)demand|hereby demand|within\s+\d+\s+days|comply",         "ONLY for demand letters — specifies demand + compliance period", False),
        ("proof_of_service",     r"(?i)registered mail|received|stamped|tracking|courier|delivery", "if material as evidence", True),
    ],
    "GOVERNMENT_SUBMISSION": [
        ("submission_cover",     r"(?i)submitted|transmit|herewith|enclosed|forward",            "what is being submitted", False),
        ("receiving_stamp",      r"(?i)received|stamped|date\s+received|receiving\s+section",   "agency acknowledgment", False),
        ("reference_number",     r"(?i)CTN SL|case no|docket|reference|ref\.?",                  "agency-assigned ref", False),
        ("addressed_to_agency",  r"(?i)ARTA|DILG|registry of deeds|BIR|civil service|land registration|department of|bureau of|office of", "agency identification", False),
        ("signed_by_submitter",  r"(?i)signed|sgd|complainant|petitioner|jonathan|atty\.",       "submitter signs", False),
    ],
    "CONTRACT": [
        ("parties_identified",   r"(?i)between|by and between|first party|second party|of legal age", "Civil Code Art 1318 capacity", False),
        ("object",               r"(?i)subject of this|object of|in consideration of|to perform", "Art 1318 object", False),
        ("consideration",        r"(?i)consideration|in exchange for|peso|₱|PHP",               "Art 1318 cause", False),
        ("signatures",           r"(?i)signature|signed|sgd",                                    "Art 1356", False),
        ("notarization",         r"(?i)before me|notary public",                                 "Art 1358 — required for some", False),
        ("date",                 r"(?i)\b\d{4}-\d{2}-\d{2}|\b\d{1,2}\s+\w+\s+\d{4}",            "effectivity", False),
    ],
    "PLAN_SURVEY": [
        ("plan_number",          r"(?i)psd-?\s*\d|psu-?\s*\d|pcs-?\s*\d|pls-?\s*\d|sgs-?\s*\d|bsd-?\s*\d", "Survey plan ID", False),
        ("geodetic_engineer",    r"(?i)geodetic engineer|GE\.|licensed surveyor|geo\.\s+engr",    "responsible surveyor", False),
        ("date_of_survey",       r"(?i)surveyed on|date of survey|approved on|approved by",     "currency", False),
        ("reference_title",      r"(?i)TCT|tct\s+no|title no|OCT",                              "which property", False),
        ("approval_authority",   r"(?i)approved\s+by|LRA|land registration authority|DENR-LMB",  "official approval", False),
    ],
}


def detect_act_type(doc):
    """Map doc.classification + filename to one of the rubric keys."""
    cls = (doc.get("classification") or "").lower()
    fn = (doc.get("smart_filename") or "").lower()
    blob = cls + " " + fn
    # Most specific first
    if "donation" in blob: return "DONATION"
    if re.search(r"revocation|cancel.{0,15}spa|cancel.{0,15}power", blob): return "REVOCATION_OF_SPA"
    if "deed" in cls and ("sale" in blob or "absolute" in blob): return "DEED_OF_SALE"
    if "deed" in cls: return "DEED_OF_SALE"
    if re.search(r"judicial\s+affidavit|jud\.?\s*aff", blob): return "JUDICIAL_AFFIDAVIT"
    if "affidavit" in cls or "affidavit" in fn: return "AFFIDAVIT"
    if "spa" in blob or "special power" in blob or "power of attorney" in blob: return "SPA"
    if "court filing" in cls or "complaint" in cls or "answer" in cls or "motion" in cls \
       or "reply" in cls or "memorandum" in cls: return "PLEADING"
    if "order" in cls or "decision" in cls or "resolution" in blob and ("court" in blob or "RTC" in blob.upper()):
        return "COURT_ORDER"
    if "notice" in cls: return "NOTICE"
    if "resolution" in cls and ("sangguniang" in blob or "municipal" in blob or "barangay" in blob):
        return "RESOLUTION_LGU"
    if "title" in cls: return "TITLE"
    if "tax document" in cls or "tax dec" in blob: return "TAX_DOCUMENT"
    if "receipt" in cls or " or " in blob or "official receipt" in blob: return "RECEIPT"
    if "letter" in cls or "demand letter" in cls or "correspondence" in cls: return "LETTER"
    if "government submission" in cls: return "GOVERNMENT_SUBMISSION"
    if "contract" in cls: return "CONTRACT"
    if "plan" in cls or "survey" in cls or "psd" in fn or "psu" in fn: return "PLAN_SURVEY"
    return None


def is_draft(doc):
    """Per Jonathan 2026-05-16: a draft cannot be considered a filed case.

    Returns (is_draft: bool, reason: str). Checks filename for [DRAFT] marker,
    execution_status='draft_unsigned', AND content-level draft indicators.
    """
    fn = (doc.get("smart_filename") or "") + " " + (doc.get("original_filename") or "")
    if re.search(r"\[DRAFT\]|\bDRAFT\b", fn, re.IGNORECASE):
        return True, f"filename contains [DRAFT] marker: {fn[:60]}"
    if (doc.get("execution_status") or "").lower() == "draft_unsigned":
        return True, "execution_status is draft_unsigned"
    text = (doc.get("extracted_text") or "")[:500]
    if re.search(r"^\s*DRAFT\s|^\s*\[\s*DRAFT\s*\]", text, re.IGNORECASE):
        return True, "text starts with DRAFT marker"
    return False, None


def cross_doc_corroboration(cur, doc):
    """For acts that require multi-document corroboration (Deed of Sale → title transfer):
       check title_chain, instruments_on_title, and transactions for the supporting
       evidence Jonathan requires: 'a deed of sale needs to be recorded on a corresponding
       title and lot'.

    Returns dict with corroboration_present / missing flags.
    """
    out = {"checks_run": [], "corroboration": {}}
    text = (doc.get("extracted_text") or "")
    fn = (doc.get("smart_filename") or "").lower()
    cls = (doc.get("classification") or "").lower()
    # Only run for deed-type docs claiming title transfer
    if not ("deed" in cls or "sale" in fn or "donation" in fn):
        return out

    # Find any TCT/OCT mentioned in this doc
    tct_matches = re.findall(r"\b(?:T(?:CT)?[-\s]*(\d{2,7}|\d{3}-\d{4,12}))", text, re.IGNORECASE)
    titles_in_doc = list({f"T-{t}" for t in tct_matches[:20]})

    out["titles_referenced_in_deed"] = titles_in_doc[:10]

    # For each title referenced, check title_chain + instruments_on_title
    for t in titles_in_doc[:5]:
        out["checks_run"].append(f"Title {t}: looking for annotation + chain")

        # Is this deed annotated on the title (via instruments_on_title)?
        cur.execute("""
            SELECT COUNT(*) AS n FROM instruments_on_title
             WHERE parent_tct_number = %s AND doc_id = %s
        """, (t, doc["id"]))
        annotated = cur.fetchone()["n"] > 0
        out["corroboration"][f"{t}_annotated_with_this_deed"] = annotated

        # Was a new title issued FROM this title (in title_chain)?
        cur.execute("""
            SELECT COUNT(*) AS n FROM title_chain
             WHERE parent_title = %s AND source_doc_id = %s
        """, (t, doc["id"]))
        spawned_new = cur.fetchone()["n"] > 0
        out["corroboration"][f"{t}_spawned_new_title_from_this_deed"] = spawned_new

    # Was BIR CAR / transfer tax paid? Look for transactions referencing this doc
    cur.execute("""
        SELECT COUNT(*) AS n FROM transactions
         WHERE source_doc_id = %s AND category IN ('cnr','cgt','dst','transfer_tax','registration_fee')
    """, (doc["id"],))
    out["corroboration"]["bir_or_tax_transactions_referencing_this_deed"] = cur.fetchone()["n"]

    return out


def audit_doc(doc, cur=None):
    """Return validity report dict for a single doc."""
    # 1. DRAFT GUARD — per Jonathan's directive, never citable as filed
    draft, draft_reason = is_draft(doc)

    act_type = detect_act_type(doc)
    if not act_type:
        return {"doc_id": doc["id"], "act_type": None,
                "is_draft": draft, "draft_reason": draft_reason,
                "error": "No matching rubric — doc classification/filename does not look like a recognized doc type"}

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

    # 2. CROSS-DOCUMENT CORROBORATION for deeds claiming title transfer
    cross = cross_doc_corroboration(cur, doc) if cur else {"checks_run": [], "corroboration": {}}

    # Validity verdict — most stringent gate first
    if draft:
        verdict = "DRAFT_NOT_CITABLE_AS_FILED"
    elif n_present_internal < max(1, n_internal // 2):
        verdict = "ASSERTED_BUT_INCOMPLETE_majority_components_missing"
    elif act_type in ("DEED_OF_SALE","DONATION") and cross.get("corroboration"):
        # For title transfers, internal alone isn't enough — must have corroboration
        any_corroborated = any(v for k, v in cross["corroboration"].items() if "annotated" in k or "spawned" in k or v)
        if not any_corroborated:
            verdict = "INTERNALLY_COMPLETE_NO_TITLE_CHAIN_CORROBORATION"
        elif n_present_internal >= n_internal - 1:
            verdict = "INTERNALLY_COMPLETE_PARTIAL_CHAIN_CORROBORATION"
        else:
            verdict = "PARTIAL_internal_and_chain"
    elif n_external_open > 0 and n_present_internal >= max(1, n_internal - 1):
        verdict = "INTERNAL_COMPLETE_external_evidence_still_required"
    elif n_present_internal == n_internal:
        verdict = "INTERNALLY_VERIFIED"
    else:
        verdict = "PARTIALLY_PRESENT_internal_components"

    return {
        "doc_id": doc["id"],
        "act_type": act_type,
        "is_draft": draft,
        "draft_reason": draft_reason,
        "components": components,
        "internal_components_present": f"{n_present_internal}/{n_internal}",
        "external_components_needed": n_external_open,
        "cross_document_corroboration": cross,
        "validity_summary": verdict,
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
            # Use parameterized ILIKE patterns to avoid % vs %s confusion in psycopg2.
            patterns = ('%deed%','%donation%','%power of attorney%','%spa%',
                        '%deed%','%donation%','%spa%','%revocation%','%affidavit%','%complaint%',
                        '%order%','%notice%','%title%','%tax%','%receipt%')
            case_filter = "AND case_file = %s" if args.case else ""
            params = patterns + ((args.case,) if args.case else ())
            cur.execute(f"""
                SELECT id, smart_filename, classification, execution_status, extracted_text
                  FROM documents
                 WHERE execution_status IN ('executed_filed','executed_notarized','government_issued')
                   AND (classification ILIKE %s OR classification ILIKE %s
                        OR classification ILIKE %s OR classification ILIKE %s
                        OR smart_filename ILIKE %s OR smart_filename ILIKE %s
                        OR smart_filename ILIKE %s OR smart_filename ILIKE %s
                        OR classification ILIKE %s OR classification ILIKE %s
                        OR classification ILIKE %s OR classification ILIKE %s
                        OR classification ILIKE %s OR classification ILIKE %s
                        OR classification ILIKE %s)
                   {case_filter}
                   AND NOT EXISTS (
                     SELECT 1 FROM extraction_chunks ec
                      WHERE ec.doc_id = documents.id AND ec.chunk_type='validity_audit'
                   )
                 LIMIT 200
            """, params)
            docs = cur.fetchall()
        else:
            sys.exit("Usage: --doc N | --all-unaudited [--case MWK-001]")

        results = []
        for d in docs:
            audit = audit_doc(d, cur=cur)
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
