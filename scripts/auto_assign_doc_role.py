#!/usr/bin/env python3
"""auto_assign_doc_role.py — heuristic doc_role assignment for 977 docs.

Scans `documents.original_filename` + `summary` and applies filename
heuristics to assign doc_role. Conservative: low-confidence matches go to
'not_yet_assessed' so Jonathan can review without false categorization.

Idempotent: only updates docs where doc_role IS NULL OR doc_role='not_yet_assessed'.

Heuristics (case-insensitive on filename):
  pattern                                          → doc_role
  TCT|T-NNNN|certificate of title|title           → title_instrument
  tax dec|TD-|tax declaration                     → tax_declaration
  deed of sale|deed of donation|deed of           → transfer_instrument
  SPA|special power of attorney                   → transfer_instrument
  letter|email|reply|response|correspondence      → correspondence
  order|resolution|decision|writ                  → order_resolution
  motion|manifestation|petition|complaint|brief
   |answer|comment|memorandum|opposition          → pleading
  birth cert|marriage cert|death cert|baptismal   → prime_evidence
  CARP|DAR|landbank                               → background
  affidavit                                       → prime_evidence
  receipt|invoice|or-                             → background

Runs once. Reports counts. No restart needed (data-only change).
"""
from __future__ import annotations
import os, re
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

RULES = [
    # (compiled regex, doc_role)
    (re.compile(r"\b(tct[\s\-_]*t?[\s\-]*\d|t[\s\-]?\d{4,6}|certificate of title)\b", re.I),
     "title_instrument"),
    (re.compile(r"\b(tax\s*dec(laration)?|td[\s\-]?\d|tax[\s_-]+declar)\b", re.I),
     "tax_declaration"),
    (re.compile(r"\b(deed\s+of\s+(sale|donation|absolute|conditional|partition|assignment)|conveyance)\b", re.I),
     "transfer_instrument"),
    (re.compile(r"\b(special\s+power\s+of\s+attorney|\bSPA\b)\b", re.I),
     "transfer_instrument"),
    (re.compile(r"\b(birth\s+(certificate|cert)|marriage\s+(certificate|cert)|death\s+(certificate|cert)|baptismal)\b", re.I),
     "prime_evidence"),
    (re.compile(r"\b(affidavit|sworn\s+statement|joint\s+affidavit)\b", re.I),
     "prime_evidence"),
    (re.compile(r"\b(letter|email|reply|response|correspondence|memo[\s_-]*to)\b", re.I),
     "correspondence"),
    (re.compile(r"\b(order|resolution|decision|writ|ruling|judgment)\b", re.I),
     "order_resolution"),
    (re.compile(r"\b(motion|manifestation|petition|complaint|brief|answer|comment|memorandum|opposition|reply\s+to|rejoinder)\b", re.I),
     "pleading"),
    (re.compile(r"\b(CARP|DAR\b|landbank|land\s+bank|EP[\s\-]?\d|CLOA)\b", re.I),
     "background"),
    (re.compile(r"\b(receipt|invoice|or[\s\-]?\d{3,}|payment)\b", re.I),
     "background"),
]


def classify(filename: str) -> str | None:
    for pattern, role in RULES:
        if pattern.search(filename or ""):
            return role
    return None


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, original_filename, COALESCE(summary, '') AS summary, doc_role, lt_number
          FROM documents
         WHERE doc_role IS NULL OR doc_role = 'not_yet_assessed'
    """)
    rows = cur.fetchall()
    counts = {}
    updates = []
    for r in rows:
        haystack = (r["original_filename"] or "") + " " + r["summary"][:300]
        role = classify(haystack)
        if not role:
            role = "not_yet_assessed"
        if role != r["doc_role"]:
            updates.append((role, r["id"]))
            counts[role] = counts.get(role, 0) + 1

    if updates:
        cur.executemany("UPDATE documents SET doc_role = %s WHERE id = %s", updates)

    print(f"Scanned: {len(rows)} docs")
    print(f"Updates applied: {len(updates)}")
    print("\nFinal role distribution (all docs):")
    cur.execute("SELECT doc_role, COUNT(*) AS n FROM documents WHERE lt_number IS NOT NULL GROUP BY doc_role ORDER BY n DESC NULLS LAST")
    for r in cur.fetchall():
        print(f"  {(r['doc_role'] or 'NULL'):25s}  {r['n']}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
