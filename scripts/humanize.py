#!/usr/bin/env python3
"""humanize.py — strip machine artifacts from human-facing legal output. $0.

A lawyer should read only words that matter to them. This converts the system's internal tokens into
clean references at render time:
  • doc:708                  -> the document's TITLE ("Complaint with Manifestation")
  • [VERIFIED · doc:701]     -> "(source: <title>)"
  • [F5405] / SUPPORTED [F#] -> the fact-id is dropped (the statement stands)
  • MWK-ARTA-1891 etc.       -> the human docket / matter name
  • "N shared docs"          -> "N related documents"
Used by case_memo / case_dossier_pdf so nothing internal leaks onto the page.
"""
import os
import re

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _clean(fn):
    t = re.sub(r"\.(pdf|docx?|jpe?g|png|zip|txt)$", "", fn or "", flags=re.I)
    t = re.sub(r"\s*\(\d+\)\s*$", "", t)          # trailing "(1)"
    t = re.sub(r"\s{2,}", " ", t).strip(" -_")
    return t or "document"


def doc_titles(cur, mc):
    cur.execute("""SELECT id, coalesce(original_filename,smart_filename,'') FROM documents
                   WHERE matter_code=%s OR id IN (SELECT doc_id FROM document_matter_links WHERE matter_code=%s)""",
                (mc, mc))
    return {i: _clean(fn) for i, fn in cur.fetchall()}


def matter_names(cur):
    cur.execute("SELECT matter_code, coalesce(nullif(docket_number,''), title, matter_code) FROM matters")
    return {code: lbl for code, lbl in cur.fetchall()}


def humanize(text, dtitles=None, mnames=None):
    """Replace internal tokens with human references. Safe on None/empty."""
    if not text:
        return text
    dtitles = dtitles or {}
    mnames = mnames or {}

    def _doc(m):
        return dtitles.get(int(m.group(1)), "the document")

    # provenance tag -> clean source citation
    text = re.sub(r"\[\s*VERIFIED[^\]\n]*?doc:\s*(\d+)\s*\]", lambda m: f"(source: {_doc(m)})", text, flags=re.I)
    # bare doc:N -> title
    text = re.sub(r"\bdocs?\.?\s*:?\s*(\d+)\b", _doc, text, flags=re.I)
    # fact-ids -> drop
    text = re.sub(r"\[\s*F\s*\d+(?:\s*,\s*F?\s*\d+)*\s*\]", "", text)
    text = re.sub(r"\bF\d{3,}\b", "", text)
    # matter codes -> human docket/name
    text = re.sub(r"\bMWK-[A-Z0-9-]+\b", lambda m: mnames.get(m.group(0), "this matter"), text)
    text = re.sub(r"\bPAR-[A-Z0-9-]+\b", lambda m: mnames.get(m.group(0), "the related matter"), text)
    # tidy machine phrasing
    text = text.replace("shared docs", "related documents").replace("source_id", "source")
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()
