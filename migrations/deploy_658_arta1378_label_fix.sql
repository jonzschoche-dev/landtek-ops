-- deploy_655_arta1378_label_fix.sql
-- =====================================================================================
-- FIX: MWK-ARTA-1378 surfaced_deadlines data-corruption defect (truth-qa gate catch).
--
-- SYMPTOM (client-facing surface): 1378's freshest surfaced_deadlines row rendered a
-- garbled, truncated, internal-shorthand label to the client and mis-bucketed the matter
-- as OVERDUE:
--     as_of 2026-07-01 | due 2026-06-07 | OVERDUE
--     label = "s docs from other matters. || PERJURY POINT (2026-06-07): Respondent s"
--
-- ROOT CAUSE (two defects, both in scripts/deadlines.py prose-harvest):
--   (A) PHANTOM DATE / STALE OVERDUE. The engine's FORWARD_RE matched the substring
--       "respond" inside the NOUN "Respondent" (opposing party) — an unbounded pattern.
--       That made the historical case-history date "PERJURY POINT (2026-06-07)" in
--       matters.stage_notes look like a forward "respond" obligation, and its ±45-char
--       window carried no PAST marker, so a narrative edit-stamp date got promoted into a
--       phantom forward OVERDUE. 1378's TRUE posture is submitted-for-resolution
--       (NSR recv 2026-06-04), next_deadline 2026-09-03 (decision window ~early Sept).
--       Same class of bug as the CV-26360 phantom (deploy_647).
--   (B) GARBLED LABEL. The harvested label was a raw ±45-char mid-sentence window:
--       it began lowercase mid-word ("s docs...") and contained the internal "||" segment
--       separator used inside stage_notes to fence case-history blocks. Never presentable.
--
-- ENGINE FIX (scripts/deadlines.py, shipped alongside this migration):
--   * FORWARD_RE: `respond` -> `\brespond\b` (the noun "Respondent" no longer matches).
--   * PAST_RE: add narrative/editorial markers (perjury|swore|sworn|non-receipt|correction|
--     admission|defaulted|contaminated) so case-history prose is classed TIMELINE, not a
--     forward deadline.
--   * New _clean_label(): a surfaced label may never carry the "||" internal separator or
--     start lowercase mid-word; repair by dropping everything from the first "||", aligning
--     to a sentence boundary, else falling back to the matter's clean stage token.
--
-- This migration is the DATA half: it purges the already-persisted phantom/garbled rows
-- from surfaced_deadlines. The as_of 2026-07-01 rows were already re-derived cleanly by a
-- `deadlines.py --write` run with the patched engine (1378 now surfaces its single honest
-- UPCOMING row: due 2026-09-03, label respondent_counter_affidavit_filed_submitted_for_resolution).
-- Historical snapshots (as_of 2026-06-30, 2026-06-20) still carry the corrupt row; delete them.
--
-- SCOPE GUARD: touches ONLY surfaced_deadlines. Does NOT touch matters, client_access.py,
-- client_portal.py, the CV-26360 operator-attested 2026-08-12 row, or any other matter.
-- Client/matter separation preserved (MWK-ARTA-1378 only).
-- =====================================================================================

BEGIN;

-- (A) Delete the phantom OVERDUE / garbled-label rows: any 1378 row whose label carries the
-- internal "||" separator. These are the deploy-642-class prose fragments; the honest posture
-- for those snapshot dates was also submitted-for-resolution (a NULL forward obligation on the
-- historical date), so the correct action is removal, not relabel.
DELETE FROM surfaced_deadlines
 WHERE matter_code = 'MWK-ARTA-1378'
   AND label LIKE '%||%';

-- (B) Belt-and-suspenders: no surfaced label anywhere may carry the "||" internal separator.
-- (Should be a no-op after (A); guards against any other matter leaking the same fragment.)
DELETE FROM surfaced_deadlines
 WHERE label LIKE '%||%';

-- VERIFY (run after commit):
--   SELECT as_of, due_date, bucket, label FROM surfaced_deadlines
--    WHERE matter_code='MWK-ARTA-1378' ORDER BY as_of DESC, due_date;
--   -- expect: only clean rows, due 2026-09-03 / UPCOMING /
--   --         respondent_counter_affidavit_filed_submitted_for_resolution
--   SELECT count(*) FROM surfaced_deadlines WHERE label LIKE '%||%';   -- expect 0

COMMIT;
