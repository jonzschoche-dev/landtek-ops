-- drip_prospect_2026-10-23.sql — the expansive layer upstream of ladders (Jonathan, 23 Oct 2026: "these tables must
-- be expansive and the whole corpus needs to be swept for prospects for MWK issues, administrative etc").
-- A prospect = any possible MWK issue found in the corpus, before it becomes a ladder. Lanes keep the drip honest:
--   drip       a follow-up the drip may carry (records ask, acknowledgment, reply owed)
--   legal_desk a position/decision for Jonathan (the drip follows, never sets positions)
--   counsel    needs a lawyer's signature or reaches a represented party
--   hold       parked (posture, timing, or Jonathan's instruction)
-- Upsert on dedupe_key (never delete and reinsert). Promotion to a ladder is Jonathan's action.
CREATE TABLE IF NOT EXISTS drip_prospect (
  id            bigserial PRIMARY KEY,
  client_code   text NOT NULL,
  matter_code   text,
  kind          text NOT NULL,
  title         text NOT NULL,
  detail        text,
  office        text,
  lane          text NOT NULL DEFAULT 'drip' CHECK (lane IN ('drip','legal_desk','counsel','hold')),
  status        text NOT NULL DEFAULT 'new' CHECK (status IN ('new','promoted','dismissed','merged','done')),
  score         numeric(6,1) NOT NULL DEFAULT 0,
  source_kind   text NOT NULL,
  source_ref    text NOT NULL,
  excerpt       text,
  evidence_doc_ids integer[] NOT NULL DEFAULT '{}',
  ladder        text,
  dedupe_key    text NOT NULL UNIQUE,
  first_seen    timestamptz NOT NULL DEFAULT now(),
  last_seen     timestamptz NOT NULL DEFAULT now(),
  decided_at    timestamptz,
  decision_note text
);
CREATE INDEX IF NOT EXISTS drip_prospect_open_idx ON drip_prospect (client_code, status, lane, score DESC);
