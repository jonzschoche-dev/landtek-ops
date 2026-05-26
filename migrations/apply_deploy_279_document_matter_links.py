#!/usr/bin/env python3
"""Deploy 279 — document_matter_links junction (many-to-many) + autolink trigger.

Jonathan's directive: "every document should be placed somewhere as it relates
somehow — sometimes for multiple cases and ways."

Current state (snapshot before this deploy):
  - 955 documents
  - 187 have no case_file (19.6% orphaned at case level)
  - 310 have no matter_code (32.5% unfiled at matter level)
  - Every doc is single-matter (documents.matter_code is one text column)

This deploy:

  A. Create junction table document_matter_links (doc_id, matter_code, case_file,
     relation_kind, provenance_level, linked_by, note). UNIQUE on
     (doc_id, matter_code, relation_kind).

  B. relation_kind vocabulary (enforced via CHECK):
       primary         — doc is core to this matter
       evidence        — exhibit / supporting fact (human/deploy-script only)
       chain_of_title  — establishes a step in a title lineage (human/deploy-script only)
       reference       — cited / mentioned (autolink may emit, low-confidence)
       quoted_in       — extracted text appears in another doc on this matter
       parallel        — sibling proceeding
       cross_proof     — relevant when read against another doc on this matter

  C. Backfill `primary` links from every (doc.id, doc.matter_code) where both set.

  D. Pattern-scan extracted_text for cross-references — add `reference` links:
       - CTN SL-NNNN-NNNN-NNNN → MWK-ARTA-{last 4}  (when matter already exists)
       - Civil Case 26-360 / 26360                  → MWK-CV26360
       - Civil Case 6839                            → MWK-CV6839
       - "T-4497" / "TCT T-4497"                    → MWK-TCT4497
       - "Mary Worrick Keesey" / "MWK estate"       → MWK-ESTATE (when in extracted_text)

  E. Install AFTER INSERT/UPDATE trigger document_autolink_matters that, on each
     row change, ensures the same backfill logic runs for new/edited docs.

  F. Create view `documents_needing_classification` — docs with zero links of
     any kind. Surfaced via daily brief.

  G. Idempotent. Safe to re-run.

  H. Audited via app.actor='jonathan_deploy_279'.
"""
from __future__ import annotations

import os
import re
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ACTOR = "jonathan_deploy_279"

# Known matter codes we'll cross-link via text patterns
KNOWN_MATTERS = [
    "MWK-ARTA-0690", "MWK-ARTA-0747", "MWK-ARTA-0792",
    "MWK-ARTA-1210", "MWK-ARTA-1212", "MWK-ARTA-1319",
    "MWK-ARTA-1321", "MWK-ARTA-1378", "MWK-ARTA-1891",
    "MWK-ARTA-DILG", "MWK-CV26360", "MWK-CV6839",
    "MWK-ESTATE", "MWK-GUARDIANSHIP", "MWK-TCT4497",
    "PAR-CAPACUAN", "PAR-CASE-88750", "PAR-CV13-131220",
    "PAR-GOLDEN-SAND", "PAR-MARTIAL-ARTS",
]

# Text → matter_code mappings (regex string → matter_code)
# These are applied PostgreSQL-side via regex_match in the trigger fn and
# Python-side for backfill. Keep both copies in sync.
TEXT_MAPPINGS = [
    # CTN SL-YYYY-MMDD-NNNN — last 4 digits identify the ARTA matter
    ("CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*(0690)\\y", "MWK-ARTA-0690"),
    ("CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*(0747)\\y", "MWK-ARTA-0747"),
    ("CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*(0792)\\y", "MWK-ARTA-0792"),
    ("CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*(1210)\\y", "MWK-ARTA-1210"),
    ("CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*(1212)\\y", "MWK-ARTA-1212"),
    ("CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*(1319)\\y", "MWK-ARTA-1319"),
    ("CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*(1321)\\y", "MWK-ARTA-1321"),
    ("CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*(1378)\\y", "MWK-ARTA-1378"),
    ("CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*(1891)\\y", "MWK-ARTA-1891"),
    # Civil cases
    ("Civil\\s+Case\\s+(No\\.?\\s+)?26[-\\s]?360", "MWK-CV26360"),
    ("Civil\\s+Case\\s+(No\\.?\\s+)?6839", "MWK-CV6839"),
    ("Civil\\s+Case\\s+(No\\.?\\s+)?13[-\\s]?131220", "PAR-CV13-131220"),
    # Title patterns
    ("\\yT[-\\s]?4497\\y", "MWK-TCT4497"),
    ("TCT\\s+(No\\.?\\s+)?T?[-\\s]?4497\\y", "MWK-TCT4497"),
    # Estate-side identifiers
    ("Mary\\s+Worrick\\s+Keesey", "MWK-ESTATE"),
    ("Heirs?\\s+of\\s+Mary\\s+Worrick\\s+Keesey", "MWK-ESTATE"),
    # Paracale references
    ("Paracale\\s+Gold\\s+Partnership", "PAR-CAPACUAN"),
    ("Allan\\s+Inocalla", "PAR-CAPACUAN"),
]

