-- deploy_717: outward-action guard — SHADOW-mode observation + a GOVERNED classifier.
--
-- Phase 1 of wiring the Supervisor's outward chokepoint to every egress. This migration is
-- OBSERVATION-ONLY: it adds the classifier's source of truth (internal_targets), a shadow log of
-- what the guard WOULD do, and a shadow->block config flip (mirrors ontology_validator_config).
-- No send behavior changes until outward_guard_config.mode is flipped to 'block'.
BEGIN;

-- 1) internal_targets — the GOVERNED source of truth for "who is internal" (operator/sim).
--    A send whose recipient matches NO active row here is classified 'outward'. Data, not code:
--    add/remove an internal target = an audited row, never a code edit (directive: routing is DATA).
CREATE TABLE IF NOT EXISTS internal_targets (
  id         serial PRIMARY KEY,
  channel    text NOT NULL CHECK (channel IN ('telegram','email','*')),
  identifier text NOT NULL,     -- chat_id, email address, or the prefix/domain value to match
  match_type text NOT NULL DEFAULT 'exact' CHECK (match_type IN ('exact','prefix','domain')),
  label      text,              -- human name of the internal target
  note       text,
  active     boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (channel, identifier, match_type)
);

-- Seed: the operator (Jonathan) + the simulator range are internal. Everything else is outward.
-- (These mirror the hardcoded FLOOR in outward_guard.py, which is the fail-safe if the DB is down.)
INSERT INTO internal_targets (channel, identifier, match_type, label, note) VALUES
  ('telegram','6513067717','exact', 'Jonathan (operator)', 'S14-governed; an operator message is never an outward move'),
  ('telegram','999000','prefix',    'simulator personas',  'sim range 999000* — never reaches a real chat'),
  ('email','jonzschoche@gmail.com','exact','Jonathan (operator)', NULL),
  ('email','jonathan@hayuma.org','exact',  'Jonathan (operator)', NULL)
ON CONFLICT (channel, identifier, match_type) DO NOTHING;

-- 2) outward_shadow_log — what the guard WOULD have done, per intercepted send. Log-only in shadow.
CREATE TABLE IF NOT EXISTS outward_shadow_log (
  id             bigserial PRIMARY KEY,
  ts             timestamptz NOT NULL DEFAULT now(),
  channel        text NOT NULL,           -- telegram | email | filing
  source         text,                    -- which agent/script originated the send
  guard_target   text,                    -- domain:ref the guard derived (e.g. telegram:5992075757)
  content_hash   text,
  classification text NOT NULL,           -- internal | outward
  would_decision text NOT NULL,           -- internal_skip | would_hold | would_allow_approved
  approved_order integer,                 -- work_order id if a matching approval already existed
  preview        text
);
CREATE INDEX IF NOT EXISTS idx_outward_shadow_ts       ON outward_shadow_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_outward_shadow_decision ON outward_shadow_log (would_decision);

-- 3) outward_guard_config — the shadow->block switch (single row), same idiom as ontology_validator_config.
--    Flip to enforce with: UPDATE outward_guard_config SET mode='block';
CREATE TABLE IF NOT EXISTS outward_guard_config (
  id   integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  mode text NOT NULL DEFAULT 'shadow' CHECK (mode IN ('shadow','block'))
);
INSERT INTO outward_guard_config (id, mode) VALUES (1, 'shadow') ON CONFLICT (id) DO NOTHING;

COMMIT;
