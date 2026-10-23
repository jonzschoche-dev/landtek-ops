-- drip_ui MVP tables (2026-10-23)
CREATE TABLE IF NOT EXISTS drip_ui_upload(
 id bigserial PRIMARY KEY, filename text NOT NULL, path text NOT NULL, mime text, size_bytes bigint,
 sha256 text, extracted_text text, uploaded_by text DEFAULT 'jonathan', created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS drip_ui_message(
 id bigserial PRIMARY KEY, role text NOT NULL, content text, upload_ids bigint[], meta jsonb, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS drip_ui_draft(
 id bigserial PRIMARY KEY, obligation_id bigint, to_addr text, cc text, subject text, body text,
 rationale text, state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','go','edit','hold')),
 decided_at timestamptz, decision_note text, created_at timestamptz DEFAULT now());
