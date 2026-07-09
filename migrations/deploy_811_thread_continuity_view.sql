-- deploy_811_thread_continuity_view.sql — v_thread_continuity (COMPOSITION_MODEL_DRAFT §2.3, approved).
-- Read-only. From ANY email-linked document, surface the WHOLE gmail conversation in time order:
-- every sibling document (bodies + attachments) across every message of the same thread.
-- Distinct from case_threads (curated litigation narratives) — this is the RAW conversation spine.
-- Rollback: DROP VIEW v_thread_continuity.

CREATE OR REPLACE VIEW v_thread_continuity AS
SELECT e.doc_id,
       g.thread_id,
       g2.received_at   AS sibling_received_at,
       g2.sent_at       AS sibling_sent_at,
       g2.subject       AS sibling_subject,
       g2.from_addr     AS sibling_from,
       g2.message_id    AS sibling_message_id,
       e2.doc_id        AS sibling_doc_id,
       e2.role          AS sibling_role,
       e2.filename      AS sibling_filename
  FROM email_documents e
  JOIN gmail_messages g  ON g.message_id  = e.message_id
  JOIN gmail_messages g2 ON g2.thread_id  = g.thread_id
  JOIN email_documents e2 ON e2.message_id = g2.message_id;

COMMENT ON VIEW v_thread_continuity IS
  'Continuity read-path (deploy_811): doc_id → its gmail thread → ALL sibling docs (role body|attachment) in time order. Raw conversation spine; curated narratives live in case_threads.';
