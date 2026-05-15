#!/usr/bin/env python3
"""Insert one documents row per attachment in /root/landtek/case_files/MWK-001/civil_26-360_attachments/.

Reads gmail_messages.attachment_refs to know which files exist, computes content hashes,
inserts with case_file='MWK-001', processing_mode='lean', status='ingested'. Idempotent
by (case_file, content_hash) — re-running won't duplicate.
"""
import os, sys, json, hashlib, psycopg2
from psycopg2.extras import Json

PG = 'postgresql://n8n:n8npassword@172.18.0.3:5432/n8n'

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    conn = psycopg2.connect(PG); cur = conn.cursor()
    cur.execute("""SELECT id, message_id, subject, sent_at, attachment_refs
                     FROM gmail_messages
                    WHERE attachment_refs IS NOT NULL
                      AND jsonb_array_length(attachment_refs) > 0
                    ORDER BY id""")
    rows = cur.fetchall()
    inserted, skipped_dup, missing_file = 0, 0, 0

    for gm_id, msg_id, subj, sent_at, refs in rows:
        if isinstance(refs, str): refs = json.loads(refs)
        for r in refs:
            local_path = r.get('local_path')
            if not local_path or not os.path.exists(local_path):
                print(f'  msg {gm_id}: missing {local_path}')
                missing_file += 1
                continue
            content_hash = sha256_file(local_path)
            cur.execute("""SELECT id FROM documents
                            WHERE case_file='MWK-001' AND content_hash=%s LIMIT 1""",
                        (content_hash,))
            existing = cur.fetchone()
            if existing:
                skipped_dup += 1
                continue

            mime = r.get('mime_type') or 'application/octet-stream'
            fn = r.get('filename') or os.path.basename(local_path)
            cur.execute("""INSERT INTO documents
                              (case_file, original_filename, smart_filename, mime_type,
                               status, processing_mode, content_hash, analyst_memo,
                               first_seen_at, last_seen_at)
                           VALUES ('MWK-001', %s, %s, %s, 'ingested', 'lean', %s, %s,
                                    NOW(), NOW())
                           RETURNING id""",
                        (fn, os.path.basename(local_path), mime, content_hash,
                         Json({'source': 'gmail_attachment',
                               'gmail_message_db_id': gm_id,
                               'gmail_message_id': msg_id,
                               'gmail_subject': subj,
                               'local_path': local_path,
                               'attachment_id': r.get('attachment_id'),
                               'size_bytes': r.get('size_bytes'),
                               'inline': r.get('inline', False)})))
            new_id = cur.fetchone()[0]
            inserted += 1
        conn.commit()

    # Backfill gmail_messages.document_id where exactly one attachment exists per email
    cur.execute("""WITH single_att AS (
                     SELECT gm.id AS gm_id,
                            (gm.attachment_refs->0->>'local_path') AS lp
                       FROM gmail_messages gm
                      WHERE jsonb_array_length(COALESCE(gm.attachment_refs,'[]'::jsonb)) = 1
                        AND gm.document_id IS NULL
                   )
                   UPDATE gmail_messages g
                      SET document_id = d.id
                     FROM single_att s
                     JOIN documents d ON d.case_file='MWK-001'
                                       AND d.analyst_memo->>'local_path' = s.lp
                    WHERE g.id = s.gm_id
                   RETURNING g.id, d.id""")
    linked = cur.fetchall()
    conn.commit()

    print(f'\nDONE: inserted={inserted} skipped_dupes={skipped_dup} missing_files={missing_file}')
    print(f'      backfilled gmail_messages.document_id on {len(linked)} single-attachment emails')
    cur.close(); conn.close()

if __name__ == '__main__':
    main()