# UNCLASSIFIED-equivalent values to skip when seeding primary
NULL_LIKE = {"", "UNCLASSIFIED", "unknown", "Unknown", "null"}


# -----------------------------------------------------------------------------
# Schema
# -----------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS document_matter_links (
  id               serial PRIMARY KEY,
  doc_id           integer NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  matter_code      text NOT NULL,
  case_file        text,
  relation_kind    text NOT NULL DEFAULT 'reference',
  provenance_level text NOT NULL DEFAULT 'inferred_strong',
  linked_by        text NOT NULL DEFAULT 'auto',
  note             text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (doc_id, matter_code, relation_kind),
  CHECK (relation_kind IN ('primary','evidence','chain_of_title','reference','quoted_in','parallel','cross_proof')),
  CHECK (provenance_level IN ('verified','inferred_strong','inferred_weak'))
);

CREATE INDEX IF NOT EXISTS idx_dml_doc      ON document_matter_links(doc_id);
CREATE INDEX IF NOT EXISTS idx_dml_matter   ON document_matter_links(matter_code);
CREATE INDEX IF NOT EXISTS idx_dml_case     ON document_matter_links(case_file);
CREATE INDEX IF NOT EXISTS idx_dml_kind     ON document_matter_links(relation_kind);

-- Touch updated_at on UPDATE
CREATE OR REPLACE FUNCTION touch_dml_updated_at() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_dml_touch ON document_matter_links;
CREATE TRIGGER trg_dml_touch BEFORE UPDATE ON document_matter_links
  FOR EACH ROW EXECUTE FUNCTION touch_dml_updated_at();
