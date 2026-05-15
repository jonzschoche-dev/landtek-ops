-- Workflow Tripwire — detect external overwrites of Leos Workflow.
--
-- Adds:
--   1. workflow_audit table — records each UPDATE to workflow_entity (any workflow)
--      with a structural fingerprint (prompt length, key clauses present, node
--      counts on critical Insert nodes, total nodes JSON size).
--   2. AFTER UPDATE trigger workflow_entity_audit_t — populates workflow_audit
--      on every change. Captures session info (application_name, pid) for
--      best-effort attribution of who/what made the change.
--   3. workflow_health view — quick "is everything still in place" check.
--   4. RAISE WARNING (visible in Postgres log) when a critical patch regresses
--      between consecutive UPDATEs.
--
-- No new logic in n8n. Pure DB-side. Read-only path for normal operation.

BEGIN;

CREATE TABLE IF NOT EXISTS workflow_audit (
    id                          SERIAL PRIMARY KEY,
    workflow_id                 VARCHAR,
    workflow_name               VARCHAR,
    changed_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    nodes_size_bytes            INT,
    node_count                  INT,
    ai_agent_prompt_len         INT,
    has_rule_a                  BOOLEAN,
    has_rule_b                  BOOLEAN,
    has_strict_isolation        BOOLEAN,
    has_jonathan_clause         BOOLEAN,
    log_file_receipt_clean      BOOLEAN,
    log_file_has_drive_id       BOOLEAN,
    upload_file_has_fallback    BOOLEAN,
    insert_chat_note_cols       INT,
    insert_cal_event_cols       INT,
    log_conversation_has_raw    BOOLEAN,
    log_leo_int_has_fallback    BOOLEAN,
    change_pid                  INT,
    change_application_name     TEXT,
    change_client_addr          INET
);

