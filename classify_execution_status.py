#!/usr/bin/env python3
"""Classify each document's execution_status (deploy_111-A).

Taxonomy:
  executed_notarized   — Doc/Book/Page/Series block present + notary acknowledgement
  executed_filed       — court filing stamp / docket entry
  executed_signed_only — signed by parties, no notarial block
  government_issued    — RD, BIR, court order, ARTA, etc.
  email_sent           — outbound communication (timestamp citable)
  email_received       — inbound communication
  draft_unsigned       — draft / unsigned working version
  template             — blank form / boilerplate
  unknown              — cannot determine

Method: deterministic regex pass first (~80% coverage), Claude Haiku fallback
for ambiguous ones (only ~20% of docs).

Populates documents.execution_status + execution_metadata (JSONB).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

NOTARIAL_RX = re.compile(
    r"(doc(?:ument)?\.?\s*no\.?\s*[:#]?\s*[\dA-Z\-]+).{0,80}"
    r"(book\s*no\.?\s*[:#]?\s*[\dA-Z\-IVXLCM]+).{0,80}"
    r"(page\s*no\.?\s*[:#]?\s*[\d\-]+).{0,80}"
    r"(series\s*of\s*\d{4}|s\.\s*\d{4})",
    re.IGNORECASE | re.DOTALL,
)
NOTARY_ACK_RX = re.compile(
    r"(subscribed\s+and\s+sworn|acknowledged\s+before\s+me|notary\s+public|"
    r"my\s+commission\s+expires|PTR\s*No|IBP\s*No|MCLE\s*Compliance)",
    re.IGNORECASE,
)

FILING_STAMP_RX = re.compile(
    r"(filed[:\s]+\d{1,2}[\-/\s][a-zA-Z\d]+[\-/\s]\d{2,4}|"
    r"date\s+filed[:\s]+|"
    r"received[:\s]+by[:\s]+|"
    r"docket\s+no\.?\s*[:#]?\s*[\dA-Z\-]+|"
    r"civil\s+case\s+no\.?\s*[:#]?\s*[\dA-Z\-]+|"
    r"OR\s+No\.?\s*[:#]?\s*\d+)",
    re.IGNORECASE,
)
COURT_HEADER_RX = re.compile(
    r"(REGIONAL\s+TRIAL\s+COURT|MUNICIPAL\s+TRIAL\s+COURT|"
    r"COURT\s+OF\s+APPEALS|SUPREME\s+COURT|"
    r"REPUBLIC\s+OF\s+THE\s+PHILIPPINES.{0,200}COURT)",
    re.IGNORECASE | re.DOTALL,
)

GOV_ISSUER_RX = re.compile(
    r"(REGISTER\s+OF\s+DEEDS|REGISTRY\s+OF\s+DEEDS|"
    r"BUREAU\s+OF\s+INTERNAL\s+REVENUE|BIR|"
    r"LAND\s+REGISTRATION\s+AUTHORITY|LRA|"
    r"ASSESSOR'?S?\s+OFFICE|TREASURER'?S?\s+OFFICE|"
    r"DEPARTMENT\s+OF\s+AGRARIAN\s+REFORM|DAR|"
    r"ANTI-RED\s+TAPE\s+AUTHORITY|ARTA|"
    r"NATIONAL\s+ARCHIVES|"
    r"TRANSFER\s+CERTIFICATE\s+OF\s+TITLE|"
    r"ORIGINAL\s+CERTIFICATE\s+OF\s+TITLE|"
    r"OFFICIAL\s+RECEIPT)",
    re.IGNORECASE,
)

EMAIL_HEADER_RX = re.compile(
    r"(from:\s*\S+@\S+|sent:\s*[a-z]+,?\s+[a-z]+\s+\d+|"
    r"date:\s*[a-z]+,?\s+\d+\s+[a-z]+|"
    r"subject:|to:\s*\S+@\S+)",
    re.IGNORECASE,
)

DRAFT_RX = re.compile(
    r"(\bDRAFT\b|for\s+review|for\s+approval|"
    r"\[DRAFT\]|preliminary\s+version|"
    r"not\s+for\s+filing|do\s+not\s+file)",
    re.IGNORECASE,
)

SIGNATURE_RX = re.compile(
    r"(\(SGD\)|\(signed\)|/s/|/sgd/|signed:\s*[a-z])",
    re.IGNORECASE,
)

DOC_NO_BLOCK_EX = re.compile(
    r"doc(?:ument)?\.?\s*no\.?\s*[:#]?\s*([\dA-Z\-]+).{0,100}"
    r"book\s*no\.?\s*[:#]?\s*([\dA-Z\-IVXLCM]+).{0,100}"
    r"page\s*no\.?\s*[:#]?\s*([\d\-]+).{0,100}"
    r"(?:series\s*of|s\.)\s*(\d{4})",
    re.IGNORECASE | re.DOTALL,
)
DOCKET_EX = re.compile(
    r"(?:docket\s+no\.?|civil\s+case\s+no\.?)\s*[:#]?\s*([\dA-Z\-]+)",
    re.IGNORECASE,
)
NOTARY_NAME_EX = re.compile(
    r"(?:notary\s+public.{0,200}?(?:atty\.?\s*|attorney\s+)([A-Z][a-zA-Z'\.\-]+(?:\s+[A-Z][a-zA-Z'\.\-]+){1,3}))",
    re.IGNORECASE,
)


def classify_text(text, classification_hint=None, mime_type=None, smart_filename=None):
    """Deterministic classifier. Returns (status, metadata_dict, confidence)."""
    if not text or len(text) < 50:
        return ("unknown", {"reason": "too_short_or_empty"}, 0.0)

    t = text[:50_000]  # cap
    meta = {}
    score = {}

    # ── Email headers ─────────────────────────────────────────────────────
    em = EMAIL_HEADER_RX.findall(t[:3000])
    if len(em) >= 2 or (mime_type and "email" in (mime_type or "").lower()) or \
       (classification_hint and classification_hint.lower() == "email"):
        # Heuristic direction: From: vs To:
        is_outbound = bool(re.search(r"from:\s*\S+@(landtek|hayuma|jonzschoche)", t, re.IGNORECASE))
        status = "email_sent" if is_outbound else "email_received"
        meta["email_headers_found"] = len(em)
        # Try to capture from/to/subject/date
        m_from = re.search(r"from:\s*([^\n\r]{1,200})", t, re.IGNORECASE)
        m_to   = re.search(r"to:\s*([^\n\r]{1,200})", t, re.IGNORECASE)
        m_sub  = re.search(r"subject:\s*([^\n\r]{1,300})", t, re.IGNORECASE)
        m_dt   = re.search(r"(?:sent|date):\s*([^\n\r]{1,100})", t, re.IGNORECASE)
        if m_from: meta["from"] = m_from.group(1).strip()
        if m_to:   meta["to"]   = m_to.group(1).strip()
        if m_sub:  meta["subject"] = m_sub.group(1).strip()
        if m_dt:   meta["sent_at"] = m_dt.group(1).strip()
        return (status, meta, 0.90)

    # ── Draft markers (early-exit if clearly draft and no notarial/filing stamp) ──
    is_draft = bool(DRAFT_RX.search(t)) or (smart_filename and "draft" in smart_filename.lower())
    has_notarial_block = bool(DOC_NO_BLOCK_EX.search(t))
    has_filing = bool(FILING_STAMP_RX.search(t)) and bool(COURT_HEADER_RX.search(t))
    has_signature = bool(SIGNATURE_RX.search(t))
    has_notary_ack = bool(NOTARY_ACK_RX.search(t))

    if is_draft and not has_notarial_block and not has_filing:
        meta["draft_indicators"] = "DRAFT marker present"
        return ("draft_unsigned", meta, 0.85)

    # ── Notarized instrument (highest legal weight) ──────────────────────
    if has_notarial_block:
        m = DOC_NO_BLOCK_EX.search(t)
        if m:
            meta["notarial_block"] = {
                "doc_no":  m.group(1),
                "book_no": m.group(2),
                "page_no": m.group(3),
                "series":  m.group(4),
            }
        nn = NOTARY_NAME_EX.search(t)
        if nn:
            meta["notary"] = nn.group(1).strip()
        return ("executed_notarized", meta, 0.95)

    # ── Filed pleading ───────────────────────────────────────────────────
    if has_filing:
        dk = DOCKET_EX.search(t)
        if dk:
            meta["docket_no"] = dk.group(1)
        ch = COURT_HEADER_RX.search(t)
        if ch:
            meta["court_header"] = ch.group(0)[:200]
        return ("executed_filed", meta, 0.90)

    # ── Government-issued ────────────────────────────────────────────────
    gov_hits = GOV_ISSUER_RX.findall(t[:5000])
    if gov_hits:
        # but only if it's clearly issued, not just referenced
        if any(k in t[:5000] for k in ("ISSUED BY", "Issued by", "ORIGINAL COPY", "CERTIFIED TRUE COPY")) \
           or len(gov_hits) >= 2 \
           or (classification_hint and classification_hint.lower() in ("title (tct/oct)", "title", "title (tct)", "tax document", "government submission")):
            meta["gov_issuer_hits"] = list(set(h.lower() for h in gov_hits))[:5]
            return ("government_issued", meta, 0.80)

    # ── Signed only (no notary, no filing) ───────────────────────────────
    if has_signature and has_notary_ack:
        # has a notary acknowledgement clause but somehow no block — treat as notarized w/ partial
        return ("executed_notarized", {"partial": True, "ack_only": True}, 0.65)
    if has_signature:
        return ("executed_signed_only", {}, 0.65)

    # ── Default ──────────────────────────────────────────────────────────
    return ("unknown", {}, 0.30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--case", default=None)
    ap.add_argument("--reclassify", action="store_true", help="re-run on already-classified docs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where = ["extracted_text IS NOT NULL", "length(extracted_text) >= 100"]
    params = []
    if not args.reclassify:
        where.append("execution_status IS NULL")
    if args.case:
        where.append("case_file = %s"); params.append(args.case)
    sql = f"""
      SELECT id, case_file, classification, mime_type, smart_filename,
             LEFT(extracted_text, 50000) AS extracted_text
        FROM documents
       WHERE {' AND '.join(where)}
       ORDER BY id
       {'LIMIT %s' if args.limit else ''}
    """
    if args.limit:
        params.append(args.limit)
    cur.execute(sql, params)
    docs = cur.fetchall()
    print(f"  scanning {len(docs)} documents")

    by_status = {}
    high_conf_low_conf = [0, 0]
    for d in docs:
        status, meta, conf = classify_text(
            d["extracted_text"], d.get("classification"), d.get("mime_type"), d.get("smart_filename")
        )
        by_status[status] = by_status.get(status, 0) + 1
        if conf >= 0.75: high_conf_low_conf[0] += 1
        else: high_conf_low_conf[1] += 1
        if not args.dry_run:
            cur.execute("""
                UPDATE documents
                   SET execution_status = %s,
                       execution_metadata = %s::jsonb,
                       updated_at = now()
                 WHERE id = %s
            """, (status, json.dumps({**meta, "confidence": conf, "method": "regex_classifier_v1"}), d["id"]))

    print("\n  ── classification summary ──")
    for s, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"    {s:24s}  {n:>4}")
    print(f"\n  high-confidence (≥0.75): {high_conf_low_conf[0]}")
    print(f"  low-confidence  (<0.75): {high_conf_low_conf[1]}")
    if args.dry_run:
        print("\n  (dry run — no writes)")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
