#!/usr/bin/env python3
"""execution_classify.py — Stage 0 of the no-hallucination pipeline. Classify each document's
EXECUTION STATUS so the evidence layer admits executed/received copies only and quarantines drafts.

Revived + extended from archive/dead_code_2026-06-06/classify_execution_status.py (which was archived,
leaving 434 docs unclassified). Additions: (1) RECEIVED-STAMP recognition for plain correspondence —
the office's "RECEIVED BY / DATE / TIME" stamp (incl. OCR variants like 'REGEIVED') — which the old
classifier missed because a receipt stamp only counted toward executed_filed (which needs a court
header); (2) --matter scoping via document_matter_links.

Taxonomy & evidence gate:
  EVIDENCE-GRADE : executed_notarized · executed_filed · government_issued · received_stamped ·
                   executed_signed_only · email_received
  NOT EVIDENCE   : draft_unsigned · email_sent (proves sending, not receipt) · template · unknown · null

Runs ON THE VPS (psycopg2 → internal DSN). Populates documents.execution_status + execution_metadata.
  python3 execution_classify.py --matter 'MWK-ARTA%' --dry-run
  python3 execution_classify.py --matter 'MWK-ARTA%'            # writes
  python3 execution_classify.py --matter 'MWK-OP-PETITION'
"""
import argparse
import json
import re
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

DOC_NO_BLOCK_EX = re.compile(
    r"doc(?:ument)?\.?\s*no\.?\s*[:#]?\s*([\dA-Z\-]+).{0,100}"
    r"book\s*no\.?\s*[:#]?\s*([\dA-Z\-IVXLCM]+).{0,100}"
    r"page\s*no\.?\s*[:#]?\s*([\d\-]+).{0,100}"
    r"(?:series\s*of|s\.)\s*(\d{4})", re.IGNORECASE | re.DOTALL)
NOTARY_ACK_RX = re.compile(
    r"(subscribed\s+and\s+sworn|acknowledged\s+before\s+me|notary\s+public|"
    r"my\s+commission\s+expires|PTR\s*No|IBP\s*No|MCLE\s*Compliance)", re.IGNORECASE)
FILING_STAMP_RX = re.compile(
    r"(filed[:\s]+\d{1,2}[\-/\s][a-zA-Z\d]+[\-/\s]\d{2,4}|date\s+filed[:\s]+|"
    r"docket\s+no\.?\s*[:#]?\s*[\dA-Z\-]+|civil\s+case\s+no\.?\s*[:#]?\s*[\dA-Z\-]+)", re.IGNORECASE)
COURT_HEADER_RX = re.compile(
    r"(REGIONAL\s+TRIAL\s+COURT|MUNICIPAL\s+TRIAL\s+COURT|COURT\s+OF\s+APPEALS|"
    r"SUPREME\s+COURT|OFFICE\s+OF\s+THE\s+OMBUDSMAN|ANTI-?RED\s+TAPE\s+AUTHORITY)", re.IGNORECASE | re.DOTALL)
# NEW — a receiving office's stamp on correspondence (delivery proof). OCR-tolerant: REGEIVED, RECElVED.
RECEIVED_STAMP_RX = re.compile(
    r"(r[eg]c[eil1]+ved\s+by|received\s+by\s*[:.\n]|received\s*[:.]\s*\d|"
    r"date\s+received|time\s+received|stamped\s+received|received\s+the\s+foregoing)", re.IGNORECASE)
GOV_ISSUER_RX = re.compile(
    r"(REGISTER\s+OF\s+DEEDS|REGISTRY\s+OF\s+DEEDS|BUREAU\s+OF\s+INTERNAL\s+REVENUE|\bBIR\b|"
    r"LAND\s+REGISTRATION\s+AUTHORITY|\bLRA\b|ASSESSOR'?S?\s+OFFICE|TREASURER'?S?\s+OFFICE|"
    r"DEPARTMENT\s+OF\s+AGRARIAN\s+REFORM|\bDAR\b|ANTI-?RED\s+TAPE\s+AUTHORITY|\bARTA\b|"
    r"TRANSFER\s+CERTIFICATE\s+OF\s+TITLE|ORIGINAL\s+CERTIFICATE\s+OF\s+TITLE|OFFICIAL\s+RECEIPT)", re.IGNORECASE)
