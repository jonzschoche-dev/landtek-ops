#!/usr/bin/env python3
"""apply_deploy_317_evidence_trail.py — make the physical filing system queryable.

The biggest leverage move in the action plan. Maps your four physical buckets
(Prime Evidence, Titles+TaxDecs, Evidence Trail, Working Cases) to first-class
schema concepts so Leo can answer "what's our evidence for claim X?" as a SQL
query instead of a hallucination.

Schema additions:
  documents.doc_role          text  (prime_evidence, title_instrument,
                                     tax_declaration, transfer_instrument,
                                     chain_proof, pleading, order_resolution,
                                     correspondence, background, not_yet_assessed)
  documents.exhibit_tier      text  (primary, rebuttal, supplemental,
                                     not_for_trial, unassessed)
  documents.chain_of_custody  text  (free-form narrative — when/how received)
  documents.lt_number         text UNIQUE  (LT-NNNN canonical citable id)

New tables:
  claims                — legal propositions the case rests on
  evidence_trail        — doc → claim mapping with relation kind + weight

New views:
  v_prime_evidence              — exhibit list grouped by claim
  v_evidence_trail_per_claim    — claim-centric narrative (each claim's docs)
  v_filing_gaps                 — open claims with <2 primary exhibits
  v_doc_by_lt                   — fast LT-NNNN lookup

LT-NNNN numbering scheme:
  LT-0001 to LT-0999   → Case 26-360 (MWK-001) docs, sequential by id
  LT-1000+             → Other matters (Paracale, Capacuan, etc.)
  Stable forever — never renumbered. Goes on physical doc + Drive filename.

Initial seed:
  - 6 foundational claims from CLAUDE.md (T-4497 mother title, void chain,
    MMK!=MWK, etc.)
  - LT-NNNN assigned to all 388 existing documents
  - doc_role / exhibit_tier left as 'not_yet_assessed' / 'unassessed' for
    Jonathan + future Opus probes to populate over time
"""
from __future__ import annotations
import os
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── 1. ALTER documents ─────────────────────────────────────────────
    cur.execute("""
        ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS doc_role         text,
            ADD COLUMN IF NOT EXISTS exhibit_tier     text DEFAULT 'unassessed',
            ADD COLUMN IF NOT EXISTS chain_of_custody text,
            ADD COLUMN IF NOT EXISTS lt_number        text
    """)
    cur.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='documents_doc_role_check') THEN
            ALTER TABLE documents ADD CONSTRAINT documents_doc_role_check
              CHECK (doc_role IS NULL OR doc_role IN (
                'prime_evidence','title_instrument','tax_declaration',
                'transfer_instrument','chain_proof','pleading','order_resolution',
                'correspondence','background','not_yet_assessed'));
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='documents_exhibit_tier_check') THEN
            ALTER TABLE documents ADD CONSTRAINT documents_exhibit_tier_check
              CHECK (exhibit_tier IN (
                'primary','rebuttal','supplemental','not_for_trial','unassessed'));
          END IF;
        END $$;
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_lt_number ON documents(lt_number) WHERE lt_number IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_doc_role ON documents(doc_role) WHERE doc_role IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_exhibit_tier ON documents(exhibit_tier) WHERE exhibit_tier != 'unassessed'")
    print("✓ documents columns + constraints + indexes")

    # ── 2. claims table ───────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id                SERIAL PRIMARY KEY,
            case_file         text NOT NULL,
            claim_text        text NOT NULL,
            claim_kind        text NOT NULL CHECK (claim_kind IN
                              ('factual','legal','procedural','foundational')),
            required_to_prove jsonb,
            status            text NOT NULL DEFAULT 'open' CHECK (status IN
                              ('open','proven','disputed','withdrawn','dropped')),
            priority          integer NOT NULL DEFAULT 3,
            short_label       text,
            notes             text,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_claims_case_file ON claims(case_file)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status) WHERE status='open'")
    print("✓ claims table")

    # ── 3. evidence_trail table ──────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS evidence_trail (
            id                     SERIAL PRIMARY KEY,
            claim_id               integer NOT NULL REFERENCES claims(id),
            supporting_doc_id      integer REFERENCES documents(id),
            supporting_title_id    integer,
            supporting_transfer_id integer,
            relation_kind          text NOT NULL CHECK (relation_kind IN
                                   ('proves','corroborates','impeaches','contextualizes')),
            weight                 text NOT NULL CHECK (weight IN
                                   ('primary','strong','moderate','weak')),
            narrative              text,
            provenance_level       text NOT NULL DEFAULT 'inferred_strong',
            added_at               timestamptz NOT NULL DEFAULT now(),
            added_by               text,
            CHECK (
                supporting_doc_id IS NOT NULL
                OR supporting_title_id IS NOT NULL
                OR supporting_transfer_id IS NOT NULL
            )
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_evidence_trail_claim ON evidence_trail(claim_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_evidence_trail_doc ON evidence_trail(supporting_doc_id)")
    print("✓ evidence_trail table")

    # ── 4. Views ─────────────────────────────────────────────────────
    cur.execute("""
        CREATE OR REPLACE VIEW v_doc_by_lt AS
        SELECT lt_number, id AS doc_id, original_filename, doc_role,
               exhibit_tier, case_file, doc_date
          FROM documents
         WHERE lt_number IS NOT NULL
    """)
    cur.execute("""
        CREATE OR REPLACE VIEW v_prime_evidence AS
        SELECT d.lt_number, d.id AS doc_id, d.original_filename,
               d.doc_role, d.exhibit_tier, d.case_file,
               et.claim_id, c.claim_text,
               et.relation_kind, et.weight
          FROM documents d
          LEFT JOIN evidence_trail et ON et.supporting_doc_id = d.id
          LEFT JOIN claims c ON c.id = et.claim_id
         WHERE d.exhibit_tier IN ('primary','rebuttal')
            OR d.doc_role = 'prime_evidence'
    """)
    cur.execute("""
        CREATE OR REPLACE VIEW v_evidence_trail_per_claim AS
        SELECT c.id, c.case_file, c.claim_text, c.short_label, c.status, c.priority,
               COALESCE(
                 json_agg(
                   jsonb_build_object(
                     'lt_number',  d.lt_number,
                     'doc_id',     d.id,
                     'filename',   d.original_filename,
                     'doc_role',   d.doc_role,
                     'relation',   et.relation_kind,
                     'weight',     et.weight,
                     'narrative',  et.narrative
                   )
                   ORDER BY CASE et.weight
                     WHEN 'primary' THEN 1
                     WHEN 'strong' THEN 2
                     WHEN 'moderate' THEN 3 ELSE 4 END
                 ) FILTER (WHERE et.id IS NOT NULL),
                 '[]'::json
               ) AS supporting_docs
          FROM claims c
          LEFT JOIN evidence_trail et ON et.claim_id = c.id
          LEFT JOIN documents d ON d.id = et.supporting_doc_id
         GROUP BY c.id
    """)
    cur.execute("""
        CREATE OR REPLACE VIEW v_filing_gaps AS
        SELECT c.id AS claim_id, c.case_file, c.claim_text, c.short_label,
               c.priority,
               COUNT(et.id) FILTER (WHERE et.weight='primary')                  AS primary_count,
               COUNT(et.id) FILTER (WHERE et.weight IN ('primary','strong'))    AS strong_or_better,
               COUNT(et.id)                                                     AS total_support
          FROM claims c
          LEFT JOIN evidence_trail et ON et.claim_id = c.id
         WHERE c.status = 'open'
         GROUP BY c.id
        HAVING COUNT(et.id) FILTER (WHERE et.weight='primary') < 2
        ORDER BY c.priority DESC, c.id
    """)
    print("✓ 4 views: v_doc_by_lt, v_prime_evidence, v_evidence_trail_per_claim, v_filing_gaps")

    # ── 5. LT-NNNN backfill (sequential within case_file) ─────────────
    # Scheme:
    #   LT-0001-0999  → MWK-001 docs (Case 26-360 universe)
    #   LT-1000-1999  → MWK-001 overflow (reserved)
    #   LT-2000+      → Paracale-001 and other matters
    cur.execute("SELECT COUNT(*) FROM documents WHERE lt_number IS NOT NULL")
    already_assigned = cur.fetchone()["count"]
    if already_assigned == 0:
        cur.execute("""
            WITH numbered AS (
              SELECT id, case_file,
                     ROW_NUMBER() OVER (PARTITION BY
                       CASE WHEN case_file = 'MWK-001' THEN 1 ELSE 2 END
                       ORDER BY id) AS rn
                FROM documents
            ),
            assigned AS (
              SELECT id, case_file,
                     CASE
                       WHEN case_file = 'MWK-001' THEN
                         'LT-' || LPAD(rn::text, 4, '0')
                       ELSE
                         'LT-' || LPAD((2000 + rn)::text, 4, '0')
                     END AS lt_number
                FROM numbered
            )
            UPDATE documents d
               SET lt_number = a.lt_number
              FROM assigned a
             WHERE d.id = a.id
        """)
        cur.execute("SELECT COUNT(*) FROM documents WHERE lt_number IS NOT NULL")
        new_assigned = cur.fetchone()["count"]
        print(f"✓ LT-NNNN assigned to {new_assigned} documents")
    else:
        print(f"✓ LT-NNNN already assigned to {already_assigned} documents (skipping)")

    # ── 6. Seed foundational claims from CLAUDE.md ────────────────────
    SEED_CLAIMS = [
        ("MWK-001", "foundational", 5, "MWK_T4497_mother_title",
         "TCT T-4497 is the mother title of the property at issue in Civil Case 26-360, registered to Heirs of Mary Worrick Keesey.",
         '["T-4497 issuance verified", "MWK heirs identified"]'),
        ("MWK-001", "factual", 5, "Balane_title_void_chain",
         "Gloria Balane's TCT T-079-2021002127 is void because it derives from cancelled T-52540 via a 2016 Deed of Sale executed by Cesar de la Fuente under an SPA that had been revoked in 2005.",
         '["2016 Deed of Sale exists","SPA revocation 2005 verified","T-52540 cancellation status","derivative chain verified"]'),
        ("MWK-001", "factual", 5, "Cesar_SPA_revoked_2005",
         "The Special Power of Attorney held by Cesar de la Fuente was revoked in 2005, predating the 2016 Deed of Sale he purported to execute under that authority.",
         '["SPA revocation document"]'),
        ("MWK-001", "factual", 4, "T30683_separate_matter",
         "TCT T-30683 (Manguisoc Mercedes) is NOT a derivative of T-4497; it is held in undivided interest by the four MWK heirs but is a separate property matter.",
         '["title_chain shows no T-4497 → T-30683 verified edge","heirs documents"]'),
        ("MWK-001", "factual", 4, "MMK_not_equal_MWK",
         "MMK and MWK refer to DIFFERENT entities. MWK = Mary Worrick Keesey. Any document conflating the two introduces evidentiary risk.",
         '["MWK identity verification","corpus occurrence count"]'),
        ("MWK-001", "factual", 3, "T4494_separate_matter",
         "TCT T-4494 (Cabanbanan San Vicente) is a separate property and NOT a verified derivative of T-4497.",
         '["title_chain shows no T-4497 → T-4494 verified edge"]'),
    ]
    cur.execute("SELECT COUNT(*) FROM claims")
    if cur.fetchone()["count"] == 0:
        for case_file, kind, priority, label, text, required in SEED_CLAIMS:
            cur.execute("""
                INSERT INTO claims (case_file, claim_kind, priority, short_label, claim_text, required_to_prove)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """, (case_file, kind, priority, label, text, required))
        print(f"✓ seeded {len(SEED_CLAIMS)} foundational claims")
    else:
        print(f"✓ claims already populated (skipping seed)")

    # ── 7. deploy_log marker ──────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deploy_log (
            deploy_id text PRIMARY KEY, summary text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_317',
         'Evidence Trail schema: documents.{doc_role,exhibit_tier,chain_of_custody,lt_number} + claims + evidence_trail + 4 views. LT-NNNN assigned to all docs. 6 foundational claims seeded from CLAUDE.md. Physical buckets now queryable.')
        ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary
    """)
    print("✓ deploy_317 logged")

    # Summary
    cur.execute("SELECT COUNT(*) AS docs FROM documents")
    docs = cur.fetchone()["docs"]
    cur.execute("SELECT COUNT(*) AS docs_lt FROM documents WHERE lt_number IS NOT NULL")
    docs_lt = cur.fetchone()["docs_lt"]
    cur.execute("SELECT COUNT(*) FROM claims")
    claims = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM v_filing_gaps")
    gaps = cur.fetchone()["count"]
    print(f"\n=== summary ===")
    print(f"  documents:          {docs}  (LT-NNNN assigned: {docs_lt})")
    print(f"  claims (open):      {claims}")
    print(f"  active filing gaps: {gaps}  (claims with <2 primary exhibits)")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
