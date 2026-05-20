#!/usr/bin/env python3
"""Deploy 221B — Proposal sibling infrastructure.

Per design P9 + Q3: LLM-driven processes write to `proposed_changes`, never
directly to critical tables. Promotion from proposal to verified requires
human review via the promote CLI (with explicit override session vars).

Single generic table (vs. one-per-target-table) — proposed row state lives
in JSONB. Cleaner schema, uniform CLI.

Idempotent.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS proposed_changes (
    id SERIAL PRIMARY KEY,
    target_table TEXT NOT NULL CHECK (target_table IN (
        'titles', 'title_chain', 'subdivision_plans',
        'instruments_on_title', 'entities', 'title_transfers',
        'verified_claims'
    )),
    target_row_id INTEGER,           -- NULL = INSERT proposal
    operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    proposed_state JSONB NOT NULL,   -- complete proposed row state
                                     -- (for UPDATE: merge keys onto current row)
    proposed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    proposed_by TEXT NOT NULL,       -- 'gemini_extraction', 'truth_negotiator', 'manual', etc.
    proposed_source_doc_id INTEGER REFERENCES documents(id),
    rationale TEXT,
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'approved', 'rejected', 'withdrawn')),
    reviewed_by TEXT
        CHECK (reviewed_by IS NULL OR reviewed_by IN ('jonathan', 'barandon', 'manual_review')),
    reviewed_at TIMESTAMPTZ,
    rejection_reason TEXT,
    promoted_at TIMESTAMPTZ,
    promoted_with_lock TEXT
        CHECK (promoted_with_lock IS NULL OR promoted_with_lock = 'hard')
);

CREATE INDEX IF NOT EXISTS idx_proposed_changes_status_table
    ON proposed_changes(review_status, target_table);
CREATE INDEX IF NOT EXISTS idx_proposed_changes_target
    ON proposed_changes(target_table, target_row_id);
CREATE INDEX IF NOT EXISTS idx_proposed_changes_pending
    ON proposed_changes(proposed_at) WHERE review_status = 'pending';

GRANT INSERT, SELECT, UPDATE ON proposed_changes TO n8n;
GRANT USAGE, SELECT ON SEQUENCE proposed_changes_id_seq TO n8n;
"""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    print("Creating proposed_changes table…")
    cur.execute(SCHEMA_SQL)
    print("✓ proposed_changes schema ready")

    cur.execute("SELECT COUNT(*) FROM proposed_changes")
    n = cur.fetchone()[0]
    print(f"  Current proposals: {n}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
