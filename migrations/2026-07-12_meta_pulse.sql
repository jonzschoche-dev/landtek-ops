-- meta-pulse: the $0, deterministic self-improving loop (2026-07-12).
--
-- Two tables. Both idempotent (safe to re-apply):
--
--   meta_pulse_state    — a singleton row holding the LAST run's observed signal
--                         state (per-assertion pass/fail, open holes_findings ids,
--                         active drift keys). The delta is computed against this.
--
--   system_evolution_log — the append-once ledger of NEW gaps only. One row per
--                         gap_id, ever. A known gap is never re-logged. Carries an
--                         A74-style machine-checkable recheck_condition so the pulse
--                         can auto-CLOSE it deterministically (no model call), and an
--                         auto_resolvable flag: FALSE rows that are still open are the
--                         ONLY queue that needs a human/Claude decision.
--
-- The pulse itself calls NO model. It wraps truth_tests/run_all.py and
-- scripts/ontology_check.py, diffs their output against meta_pulse_state, and
-- records deltas here. See scripts/meta_pulse.py.

BEGIN;

CREATE TABLE IF NOT EXISTS meta_pulse_state (
    id           integer PRIMARY KEY DEFAULT 1,
    last_run_at  timestamptz,
    -- {"testfile::label": "pass"|"fail", ...}
    assertions   jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- [int]  ids of holes_findings rows that were status='open' last run
    holes_ids    jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- [text] normalized drift signal keys active last run (invariant:/enforcement:/alignment:)
    drift        jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- true once the baseline has been seeded (first run seeds, logs nothing)
    seeded       boolean NOT NULL DEFAULT false,
    CONSTRAINT meta_pulse_state_singleton CHECK (id = 1)
);

-- Seed the singleton so UPDATE ... WHERE id=1 always has a row.
INSERT INTO meta_pulse_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS system_evolution_log (
    gap_id           text PRIMARY KEY,        -- stable key: assertion:… | hole:<id> | drift:<key>
    kind             text NOT NULL,           -- 'assertion' | 'hole' | 'drift'
    detail           text,
    metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,
    recheck_condition text,                    -- machine-checkable predicate (NULL = none)
    auto_resolvable  boolean NOT NULL DEFAULT false,
    status           text NOT NULL DEFAULT 'open',   -- 'open' | 'resolved'
    first_seen       timestamptz NOT NULL DEFAULT now(),
    last_seen        timestamptz NOT NULL DEFAULT now(),
    resolved_at      timestamptz,
    resolved_via     text,
    CONSTRAINT system_evolution_log_kind_ck   CHECK (kind   IN ('assertion','hole','drift')),
    CONSTRAINT system_evolution_log_status_ck CHECK (status IN ('open','resolved'))
);

-- The operator/Claude decision queue: open gaps with no automatic resolution.
CREATE INDEX IF NOT EXISTS system_evolution_log_open_manual_idx
    ON system_evolution_log (status, auto_resolvable)
    WHERE status = 'open' AND auto_resolvable = false;

COMMIT;