CREATE INDEX IF NOT EXISTS idx_workflow_audit_changed_at ON workflow_audit(changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_audit_name ON workflow_audit(workflow_name, changed_at DESC);


CREATE OR REPLACE FUNCTION workflow_entity_audit_trigger()
RETURNS TRIGGER AS $$
DECLARE
    n          jsonb;
    ai_sm      text;
    ai_len     int := 0;
    has_a      boolean := false;
    has_b      boolean := false;
    has_iso    boolean := false;
    has_jon    boolean := false;
    lfr_clean  boolean := false;
    lfr_drvid  boolean := false;
    ulf_fb     boolean := false;
    icn_cols   int := 0;
    ice_cols   int := 0;
    lc_raw     boolean := false;
    lli_fb     boolean := false;
    nodes_arr  jsonb;
    prev_row   workflow_audit%ROWTYPE;
BEGIN
    nodes_arr := NEW.nodes::jsonb;

    FOR n IN SELECT * FROM jsonb_array_elements(nodes_arr) LOOP
        CASE n->>'name'
            WHEN 'AI Agent' THEN
                ai_sm := n->'parameters'->'options'->>'systemMessage';
                ai_len := coalesce(length(ai_sm), 0);
                has_a   := ai_sm ~ 'Rule A — non-negotiable';
                has_b   := ai_sm ~ 'PROACTIVE INVESTIGATION';
                has_iso := ai_sm ~ 'STRICT CLIENT ISOLATION';
                has_jon := ai_sm ~ 'Never assume or leak information from Jonathan';
            WHEN 'Log File Receipt1' THEN
                lfr_clean := (n->'parameters'->'columns'->'value'->>'case_file') !~ '\}\} \}\}';
                lfr_drvid := (n->'parameters'->'columns'->'value' ? 'drive_file_id');
            WHEN 'Upload file' THEN
                ulf_fb := (n->'parameters'->>'name') ~ 'smart_filename'
                          AND (n->'parameters'->>'name') ~ 'untitled';
            WHEN 'Insert Chat Note' THEN
                SELECT count(*)::int INTO icn_cols
                  FROM jsonb_object_keys(n->'parameters'->'columns'->'value');
            WHEN 'Insert Calendar Event' THEN
                SELECT count(*)::int INTO ice_cols
                  FROM jsonb_object_keys(n->'parameters'->'columns'->'value');
            WHEN 'Log Conversation' THEN
                lc_raw := (n->'parameters'->'columns'->'value' ? 'raw_llm_output');
            WHEN 'Log Leo Interaction' THEN
                lli_fb := (n->'parameters'->>'jsonBody') ~ 'file upload, no caption';
            ELSE
                NULL;
        END CASE;
    END LOOP;

    INSERT INTO workflow_audit (
        workflow_id, workflow_name, nodes_size_bytes, node_count,
        ai_agent_prompt_len, has_rule_a, has_rule_b, has_strict_isolation, has_jonathan_clause,
        log_file_receipt_clean, log_file_has_drive_id, upload_file_has_fallback,
        insert_chat_note_cols, insert_cal_event_cols,
        log_conversation_has_raw, log_leo_int_has_fallback,
        change_pid, change_application_name, change_client_addr
    ) VALUES (
        NEW.id, NEW.name, length(NEW.nodes::text), jsonb_array_length(nodes_arr),
        ai_len, has_a, has_b, has_iso, has_jon,
        lfr_clean, lfr_drvid, ulf_fb,
        icn_cols, ice_cols,
        lc_raw, lli_fb,
        pg_backend_pid(),
        current_setting('application_name', true),
        inet_client_addr()
    );

    -- Compare to previous audit for this workflow and warn on regressions
    SELECT * INTO prev_row
      FROM workflow_audit
     WHERE workflow_id = NEW.id AND id < currval('workflow_audit_id_seq')
     ORDER BY id DESC LIMIT 1;

    IF FOUND AND NEW.name = 'Leos Workflow' THEN
        IF prev_row.ai_agent_prompt_len > ai_len + 500 THEN
            RAISE WARNING 'WORKFLOW REGRESSION: AI Agent prompt shrunk from % to % chars (delta %)',
                prev_row.ai_agent_prompt_len, ai_len, ai_len - prev_row.ai_agent_prompt_len;
        END IF;
        IF prev_row.has_rule_a AND NOT has_a THEN
            RAISE WARNING 'WORKFLOW REGRESSION: Rule A vanished from AI Agent prompt';
        END IF;
        IF prev_row.has_strict_isolation AND NOT has_iso THEN
            RAISE WARNING 'WORKFLOW REGRESSION: STRICT CLIENT ISOLATION vanished';
        END IF;
        IF prev_row.has_jonathan_clause AND NOT has_jon THEN
            RAISE WARNING 'WORKFLOW REGRESSION: Jonathan-leakage clause vanished';
        END IF;
        IF prev_row.log_file_receipt_clean AND NOT lfr_clean THEN
            RAISE WARNING 'WORKFLOW REGRESSION: Log File Receipt1 template bug returned';
        END IF;
        IF prev_row.insert_chat_note_cols > icn_cols + 3 THEN
            RAISE WARNING 'WORKFLOW REGRESSION: Insert Chat Note column count dropped from % to %',
                prev_row.insert_chat_note_cols, icn_cols;
        END IF;
        IF prev_row.log_conversation_has_raw AND NOT lc_raw THEN
            RAISE WARNING 'WORKFLOW REGRESSION: Log Conversation raw_llm_output mapping vanished';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS workflow_entity_audit_t ON workflow_entity;
CREATE TRIGGER workflow_entity_audit_t
AFTER UPDATE ON workflow_entity
FOR EACH ROW
WHEN (OLD.nodes::text IS DISTINCT FROM NEW.nodes::text)
EXECUTE FUNCTION workflow_entity_audit_trigger();


CREATE OR REPLACE VIEW workflow_health AS
SELECT
    workflow_name,
    changed_at,
    EXTRACT(EPOCH FROM (now() - changed_at))::int AS sec_ago,
    nodes_size_bytes,
    node_count,
    ai_agent_prompt_len AS prompt_len,
    has_rule_a, has_rule_b, has_strict_isolation, has_jonathan_clause,
    log_file_receipt_clean AS lfr_clean,
    log_file_has_drive_id  AS lfr_drvid,
    upload_file_has_fallback AS upl_fb,
    insert_chat_note_cols AS icn,
    insert_cal_event_cols AS ice,
    log_conversation_has_raw AS lc_raw,
    log_leo_int_has_fallback AS lli_fb,
    change_application_name AS source,
    CASE
        WHEN NOT (has_rule_a AND has_rule_b AND has_strict_isolation
                  AND has_jonathan_clause AND log_file_receipt_clean
                  AND log_file_has_drive_id AND upload_file_has_fallback
                  AND log_conversation_has_raw AND log_leo_int_has_fallback
                  AND insert_chat_note_cols >= 8
                  AND insert_cal_event_cols >= 8)
        THEN 'DEGRADED'
        ELSE 'OK'
    END AS overall_status
  FROM workflow_audit
 WHERE id IN (SELECT max(id) FROM workflow_audit GROUP BY workflow_name)
 ORDER BY workflow_name;


-- Backfill a baseline row for the current state of every existing workflow
INSERT INTO workflow_audit (workflow_id, workflow_name, nodes_size_bytes, node_count,
    ai_agent_prompt_len, has_rule_a, has_rule_b, has_strict_isolation, has_jonathan_clause,
    log_file_receipt_clean, log_file_has_drive_id, upload_file_has_fallback,
    insert_chat_note_cols, insert_cal_event_cols,
    log_conversation_has_raw, log_leo_int_has_fallback,
    change_pid, change_application_name)
SELECT
    we.id,
    we.name,
    length(we.nodes::text),
    jsonb_array_length(we.nodes::jsonb),
    coalesce(length((SELECT n->'parameters'->'options'->>'systemMessage'
                       FROM jsonb_array_elements(we.nodes::jsonb) n
                      WHERE n->>'name'='AI Agent')), 0),
    EXISTS(SELECT 1 FROM jsonb_array_elements(we.nodes::jsonb) n
            WHERE n->>'name'='AI Agent'
              AND (n->'parameters'->'options'->>'systemMessage') ~ 'Rule A — non-negotiable'),
    EXISTS(SELECT 1 FROM jsonb_array_elements(we.nodes::jsonb) n
            WHERE n->>'name'='AI Agent'
              AND (n->'parameters'->'options'->>'systemMessage') ~ 'PROACTIVE INVESTIGATION'),
    EXISTS(SELECT 1 FROM jsonb_array_elements(we.nodes::jsonb) n
            WHERE n->>'name'='AI Agent'
              AND (n->'parameters'->'options'->>'systemMessage') ~ 'STRICT CLIENT ISOLATION'),
    EXISTS(SELECT 1 FROM jsonb_array_elements(we.nodes::jsonb) n
            WHERE n->>'name'='AI Agent'
              AND (n->'parameters'->'options'->>'systemMessage') ~ 'Never assume or leak information from Jonathan'),
    EXISTS(SELECT 1 FROM jsonb_array_elements(we.nodes::jsonb) n
            WHERE n->>'name'='Log File Receipt1'
              AND (n->'parameters'->'columns'->'value'->>'case_file') !~ '\}\} \}\}'),
    EXISTS(SELECT 1 FROM jsonb_array_elements(we.nodes::jsonb) n
            WHERE n->>'name'='Log File Receipt1'
              AND (n->'parameters'->'columns'->'value' ? 'drive_file_id')),
    EXISTS(SELECT 1 FROM jsonb_array_elements(we.nodes::jsonb) n
            WHERE n->>'name'='Upload file'
              AND (n->'parameters'->>'name') ~ 'untitled'),
    coalesce((SELECT count(*)::int FROM jsonb_array_elements(we.nodes::jsonb) n,
                                   jsonb_object_keys(n->'parameters'->'columns'->'value')
              WHERE n->>'name'='Insert Chat Note'), 0),
    coalesce((SELECT count(*)::int FROM jsonb_array_elements(we.nodes::jsonb) n,
                                   jsonb_object_keys(n->'parameters'->'columns'->'value')
              WHERE n->>'name'='Insert Calendar Event'), 0),
    EXISTS(SELECT 1 FROM jsonb_array_elements(we.nodes::jsonb) n
            WHERE n->>'name'='Log Conversation'
              AND (n->'parameters'->'columns'->'value' ? 'raw_llm_output')),
    EXISTS(SELECT 1 FROM jsonb_array_elements(we.nodes::jsonb) n
            WHERE n->>'name'='Log Leo Interaction'
              AND (n->'parameters'->>'jsonBody') ~ 'file upload, no caption'),
    pg_backend_pid(),
    'tripwire_baseline_backfill'
  FROM workflow_entity we;

COMMIT;
