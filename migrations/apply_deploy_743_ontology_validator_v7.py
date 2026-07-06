#!/usr/bin/env python3
"""apply_deploy_743_ontology_validator_v7.py — V7: comms identity isolation (A25), SHADOW.

Adds the 7th ontology_validator check: a channel_users row's mapped_client_code must resolve
to exactly one real client (A25 Part 1 — declared-client validity). This is the comms analogue
of V4 (matter_facts) and V6 (geometry). Spec: docs/ontology_validator_V7_channel_users_spec.md.

SHADOW MODE: V7 ships in 'log' — the trigger logs ONTOLOGY_CHANNEL_BAD_CLIENT to holes_findings
and BLOCKS NOTHING. Flip to enforce only post-Aug-12 + explicit approval:
    UPDATE ontology_validator_config SET mode='block' WHERE check_code='V7';

Additive + safe:
  - Reuses the ontology_reject() logger + ontology_validator_config from deploy_691 (does NOT
    redefine them). Aborts with a clear message if deploy_691 was never applied.
  - Allowlist: operators (mapped_operator / role='operator') and sim personas (channel_user_id
    LIKE '999000%') are OUT OF SCOPE — excluded in both the view and the trigger.
  - A25 Part 2 (cross-channel same-human -> one client) is NOT built here: it needs a person-key
    (channel_users.entity_id), a HELD schema decision. This migration is Part 1 only.
  - Reversible: --rollback drops the V7 trigger/view/function and removes the V7 config row only
    (leaves deploy_691's shared objects intact).
  - Self-tests that the trigger is genuinely non-blocking in 'log' mode before committing.

Usage (run on the VPS — needs DB access):
    python3 migrations/apply_deploy_743_ontology_validator_v7.py --go
    python3 migrations/apply_deploy_743_ontology_validator_v7.py --rollback
"""
import os
import sys

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

APPLY_SQL = r"""
-- 0. config table exists (idempotent; deploy_691 normally owns it) --------------
CREATE TABLE IF NOT EXISTS ontology_validator_config (
  check_code text PRIMARY KEY,
  mode       text NOT NULL DEFAULT 'log' CHECK (mode IN ('log','block','off')),
  note       text,
  updated_at timestamptz DEFAULT now()
);
INSERT INTO ontology_validator_config(check_code, mode, note) VALUES
  ('V7','log','channel identity client-isolation (A25) via v_ontology_channel_cross')
ON CONFLICT (check_code) DO NOTHING;

-- 1. detector view — declared client must resolve to a real, single client -----
--    Allowlist: operators + sim personas are out of scope (they carry no client).
CREATE OR REPLACE VIEW v_ontology_channel_cross AS
SELECT cu.id                             AS ref,
       cu.channel_id,
       cu.channel_user_id,
       cu.mapped_client_code             AS declared_client,
       _client_of(cu.mapped_client_code) AS resolved_client
FROM   channel_users cu
WHERE  cu.mapped_client_code IS NOT NULL
  AND  _client_of(cu.mapped_client_code) IS NULL          -- resolves to NOTHING -> invalid
  AND  coalesce(cu.mapped_operator,'') = ''               -- exclude internal operators
  AND  coalesce(cu.role,'') <> 'operator'                 -- exclude operator role
  AND  cu.channel_user_id NOT LIKE '999000%';             -- exclude sim personas (S1 range)

-- 2. write-time trigger fn (same shape as ontvv_client_isolation / ontvv_geometry_isolation)
CREATE OR REPLACE FUNCTION ontvv_channel_isolation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text;
BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V7';
  IF m IS NULL OR m='off' THEN RETURN NEW; END IF;
  IF NEW.mapped_client_code IS NOT NULL
     AND coalesce(NEW.mapped_operator,'') = ''
     AND coalesce(NEW.role,'') <> 'operator'
     AND NEW.channel_user_id NOT LIKE '999000%'
     AND _client_of(NEW.mapped_client_code) IS NULL THEN
    PERFORM ontology_reject('ONTOLOGY_CHANNEL_BAD_CLIENT',
      'channel_users id=' || coalesce(NEW.id::text,'?') ||
      ' mapped_client_code=' || NEW.mapped_client_code ||
      ' does not resolve to a known client');
    IF m='block' THEN
      RAISE EXCEPTION 'ontology_validator V7: channel_users.mapped_client_code (%) must resolve to exactly one known client (ONTOLOGY.md A25)',
        NEW.mapped_client_code;
    END IF;
  END IF;
  RETURN NEW;
END $$;
"""


