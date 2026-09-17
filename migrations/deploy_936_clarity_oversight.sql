-- deploy_936: clarity + human-oversight flags on derived cards
-- Unclear data must never look finished. Flag for human review; measure intake vs 90% target.
--
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_936_clarity_oversight.sql

BEGIN;

ALTER TABLE title_brief
  ADD COLUMN IF NOT EXISTS clarity_score        numeric(5,3),
  ADD COLUMN IF NOT EXISTS clarity_status       text,          -- clear | partial | unclear
  ADD COLUMN IF NOT EXISTS missing_fields       text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS needs_human_review   boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS oversight_reason     text;

ALTER TABLE matter_brief
  ADD COLUMN IF NOT EXISTS clarity_score        numeric(5,3),
  ADD COLUMN IF NOT EXISTS clarity_status       text,
  ADD COLUMN IF NOT EXISTS missing_fields       text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS needs_human_review   boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS oversight_reason     text;

CREATE INDEX IF NOT EXISTS title_brief_oversight_idx
  ON title_brief (needs_human_review) WHERE needs_human_review;
CREATE INDEX IF NOT EXISTS matter_brief_oversight_idx
  ON matter_brief (needs_human_review) WHERE needs_human_review;

-- Standing intake meter (append-only)
CREATE TABLE IF NOT EXISTS intake_clarity_log (
    id                  bigserial PRIMARY KEY,
    logged_at           timestamptz NOT NULL DEFAULT now(),
    -- doc path
    docs_total          int,
    docs_with_text      int,
    docs_linked_text    int,
    docs_with_facts     int,
    doc_fact_intake_pct  numeric(6,2),
    -- fact → typed fields
    facts_total         int,
    facts_with_fields   int,
    fact_field_intake_pct numeric(6,2),
    -- title cards
    titles_total        int,
    titles_clear        int,
    titles_partial      int,
    titles_unclear      int,
    titles_need_review  int,
    title_core_intake_pct numeric(6,2),  -- (clear+partial)/total  — "usable for table"
    -- matter cards
    matters_total       int,
    matters_need_review int,
    target_pct          numeric(6,2) NOT NULL DEFAULT 90.0,
    notes               text
);

COMMENT ON TABLE intake_clarity_log IS
  'Meter toward 90%+ table intake. Unclear rows are counted and flagged, never disguised as complete.';

COMMIT;

SELECT 'clarity cols title_brief: ' || count(*)::text
  FROM information_schema.columns
 WHERE table_name='title_brief' AND column_name='needs_human_review';
