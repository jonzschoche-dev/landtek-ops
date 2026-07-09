-- deploy_810: agent_registry — the A61 tier registry + Supervisor Phase-2 work-routing map.
--
-- Graduates A61 ("the autonomy ladder is governance"): tiers become REGISTRY-RECORDED instead of living
-- in prose/config. A61 is strict — a tier may only RISE via a metric gate + human sign-off, recorded,
-- and a grant NAMES its metric evidence; no agent raises its own tier. So a heuristic classification is
-- only 'provisional'; it becomes 'granted' autonomy only through a recorded human sign-off.
--
-- Also the enumerable fleet roster (the prerequisite the Supervisor needs to route Phase-2 work): the
-- fleet lives in 3 divergent places (agents.py catalog / 37 systemd timers / cron), and agents.py names
-- only 7 of the 37 timers — 30 running agents are invisible to it. This table reconciles all three from
-- runtime ground truth (see scripts/fleet_registry.py). One row per agent: identity, tier(+grant), owner,
-- heartbeat source. A supervisor cannot supervise what it cannot enumerate.
BEGIN;

CREATE TABLE IF NOT EXISTS agent_registry (
  agent_key          text PRIMARY KEY,        -- canonical name (timer stem / cron script / catalog key)
  display_name       text,
  role               text,                     -- from agents.py when matched
  -- ── A61 autonomy tier + its grant provenance ──
  tier               text NOT NULL DEFAULT 'unset'
                     CHECK (tier IN ('T0','T1','T2','T3','unset')),
  tier_status        text NOT NULL DEFAULT 'provisional'
                     CHECK (tier_status IN ('provisional','granted')),  -- granted ONLY via recorded sign-off
  tier_evidence      text,                     -- A61: a grant NAMES its metric evidence (NULL while provisional)
  tier_signed_off_by text,                     -- A61: human sign-off, recorded (NULL until ratified)
  tier_set_at        timestamptz,
  -- ── enumeration + routing ──
  fuel               text,                     -- det | local | api | human (agents.py)
  owner              text NOT NULL DEFAULT 'unassigned',       -- one of the 10 directive domains
  heartbeat_source   text NOT NULL DEFAULT 'none',             -- systemd:<unit> | cron:<script> | db:<table> | none
  systemd_unit       text,
  cadence            text,
  layer              text NOT NULL DEFAULT 'catalog-only'
                     CHECK (layer IN ('systemd','cron','cron-child','catalog-only')),
  supervised         boolean NOT NULL DEFAULT false,           -- A59: consequential work routes through work_orders
  state              text NOT NULL DEFAULT 'live'
                     CHECK (state IN ('live','dormant','planned','superseded')),
  note               text,
  seen_at            timestamptz,              -- last time the generator observed it in runtime ground truth
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_registry_tier  ON agent_registry (tier);
CREATE INDEX IF NOT EXISTS idx_agent_registry_owner ON agent_registry (owner);
CREATE INDEX IF NOT EXISTS idx_agent_registry_layer ON agent_registry (layer);

-- The A61 artifact at a glance: fleet by governance tier, and how many tiers are actually GRANTED
-- (signed-off) vs merely provisional (heuristic, awaiting ratification).
CREATE OR REPLACE VIEW v_fleet_by_tier AS
  SELECT tier,
         count(*)                                        AS agents,
         count(*) FILTER (WHERE tier_status='granted')   AS granted,
         count(*) FILTER (WHERE supervised)              AS supervised,
         count(*) FILTER (WHERE note LIKE 'RUNNING but not%') AS uncatalogued
    FROM agent_registry
   GROUP BY tier
   ORDER BY tier;

COMMIT;