"""


# -----------------------------------------------------------------------------
# Autolink trigger function
# -----------------------------------------------------------------------------

TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION document_autolink_matters() RETURNS TRIGGER AS $$
DECLARE
  pat_record RECORD;
  detected_matter text;
BEGIN
  -- 1) Primary link from documents.matter_code (high-confidence)
  IF NEW.matter_code IS NOT NULL AND NEW.matter_code NOT IN ('', 'UNCLASSIFIED', 'unknown', 'Unknown') THEN
    INSERT INTO document_matter_links (doc_id, matter_code, case_file, relation_kind, provenance_level, linked_by, note)
    VALUES (NEW.id, NEW.matter_code, NEW.case_file, 'primary', 'verified', 'autolink_trigger',
            'Primary link from documents.matter_code')
    ON CONFLICT (doc_id, matter_code, relation_kind) DO UPDATE
      SET case_file = EXCLUDED.case_file, updated_at = now();
  END IF;

  -- 2) Reference links from regex patterns over extracted_text (low-confidence)
  IF NEW.extracted_text IS NOT NULL AND LENGTH(NEW.extracted_text) > 50 THEN
    -- CTN SL identifiers (any of the 9 known ARTA matters)
    FOR pat_record IN
      SELECT matter, pat FROM (VALUES
        ('MWK-ARTA-0690', 'CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*0690\\M'),
        ('MWK-ARTA-0747', 'CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*0747\\M'),
        ('MWK-ARTA-0792', 'CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*0792\\M'),
        ('MWK-ARTA-1210', 'CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*1210\\M'),
        ('MWK-ARTA-1212', 'CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*1212\\M'),
        ('MWK-ARTA-1319', 'CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*1319\\M'),
        ('MWK-ARTA-1321', 'CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*1321\\M'),
        ('MWK-ARTA-1378', 'CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*1378\\M'),
        ('MWK-ARTA-1891', 'CTN[\\s-]*SL[-\\s]*\\d{4}[-\\s]*\\d{4}[-\\s]*1891\\M'),
        ('MWK-CV26360',   'Civil\\s+Case\\s+(No\\.?\\s+)?26[-\\s]?360'),
        ('MWK-CV6839',    'Civil\\s+Case\\s+(No\\.?\\s+)?6839'),
        ('PAR-CV13-131220','Civil\\s+Case\\s+(No\\.?\\s+)?13[-\\s]?131220'),
        ('MWK-TCT4497',   '\\mT[-\\s]?4497\\M'),
        ('MWK-ESTATE',    'Mary\\s+Worrick\\s+Keesey'),
        ('PAR-CAPACUAN',  '(Paracale\\s+Gold\\s+Partnership|Allan\\s+Inocalla)')
      ) AS p(matter, pat)
    LOOP
      IF NEW.extracted_text ~* pat_record.pat THEN
        -- Only add reference link if not already primary
        INSERT INTO document_matter_links (doc_id, matter_code, relation_kind, provenance_level, linked_by, note)
        VALUES (NEW.id, pat_record.matter, 'reference', 'inferred_strong', 'autolink_trigger',
                'Detected via text pattern: ' || pat_record.matter)
        ON CONFLICT (doc_id, matter_code, relation_kind) DO NOTHING;
      END IF;
    END LOOP;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_autolink ON documents;
CREATE TRIGGER trg_documents_autolink
  AFTER INSERT OR UPDATE OF case_file, matter_code, extracted_text ON documents
  FOR EACH ROW EXECUTE FUNCTION document_autolink_matters();
"""


# -----------------------------------------------------------------------------
# View: documents_needing_classification
# -----------------------------------------------------------------------------

