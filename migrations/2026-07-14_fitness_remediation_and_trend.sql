-- Truth-Layer Fitness — remediation candidate lane + trend view. Additive, idempotent.
-- The candidate lane is a DEDICATED shadow table (not proposed_facts / matter_facts), so a shadow
-- remediation can NEVER touch a fact or a governed lane. A human/governed step promotes candidates onward.
BEGIN;

CREATE TABLE IF NOT EXISTS fitness_remediation_candidate (
  id              BIGSERIAL PRIMARY KEY,
  object_pk       BIGINT REFERENCES fitness_object(id),
  domain          TEXT, object_type TEXT, object_id TEXT, client_code TEXT,
  dimension       TEXT, submeasure TEXT, remediation TEXT,
  target          JSONB,
  proposed_action TEXT,                       -- the human-readable, matched remediation (never executed here)
  status          TEXT NOT NULL DEFAULT 'candidate',   -- candidate -> (human) approved/rejected/promoted
  created_by      TEXT DEFAULT 'truth_layer_fitness',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (object_pk, dimension, submeasure)   -- one open candidate per weakness (idempotent)
);
GRANT INSERT, SELECT ON fitness_remediation_candidate TO tlfh_harness;
GRANT USAGE, SELECT ON SEQUENCE fitness_remediation_candidate_id_seq TO tlfh_harness;

-- cycle-over-cycle grounding coverage + open-target count (the "recalc / is it getting better" signal)
CREATE OR REPLACE VIEW v_fitness_trend AS
SELECT c.id AS cycle_id, c.domain, c.cohort, c.cycle_at, c.n_objects,
       count(*) FILTER (WHERE m.dimension='grounding' AND m.submeasure='grounded' AND m.value='True') AS grounded,
       count(*) FILTER (WHERE m.dimension='grounding' AND m.submeasure='grounded')                    AS grounded_total,
       count(*) FILTER (WHERE m.weakness_target IS NOT NULL)                                          AS open_targets
  FROM fitness_cycle c
  LEFT JOIN fitness_measurement m ON m.cycle_id = c.id
 GROUP BY c.id, c.domain, c.cohort, c.cycle_at, c.n_objects
 ORDER BY c.id;
GRANT SELECT ON v_fitness_trend TO tlfh_harness;

COMMIT;
