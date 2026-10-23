-- drip_ui_wiring_2026-10-23.sql — the Drip UI joins the drip core (Jonathan, 23 Oct 2026: "wire the Drip UI:
-- queue from ladder status + next targets, drafts through the gate and cadence, Go makes a Gmail draft").
-- Additive and idempotent. drip_ui_draft is the fifth core table: drafts awaiting Jonathan.
ALTER TABLE drip_ui_draft ADD COLUMN IF NOT EXISTS ladder text;          -- every draft belongs to a ladder
ALTER TABLE drip_ui_draft ADD COLUMN IF NOT EXISTS gate jsonb;           -- scripts/drip_gate.py result at creation / Go
ALTER TABLE drip_ui_draft ADD COLUMN IF NOT EXISTS gmail_draft_id text;  -- set when Go stages it in Gmail Drafts
ALTER TABLE drip_ui_draft ADD COLUMN IF NOT EXISTS account text;         -- the Gmail account it was staged in
ALTER TABLE drip_ui_draft ADD COLUMN IF NOT EXISTS staged_at timestamptz;
