-- deploy_879: A79 role axis — comms_role_policy (the single policy the gate reads to clamp every
-- externalizing path: COMM-AGENT-MAX bot reply · A76/P2 reactive increment · A75 pulse). Shadow-first;
-- the clamp in outward_guard.py logs what it WOULD clamp and blocks nothing until a role graduates.
-- Idempotent. Rollback: DROP VIEW v_comms_role_policy; DROP TABLE comms_role_policy;
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_879_comms_role_policy.sql

CREATE TABLE IF NOT EXISTS comms_role_policy (
    role               text PRIMARY KEY,
    disclosure_ceiling text NOT NULL DEFAULT 'none',
    gate_default       text NOT NULL DEFAULT 'hold',
    dose_ceiling       integer NOT NULL DEFAULT 1,
    cadence            text NOT NULL DEFAULT 'gentle',
    projection_profile text NOT NULL DEFAULT 'human_safe',
    notes              text,
    updated_at         timestamptz DEFAULT now(),
    updated_by         text
);

INSERT INTO comms_role_policy (role, disclosure_ceiling, gate_default, dose_ceiling, cadence, projection_profile, notes) VALUES
('counterparty', 'none',                'refuse', 0,  'gentle',   'human_safe',   'NEVER auto-anything. Operator-only. A5 hard wall + A21 outward chokepoint.'),
('counsel',      'facts_plus_strategy', 'allow',  3,  'standard', 'human_safe',   'External counsel lane — facts + limited strategy, still S14 human-readable.'),
('client',       'full',                'allow',  5,  'gentle',   'human_safe',   'MWK-001 lane — full A75/A32 projection, gentle cadence.'),
('internal',     'full',                'allow',  10, 'standard', 'machine_typed','Operator + sim lane — typed handles intact for downstream agents.'),
('public',       'none',                'refuse', 0,  'gentle',   'human_safe',   'No auto-publish. A11 + A21 only.'),
('agent',        'machine_typed',       'allow',  20, 'urgent',   'machine_typed','Internal fleet — full typed projection, higher dose for A71 metabolism.')
ON CONFLICT (role) DO UPDATE SET
    disclosure_ceiling = EXCLUDED.disclosure_ceiling, gate_default = EXCLUDED.gate_default,
    dose_ceiling = EXCLUDED.dose_ceiling, cadence = EXCLUDED.cadence,
    projection_profile = EXCLUDED.projection_profile, notes = EXCLUDED.notes, updated_at = now();

CREATE OR REPLACE VIEW v_comms_role_policy AS SELECT * FROM comms_role_policy;

-- self-test: exactly the 6 canonical roles, counterparty + public refuse at dose 0
SELECT 'comms_role_policy rows (expect 6): ' || count(*)::text FROM comms_role_policy;
SELECT 'refuse-role dose_ceilings (expect 0,0): ' || string_agg(dose_ceiling::text, ',' ORDER BY role)
  FROM comms_role_policy WHERE gate_default = 'refuse';
