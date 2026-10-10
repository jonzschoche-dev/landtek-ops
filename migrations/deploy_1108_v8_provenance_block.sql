-- deploy_1108 — A42: flip the V8 provenance guard (deploy_769) from shadow 'log' to 'block'.
--
-- WHY. V8 shadowed since 2026-07-08 with exactly ONE finding, a true positive: doc 14902 (SB Mercedes
-- Res. 103-86), INSERTed 2026-09-20 05:42 UTC by an ad-hoc session with
-- model_used='gemini-3.6-flash + operator visual verification' and no extraction_runs row (the vision read
-- ran outside the pipeline in /tmp/ocr103.py). Shadow logged it; nothing stopped it; the A42 truth test
-- (test_provenance_earned_from_run) failed every deploy gate from then on.
--
-- Data fix (applied directly, 2026-10-10): doc 14902 model_used -> NULL; withdrawn value + reason recorded
-- in execution_metadata.a42_stamp_withdrawn; raw model output + pre-change row kept at
-- /root/landtek_backups/a42_doc14902_2026-10-10/. holes_findings 1550125 marked remediated. Not re-OCR'd:
-- reocr_gemini would replace the operator-corrected transcript, and no real run can back that text.
--
-- Write path fix (this file): with mode='block' the trigger RAISEs, so model_used can only be set when a
-- completed extraction_runs row (model set) already exists for the doc. Both repo writers already comply:
--   scripts/reocr_gemini.py      — INSERTs the extraction_runs row, then stamps, in one txn
--   scripts/case_corpus_sweep.sh — stamps only FROM the latest completed extraction_runs.model
-- A stamp on INSERT INTO documents is therefore always refused (no run can precede the doc's id).
-- Verified pre-flip in a rolled-back txn: unearned UPDATE -> RAISE; run-then-stamp -> OK. 86/86 live stamps
-- backed. Idempotent. Revert: UPDATE ontology_validator_config SET mode='log' WHERE check_code='V8';

UPDATE ontology_validator_config
   SET mode = 'block',
       note = 'provenance earned-from-run (A42): documents.model_used must trace to a completed extraction_runs row. BLOCK since deploy_1108 (2026-10-10).',
       updated_at = now()
 WHERE check_code = 'V8' AND mode <> 'block';
