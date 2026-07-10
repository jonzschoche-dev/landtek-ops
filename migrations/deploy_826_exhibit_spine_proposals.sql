-- deploy_826_exhibit_spine_proposals.sql — staging table for Exhibit-Spine Suggestions v2.
-- Suggestions are PROPOSALS, never direct writes: exhibit_spine.py --suggest fills this table;
-- an operator applies one via --apply <id>, which inserts into case_thread_documents THROUGH the
-- enforced V9 (A54 client-scope) gate. V10/A56 untouched (finalized_at stays operator-only).
-- Additive + reversible: DROP TABLE exhibit_spine_proposals.

CREATE TABLE IF NOT EXISTS exhibit_spine_proposals (
  id                serial PRIMARY KEY,
  main_doc_id       integer NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
  case_file         text NOT NULL,
  thread_name       text NOT NULL,
  proposed_members  jsonb NOT NULL,   -- [{doc_id, role: filing_main|exhibit|cover, label, order_seq, fn}]
  gaps              jsonb,            -- labels the main's TEXT cites but no corpus doc matches = missing-evidence LEADS
  basis             text,             -- how the proposal was derived (grounded, human-readable)
  status            text NOT NULL DEFAULT 'pending',   -- pending | applied | rejected
  created_at        timestamptz DEFAULT now(),
  decided_at        timestamptz,
  applied_thread_id integer REFERENCES case_threads(id)
);
CREATE INDEX IF NOT EXISTS idx_esp_status ON exhibit_spine_proposals (status);
COMMENT ON TABLE exhibit_spine_proposals IS
  'Operator-gated exhibit-spine proposals (deploy_826). --suggest writes here; --apply inserts to case_thread_documents through the V9 gate. gaps = cited-but-absent exhibit labels (missing-evidence leads).';