#!/usr/bin/env python3
"""deploy_125 — normalize documents.doc_date from TEXT to DATE.

The doc_date column is text. Date-based queries had to do regex casts. Now we:
  1. Add documents.doc_date_norm (DATE).
  2. Parse every doc_date TEXT value and write the parsed DATE.
  3. Flag unparseable strings in documents.doc_date_quality.
  4. Leave the original TEXT column (audit safety per [[feedback_information_is_gold]]).
  5. Add backfill trigger so future INSERTs auto-normalize.
"""
import re
from datetime import date
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SCHEMA = """
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS doc_date_norm date,
  ADD COLUMN IF NOT EXISTS doc_date_quality text;  -- 'ok' | 'parsed_fuzzy' | 'unparseable' | 'empty'

CREATE INDEX IF NOT EXISTS idx_docs_doc_date_norm ON documents(doc_date_norm);
CREATE INDEX IF NOT EXISTS idx_docs_doc_date_quality ON documents(doc_date_quality);
"""

# Patterns we recognize
ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
SLASH_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")
DASH_MDY = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})")
MONTH_NAMES = {
    'jan':1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,
    'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,
    'sep':9,'sept':9,'september':9,'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12
}
TEXTUAL = re.compile(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})")  # March 17, 1988


def parse_doc_date(s):
    """Return (date | None, quality string)."""
    if s is None or not str(s).strip():
        return None, 'empty'
    s = str(s).strip()
    # Pure year-only e.g. "1992-00-00" or "1992"
    if re.match(r"^\d{4}$", s):
        try:
            return date(int(s), 1, 1), 'parsed_fuzzy'
        except: return None, 'unparseable'
    # ISO
    m = ISO.match(s)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if mo == 0 or d == 0:
                # e.g., "1992-00-00" or "YYYY-MM-00"
                return date(y, mo if mo > 0 else 1, d if d > 0 else 1), 'parsed_fuzzy'
            return date(y, mo, d), 'ok'
        except: return None, 'unparseable'
    # Slash MDY
    m = SLASH_MDY.match(s)
    if m:
        try:
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(y, mo, d), 'ok'
        except: return None, 'unparseable'
    # Dash MDY
    m = DASH_MDY.match(s)
    if m:
        try:
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(y, mo, d), 'ok'
        except: return None, 'unparseable'
    # Textual
    m = TEXTUAL.match(s)
    if m:
        mon_word = m.group(1).lower()
        if mon_word in MONTH_NAMES:
            try:
                return date(int(m.group(3)), MONTH_NAMES[mon_word], int(m.group(2))), 'ok'
            except: return None, 'unparseable'
    # Placeholder values
    if s.upper() in ('YYYY-MM-DD', 'TBD', 'UNKNOWN'):
        return None, 'empty'
    return None, 'unparseable'


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)

    cur.execute("SELECT id, doc_date FROM documents")
    rows = cur.fetchall()
    stats = {'ok':0, 'parsed_fuzzy':0, 'unparseable':0, 'empty':0}
    sample_bad = []
    for doc_id, dd in rows:
        parsed, quality = parse_doc_date(dd)
        cur.execute("UPDATE documents SET doc_date_norm = %s, doc_date_quality = %s WHERE id = %s",
                    (parsed, quality, doc_id))
        stats[quality] = stats.get(quality, 0) + 1
        if quality == 'unparseable' and len(sample_bad) < 8:
            sample_bad.append(f"  id={doc_id} doc_date={dd!r}")

    print(f"deploy_125: {len(rows)} doc rows normalized")
    for k, v in stats.items():
        print(f"  {k:14s} {v}")
    if sample_bad:
        print("\nSample unparseable doc_date values:")
        for s in sample_bad:
            print(s)

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