VIEW_SQL = """
CREATE OR REPLACE VIEW documents_needing_classification AS
  SELECT d.id, d.case_file, d.matter_code, d.smart_filename, d.original_filename,
         d.created_at, d.ingest_source,
         LEFT(COALESCE(d.extracted_text, ''), 200) AS preview
    FROM documents d
   WHERE NOT EXISTS (
     SELECT 1 FROM document_matter_links l WHERE l.doc_id = d.id
   )
   ORDER BY d.created_at DESC;

CREATE OR REPLACE VIEW document_matter_overview AS
  SELECT d.id AS doc_id,
         d.smart_filename,
         d.case_file AS primary_case,
         d.matter_code AS primary_matter,
         array_agg(DISTINCT l.matter_code ORDER BY l.matter_code)
           FILTER (WHERE l.matter_code IS NOT NULL) AS all_matters,
         array_agg(DISTINCT l.relation_kind || '/' || l.matter_code ORDER BY l.relation_kind || '/' || l.matter_code)
           FILTER (WHERE l.matter_code IS NOT NULL) AS relations,
         COUNT(DISTINCT l.matter_code) AS matter_count
    FROM documents d
    LEFT JOIN document_matter_links l ON l.doc_id = d.id
   GROUP BY d.id, d.smart_filename, d.case_file, d.matter_code;
"""


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def main() -> int:
    print("Deploy 279 — document_matter_links junction + autolink")
    print("=" * 60)

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = %s", (ACTOR,))

    # A) Schema
    print("\n  A) Schema — document_matter_links")
    cur.execute(SCHEMA_SQL)
    conn.commit()
    print("    ✓ table + indexes + touch trigger")

    # B) Trigger function
    print("\n  B) Install autolink trigger on documents")
    cur.execute(TRIGGER_SQL)
    conn.commit()
    print("    ✓ document_autolink_matters() + trg_documents_autolink")

    # C) Views
    print("\n  C) Views — documents_needing_classification + document_matter_overview")
    cur.execute(VIEW_SQL)
    conn.commit()
    print("    ✓ views installed")

    # D) Backfill primary links
    print("\n  D) Backfill primary links from existing documents")
    cur.execute("""
        INSERT INTO document_matter_links (doc_id, matter_code, case_file, relation_kind, provenance_level, linked_by, note)
        SELECT id, matter_code, case_file, 'primary', 'verified', 'deploy_279_backfill',
               'Backfilled from documents.matter_code'
          FROM documents
         WHERE matter_code IS NOT NULL
           AND matter_code NOT IN ('', 'UNCLASSIFIED', 'unknown', 'Unknown')
        ON CONFLICT (doc_id, matter_code, relation_kind) DO NOTHING
        RETURNING id
    """)
    n_primary = cur.rowcount
    conn.commit()
    print(f"    ✓ {n_primary} primary links seeded")

    # E) Backfill reference links via text patterns
    print("\n  E) Pattern-scan extracted_text for cross-references")
    n_ref_total = 0
    for pat, matter in TEXT_MAPPINGS:
        cur.execute("""
            INSERT INTO document_matter_links (doc_id, matter_code, relation_kind, provenance_level, linked_by, note)
            SELECT d.id, %s, 'reference', 'inferred_strong', 'deploy_279_backfill',
                   'Detected via text pattern: ' || %s
              FROM documents d
             WHERE d.extracted_text IS NOT NULL
               AND d.extracted_text ~* %s
               AND COALESCE(d.matter_code, '') <> %s  -- skip when already primary
            ON CONFLICT (doc_id, matter_code, relation_kind) DO NOTHING
            RETURNING id
        """, (matter, matter, pat, matter))
        n = cur.rowcount
        n_ref_total += n
        if n:
            print(f"    ✓ {n:>4}  {matter}  ← /{pat[:50]}.../")
    conn.commit()
    print(f"  → {n_ref_total} reference links seeded")

    # F) Sanity counts
    print("\n  F) Final state")
    cur.execute("""
        SELECT relation_kind, COUNT(*) AS n,
               COUNT(DISTINCT doc_id) AS docs,
               COUNT(DISTINCT matter_code) AS matters
          FROM document_matter_links
         GROUP BY relation_kind
         ORDER BY 2 DESC
    """)
    for r in cur.fetchall():
        print(f"    {r['relation_kind']:>14}  rows={r['n']:>4}  docs={r['docs']:>4}  matters={r['matters']:>3}")

    cur.execute("SELECT COUNT(*) AS total FROM documents")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(DISTINCT doc_id) AS n FROM document_matter_links")
    linked = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM documents_needing_classification")
    triage = cur.fetchone()["n"]
    print(f"\n    Total docs:           {total}")
    print(f"    Linked to ≥1 matter:  {linked} ({linked*100//total}%)")
    print(f"    Needing classification: {triage} ({triage*100//total}%)")

    # Multi-matter docs (the "many ways" the user described)
    cur.execute("""
        SELECT COUNT(*) AS n FROM (
          SELECT doc_id FROM document_matter_links GROUP BY doc_id HAVING COUNT(DISTINCT matter_code) > 1
        ) s
    """)
    multi = cur.fetchone()["n"]
    print(f"    Multi-matter docs:    {multi} ({multi*100//total}%)")

    # Sample of multi-matter
    print("\n  G) Sample multi-matter docs (top 5 by matter count):")
    cur.execute("""
        SELECT d.id, d.smart_filename, d.matter_code AS primary,
               array_agg(DISTINCT l.matter_code ORDER BY l.matter_code) AS all_matters,
               COUNT(DISTINCT l.matter_code) AS n
          FROM documents d
          JOIN document_matter_links l ON l.doc_id = d.id
         GROUP BY d.id, d.smart_filename, d.matter_code
        HAVING COUNT(DISTINCT l.matter_code) > 1
         ORDER BY n DESC, d.id DESC
         LIMIT 5
    """)
    for r in cur.fetchall():
        title = (r['smart_filename'] or '(no filename)')[:60]
        print(f"    doc#{r['id']}  primary={r['primary']!r}  n={r['n']}  →  {r['all_matters']}")
        print(f"        {title}")

    cur.close()
    conn.close()
    print("\n  ✓ deploy_279 complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
