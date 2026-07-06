-- deploy_712_work_order_target.sql — a work order can point at a specific target (e.g. a document).
-- Needed so ocr_remediation orders carry the doc_id the connect-verify gate checks. Generic ref
-- ('doc:233', 'gap:transfer:36:req:1', ...). Idempotent.

ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS target_ref text;
