#!/usr/bin/env python3
"""Deploy 119 — Party filing classifier schema."""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
CREATE TABLE IF NOT EXISTS case_party_filings (
  id              serial PRIMARY KEY,
  matter_code     text REFERENCES matters(matter_code),
  case_file       text,
  doc_id          integer REFERENCES documents(id) ON DELETE CASCADE,
  filing_party    text NOT NULL,    -- 'plaintiff','respondent','co_defendant','intervenor','court','witness','counsel','third_party'
  filing_role     text,             -- 'pleading','order','evidence','correspondence','notice','affidavit','motion','reply'
  filing_date     date,
  signature_party text,             -- who actually signed (e.g., "Atty. Barandon for plaintiff")
  next_response_due date,           -- when WE owe a response
  confidence      real DEFAULT 0.7,
  detection_method text,            -- 'regex','haiku','manual'
  notes           text,
  created_at      timestamptz DEFAULT now(),
  UNIQUE(doc_id, filing_party)
);
CREATE INDEX IF NOT EXISTS idx_cpf_matter ON case_party_filings(matter_code, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_cpf_party ON case_party_filings(filing_party, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_cpf_response_due ON case_party_filings(next_response_due) WHERE next_response_due IS NOT NULL;
"""

def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    print("  ✓ case_party_filings schema applied")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
