-- APPLIED 2026-10-20 on Jonathan's go (chat): dry-run then commit on the VPS; drip_event 1292.
-- DRAFT DELTA (NOT APPLIED) — the SLEEP DOCTRINE as hard gates (Jonathan, 20 Oct 2026), on top of the LIVE drip v2
-- fabric (drip_v2_fabric_REVISED_2026-10-20.sql). Spec: agent_specs/005_drip.md "THE SLEEP DOCTRINE". Additive.
-- Dry run:  (sed '$d' this_file; echo ROLLBACK;) | docker exec -i n8n-postgres-1 psql -U n8n -d n8n -v ON_ERROR_STOP=1
BEGIN;

-- The cost line leaves the routine plane: first stated (as sworn neutral fact) at R2, never at ask/edition/R1
UPDATE drip_style_register SET burden_line_from_rung = 2, updated_at = now()
 WHERE audience IN ('official','supervisor') AND coalesce(burden_line_from_rung, 99) < 2;

-- Allow the new lint class (the live CHECK enumerates classes)
DO $$
DECLARE c text;
BEGIN
  SELECT conname INTO c FROM pg_constraint
   WHERE conrelid = 'drip_lint_rule'::regclass AND contype = 'c' AND pg_get_constraintdef(oid) ILIKE '%rule_class%';
  IF c IS NOT NULL AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = c AND pg_get_constraintdef(oid) ILIKE '%strategic_tell%') THEN
    EXECUTE format('ALTER TABLE drip_lint_rule DROP CONSTRAINT %I', c);
    ALTER TABLE drip_lint_rule ADD CONSTRAINT drip_lint_rule_class_check CHECK (rule_class IN (
      'instigation','threat_early','characterization','untagged_inference','untraceable_fact','multi_duty','multi_officer',
      'markup','length','missing_easy_yes','missing_gracious_close','cold_tone','internal_goal_leak','unpleadable_amount',
      'state_of_mind_sworn','image_signature_enotary','strategic_tell','routine_too_long','supervisor_cc_early',
      'adverse_annex_early'));
  END IF;
END $$;

INSERT INTO drip_lint_rule (rule_class, pattern, audiences, max_rung, action, rationale) VALUES
 ('strategic_tell', '₱|\mPHP\M|\mpesos?\M', '{official,supervisor,phone_drip}', 1, 'refuse', 'Sleep doctrine: no peso amounts or rates in routine drips; the cost is logged internally (loss_line) and first stated at R2'),
 ('strategic_tell', '\m(without prejudice|reserv\w*|accru\w*|compensation|occup\w*|demand\w*|liabilit\w*|damages|remed(y|ies)|unlawful\w*|illegal\w*|registered owner)\M', '{official,supervisor,phone_drip}', 1, 'refuse', 'Sleep doctrine: legal-posture words wake the office and its lawyer; routine drips ask, they do not position'),
 ('strategic_tell', '\m(R\.A\.|Republic Act|Civil Code|Local Government Code|P\.D\.|Presidential Decree)\M', '{official,supervisor,phone_drip}', 1, 'refuse', 'Sleep doctrine: no statute citations in routine drips (the reply period is stated plainly)'),
 ('strategic_tell', '\m(ARTA|CSC|Civil Service Commission|Ombudsman|court|tribunal|sanction\w*|file (a|an) (case|complaint))\M', '{official,supervisor,phone_drip}', 1, 'refuse', 'Sleep doctrine: no forum named in routine drips'),
 ('routine_too_long', NULL, '{official,supervisor,phone_drip}', 1, 'refuse', 'Sleep doctrine: a routine drip is ≤ ~250 words and one page; checked in code'),
 ('supervisor_cc_early', NULL, '{official}', 1, 'refuse', 'Sleep doctrine: no copy-furnished to supervisors or other offices before R1; checked in code'),
 ('adverse_annex_early', NULL, '{official,supervisor}', 1, 'refuse', 'Sleep doctrine: routine drips annex only the authority (SPA); comparators, the office''s own declarations and admissions wait for later rungs; checked in code against annex_manifest')
ON CONFLICT (rule_class, pattern) DO NOTHING;

COMMIT;