EMAIL_HEADER_RX = re.compile(
    r"(from:\s*\S+@\S+|sent:\s*[a-z]+,?\s+[a-z]+\s+\d+|date:\s*[a-z]+,?\s+\d+\s+[a-z]+|"
    r"subject:|to:\s*\S+@\S+)", re.IGNORECASE)
DRAFT_RX = re.compile(
    r"(\bDRAFT\b|for\s+review|for\s+approval|\[DRAFT\]|preliminary\s+version|"
    r"not\s+for\s+filing|do\s+not\s+file|for\s+signature|unsigned)", re.IGNORECASE)
SIGNATURE_RX = re.compile(r"(\(SGD\)|\(signed\)|/s/|/sgd/|signed:\s*[a-z])", re.IGNORECASE)
NOTARY_NAME_EX = re.compile(
    r"(?:notary\s+public.{0,200}?(?:atty\.?\s*|attorney\s+)([A-Z][a-zA-Z'\.\-]+(?:\s+[A-Z][a-zA-Z'\.\-]+){1,3}))",
    re.IGNORECASE)


def classify_text(text, classification_hint=None, mime_type=None, smart_filename=None):
    if not text or len(text) < 50:
        return ("unknown", {"reason": "too_short_or_empty"}, 0.0)
    t = text[:50_000]
    head, tail = t[:4000], t[-3000:]
    meta = {}

    em = EMAIL_HEADER_RX.findall(t[:3000])
    if len(em) >= 2 or (mime_type and "email" in (mime_type or "").lower()) or \
       (classification_hint and classification_hint.lower() == "email"):
        is_outbound = bool(re.search(r"from:\s*\S+@(landtek|hayuma|jonzschoche|gmail)", t, re.IGNORECASE))
        status = "email_sent" if is_outbound else "email_received"
        meta["email_headers_found"] = len(em)
        for k, rx in (("from", r"from:\s*([^\n\r]{1,200})"), ("to", r"to:\s*([^\n\r]{1,200})"),
                      ("subject", r"subject:\s*([^\n\r]{1,300})"), ("sent_at", r"(?:sent|date):\s*([^\n\r]{1,100})")):
            m = re.search(rx, t, re.IGNORECASE)
            if m:
                meta[k] = m.group(1).strip()
        return (status, meta, 0.90)

    # ── complainant-authored outbound correspondence is NOT a gov/notarized instrument ──
    # (a letter ADDRESSED TO the Assessor/ARTA mentions those offices but is not issued by them)
    is_letter = bool(re.search(r"\bTo:\s", head)) and bool(
        re.search(r"representative for|jonzschoche@|jonathan\s+zschoche|patricia\s+keesey", head, re.IGNORECASE))
    if is_letter and not DOC_NO_BLOCK_EX.search(t):
        if RECEIVED_STAMP_RX.search(head) or RECEIVED_STAMP_RX.search(tail):
            return ("received_stamped", {"received_stamp": True, "letter": True}, 0.85)
        if DRAFT_RX.search(t):
            return ("draft_unsigned", {"letter": True}, 0.80)
        # receipt not provable from text alone — leave to version-pairing, do NOT guess evidence-grade
        return ("unknown", {"letter": True, "note": "complainant correspondence; receipt unprovable from text — resolve via version-pairing"}, 0.40)

    is_draft = bool(DRAFT_RX.search(t)) or (smart_filename and "draft" in smart_filename.lower())
    has_notarial_block = bool(DOC_NO_BLOCK_EX.search(t))
    has_filing = bool(FILING_STAMP_RX.search(t)) and bool(COURT_HEADER_RX.search(t))
    has_received = bool(RECEIVED_STAMP_RX.search(head)) or bool(RECEIVED_STAMP_RX.search(tail))

    # draft only if nothing proves execution/receipt
    if is_draft and not has_notarial_block and not has_filing and not has_received:
        meta["draft_indicators"] = "DRAFT marker present, no execution/receipt stamp"
        return ("draft_unsigned", meta, 0.85)

    if has_notarial_block:
        m = DOC_NO_BLOCK_EX.search(t)
        meta["notarial_block"] = {"doc_no": m.group(1), "book_no": m.group(2), "page_no": m.group(3), "series": m.group(4)}
        nn = NOTARY_NAME_EX.search(t)
        if nn:
            meta["notary"] = nn.group(1).strip()
        return ("executed_notarized", meta, 0.95)

    if has_filing:
        dk = re.search(r"(?:docket\s+no\.?|civil\s+case\s+no\.?)\s*[:#]?\s*([\dA-Z\-]+)", t, re.IGNORECASE)
        if dk:
            meta["docket_no"] = dk.group(1)
        return ("executed_filed", meta, 0.90)

    # ── tribunal ORDER / RESOLUTION issued by ARTA or a court (government_issued, not the complainant's) ──
    is_order = re.search(r"\bOSCA\b|order\s+for\s+(the\s+)?submission|it\s+is\s+hereby\s+(ordered|resolved)|"
                         r"\bso\s+ordered\b|wherefore.{0,80}(ordered|resolved)|notice\s+of\s+(extension|hearing)|"
                         r"\bindorsement\b", t, re.IGNORECASE)
    if is_order and not is_letter and (
            COURT_HEADER_RX.search(head[:1800]) or re.search(r"anti-?red\s+tape|office\s+of\s+the\s+(president|ombudsman)", head[:1800], re.IGNORECASE)):
        return ("government_issued", {"tribunal_order": True}, 0.85)

    # NEW — received-stamped correspondence (the delivery-proof copy; evidence-grade)
    if has_received:
        meta["received_stamp"] = True
        return ("received_stamped", meta, 0.85)

    # government-ISSUED requires genuine issuance markers, not a mere office mention (which appears in
    # any letter addressed to that office). The old 'len(gov_hits) >= 2' path promoted correspondence.
    gov_hits = GOV_ISSUER_RX.findall(t[:5000])
    if gov_hits and (
        re.search(r"certified\s+true\s+copy|original\s+copy|issued\s+by|this\s+is\s+to\s+certify|"
                  r"O\.?\s?R\.?\s*No\.?\s*\d|\bT-\d{3,}\b|TCT\s*No|OCT\s*No", t[:6000], re.IGNORECASE)
        or (classification_hint and classification_hint.lower() in
            ("title (tct/oct)", "title", "title (tct)", "tax document", "government submission"))):
        meta["gov_issuer_hits"] = list(set(h.lower() for h in gov_hits))[:5]
        return ("government_issued", meta, 0.80)

    if SIGNATURE_RX.search(t) and NOTARY_ACK_RX.search(t):
        return ("executed_notarized", {"partial": True, "ack_only": True}, 0.65)
    if SIGNATURE_RX.search(t):
        return ("executed_signed_only", {}, 0.65)
    return ("unknown", {}, 0.30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--matter", default=None, help="scope to a matter_code family (ILIKE) via document_matter_links")
    ap.add_argument("--reclassify", action="store_true", help="re-run on already-classified docs too")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where = ["extracted_text IS NOT NULL", "length(extracted_text) >= 100"]
    params = []
    if not args.reclassify:
        where.append("execution_status IS NULL")
    if args.matter:
        where.append("id IN (SELECT doc_id FROM document_matter_links WHERE matter_code ILIKE %s)")
        params.append(args.matter)
    sql = (f"SELECT id, classification, mime_type, smart_filename, LEFT(extracted_text,50000) AS extracted_text "
           f"FROM documents WHERE {' AND '.join(where)} ORDER BY id" + (" LIMIT %s" if args.limit else ""))
    if args.limit:
        params.append(args.limit)
    cur.execute(sql, params)
    docs = cur.fetchall()
    print(f"  scanning {len(docs)} documents (matter={args.matter}, reclassify={args.reclassify})")

    by_status, conf_hi = {}, 0
    for d in docs:
        status, meta, conf = classify_text(d["extracted_text"], d.get("classification"), d.get("mime_type"), d.get("smart_filename"))
        by_status[status] = by_status.get(status, 0) + 1
        conf_hi += conf >= 0.75
        if not args.dry_run:
            cur.execute("UPDATE documents SET execution_status=%s, execution_metadata=%s::jsonb, updated_at=now() WHERE id=%s",
                        (status, json.dumps({**meta, "confidence": conf, "method": "regex_classifier_v2"}), d["id"]))
    print("  ── classification summary ──")
    for s, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"    {s:22s} {n:>4}")
    print(f"  high-confidence (>=0.75): {conf_hi} / {len(docs)}" + ("   (DRY RUN — no writes)" if args.dry_run else ""))
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
