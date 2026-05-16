#!/usr/bin/env python3
"""Deploy 034b — close the remaining surfaces.

1. Patch Log Leo Interaction node — provide non-empty fallback for `question`
   so file uploads (which have no rawText) stop failing with HTTP 400.
2. Clean up documents id 618 + 619 — strip trailing `}}`, mark status, leave
   drive_file_id empty (file bytes unrecoverable; recorded for audit).
3. Mark all 121 in-flight executions as canceled (they were killed by restarts
   during this session — leaving them as finished=false is misleading).

No new schema. Only JSON patch + targeted UPDATE + targeted UPDATE on execution_entity.
"""
import json
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")

NEW_JSONBODY = """={{ {
  "channel": "telegram",
  "sender_id": $('Context Builder').first().json.senderId,
  "sender_name": $('Context Builder').first().json.senderName,
  "question": ($('Context Builder').first().json.rawText || '[file upload, no caption]'),
  "case_file": $('Parse Agent1').first().json.case_file,
  "response_json": $('Parse Agent1').first().json,
  "reply_text": $('Parse Agent1').first().json.telegram_reply_to_client,
  "execution_id": $execution.id
} }}"""


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()

    # ── 1. Patch Log Leo Interaction node ───────────────────────────────────
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes = cur.fetchone()

    patched = False
    for n in nodes:
        if n.get("name") == "Log Leo Interaction":
            n["parameters"]["jsonBody"] = NEW_JSONBODY
            patched = True
            print(" - Log Leo Interaction: jsonBody patched with rawText fallback")

    if not patched:
        print("WARN: Log Leo Interaction node not found")
    else:
        cur.execute("""
            UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s
        """, (json.dumps(nodes), wf_id))

    # ── 2. Clean up documents 618 + 619 ─────────────────────────────────────
    cur.execute("""
        UPDATE documents
           SET case_file = 'MWK-001',
               original_filename = trim(replace(original_filename, '}}', '')),
               drive_link = NULL,
               mime_type = 'application/pdf',
               status = 'broken_ingest_no_drive',
               analyst_memo = jsonb_build_object(
                   'cleanup_deploy', '034b',
                   'cleanup_at', now()::text,
                   'reason', 'Pre-deploy-032 template corruption; file bytes never reached Drive; metadata back-filled from conversation context (Don Qi Style SPA upload, MWK-001).'
               )
         WHERE id IN (618, 619)
        RETURNING id, case_file, original_filename, drive_file_id, status;
    """)
    print("\n - documents 618/619 cleaned:")
    for row in cur.fetchall():
        print(f"     id={row[0]}  case_file={row[1]!r}  fn={row[2]!r}  drive_id={row[3]!r}  status={row[4]!r}")

    # ── 3. Mark 121 in-flight executions as canceled ────────────────────────
    cur.execute("""
        UPDATE execution_entity
           SET status='canceled',
               finished=true,
               "stoppedAt" = COALESCE("stoppedAt", "startedAt")
         WHERE finished=false
        RETURNING id;
    """)
    canceled = cur.fetchall()
    print(f"\n - {len(canceled)} in-flight executions marked canceled")

    conn.commit()
    print(f"\nworkflow_entity row updated (id={wf_id})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