def _preflight(cur):
    """deploy_691's shared logger must exist — V7 depends on it."""
    cur.execute("SELECT to_regprocedure('ontology_reject(text,text)') IS NOT NULL;")
    if not cur.fetchone()[0]:
        raise RuntimeError("ontology_reject() missing — apply deploy_691 (V1/V3/V4) first.")
    cur.execute("SELECT to_regprocedure('_client_of(text)') IS NOT NULL;")
    if not cur.fetchone()[0]:
        raise RuntimeError("_client_of() missing — apply deploy_716 (V4 enforce) first.")


def _apply(cur):
    cur.execute(APPLY_SQL)
    cur.execute("DROP TRIGGER IF EXISTS ontvv_v7_channel_users ON channel_users;")
    cur.execute(
        "CREATE TRIGGER ontvv_v7_channel_users BEFORE INSERT OR UPDATE ON channel_users "
        "FOR EACH ROW EXECUTE FUNCTION ontvv_channel_isolation();"
    )


def _rollback(cur):
    cur.execute("DROP TRIGGER IF EXISTS ontvv_v7_channel_users ON channel_users;")
    cur.execute("DROP VIEW IF EXISTS v_ontology_channel_cross;")
    cur.execute("DROP FUNCTION IF EXISTS ontvv_channel_isolation();")
    cur.execute("DELETE FROM ontology_validator_config WHERE check_code='V7';")


PROBE_CODE = "__v7_selftest_noclient__"
PROBE_UID = "__v7_selftest__"


def _selftest(cur):
    """Prove the V7 trigger fires AND is non-blocking in 'log' mode, then clean up.

    Inserts a probe channel_users row with a bogus client under a SAVEPOINT: in 'log' mode the
    trigger must log a finding and let the write through (no RAISE). Anything else is a bug.
    """
    cur.execute("SELECT id FROM channels ORDER BY id LIMIT 1;")
    row = cur.fetchone()
    if not row:
        print("  selftest: no channels row to probe against — logger path only (trigger unverified live).")
        return
    ch_id = row[0]
    cur.execute("SAVEPOINT v7probe;")
    try:
        cur.execute(
            "INSERT INTO channel_users (channel_id, channel_user_id, role, mapped_client_code) "
            "VALUES (%s, %s, 'client', %s);",
            (ch_id, PROBE_UID, PROBE_CODE),
        )  # must NOT raise in log mode
        cur.execute(
            "SELECT count(*) FROM holes_findings "
            "WHERE hole_type='ONTOLOGY_CHANNEL_BAD_CLIENT' AND description LIKE %s;",
            (f"%{PROBE_CODE}%",),
        )
        n = cur.fetchone()[0]
        assert n >= 1, "V7 trigger did not log the bad-client probe — investigate before applying"
        print(f"  selftest OK — probe inserted (NOT blocked, log mode) + {n} finding logged.")
    finally:
        # undo the probe row entirely, then remove its finding
        cur.execute("ROLLBACK TO SAVEPOINT v7probe;")
        cur.execute("RELEASE SAVEPOINT v7probe;")
        cur.execute("DELETE FROM holes_findings WHERE description LIKE %s;", (f"%{PROBE_CODE}%",))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("--go", "--rollback"):
        print(__doc__)
        sys.exit(2)
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            if mode == "--rollback":
                _rollback(cur)
                conn.commit()
                print("ontology_validator V7: rolled back (trigger/view/function dropped, V7 config row removed).")
                return
            _preflight(cur)
            _apply(cur)
            _selftest(cur)
            conn.commit()
            with conn.cursor() as c2:
                c2.execute("SELECT check_code, mode FROM ontology_validator_config WHERE check_code='V7';")
                cfg = c2.fetchone()
                c2.execute("SELECT count(*) FROM v_ontology_channel_cross;")
                live = c2.fetchone()[0]
        print("ontology_validator V7 applied (SHADOW).")
        print(f"  config: {cfg}")
        print(f"  v_ontology_channel_cross live violations right now: {live} (expected 0)")
        print("  V7 in 'log' mode — nothing is blocked. Flip to 'block' only post-Aug-12 + approval.")
    except Exception as e:
        conn.rollback()
        print(f"FAILED, rolled back: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
