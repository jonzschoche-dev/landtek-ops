-- Truth-Layer Fitness — the actionable weakness queue (the "diagnose/prioritize" output the remediation
-- loop consumes). Read-only derivation over the append-only ledger: the LATEST measurement per
-- (object, dimension, submeasure) that carries a named remediation target. Additive, idempotent.
BEGIN;

CREATE OR REPLACE VIEW v_fitness_gaps AS
WITH latest AS (
  SELECT DISTINCT ON (m.object_pk, m.dimension, m.submeasure)
         m.object_pk, m.dimension, m.submeasure, m.value, m.weakness_target, m.prev_value, m.cycle_at
    FROM fitness_measurement m
   ORDER BY m.object_pk, m.dimension, m.submeasure, m.id DESC)
SELECT o.domain, o.object_type, o.object_id, o.client_code,
       l.dimension, l.submeasure, l.value,
       l.weakness_target->>'action' AS remediation,
       l.weakness_target->>'what'   AS target,
       (l.prev_value IS NOT NULL AND l.prev_value <> l.value) AS regressed,
       l.cycle_at
  FROM latest l
  JOIN fitness_object o ON o.id = l.object_pk
 WHERE l.weakness_target IS NOT NULL;

GRANT SELECT ON v_fitness_gaps TO tlfh_harness;

COMMIT;
