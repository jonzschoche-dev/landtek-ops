-- Drip Charter adopted by Jonathan, 20 Oct 2026 (case_work/MWK-001/DRIP_CHARTER.md).
-- Charter amendments are logged in drip_feedback with scope 'charter'. Additive and idempotent.
BEGIN;
ALTER TABLE drip_feedback DROP CONSTRAINT IF EXISTS drip_feedback_scope_check;
ALTER TABLE drip_feedback ADD CONSTRAINT drip_feedback_scope_check
  CHECK (scope = ANY (ARRAY['charter','global','office','ladder','instrument']));
COMMIT;
