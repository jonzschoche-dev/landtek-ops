-- deploy_711_validator_enforce.sql — flip ontology_validator from SHADOW to ENFORCE.
-- Audit (2026-07-06): V1/V3 logged ZERO violations across the shadow period and 0 verified
-- matter_facts are ungrounded right now → false-positive risk ~0. Verified live: V1 blocks
-- drift-table writes, V3 blocks ungrounded verified facts, grounded writes still pass (and the
-- pre-existing enforce_provenance_facts() verbatim gate is even stricter — two layers now).
-- V4 stays 'log' (client-isolation detector) — enforcing it needs the A5 FK-hardening, not a flip.
-- Idempotent.

UPDATE ontology_validator_config SET mode='block', updated_at=now() WHERE check_code IN ('V1','V3');
UPDATE ontology_validator_config SET mode='log',   updated_at=now() WHERE check_code = 'V4';
