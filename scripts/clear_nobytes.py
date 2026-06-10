#!/usr/bin/env python3
"""clear_nobytes.py — give the OCR backfill a finish line.

The daemon can only OCR docs whose bytes it can fetch. Some OCR-target docs
(canonical, no text) have a dead file_path and no Drive copy — they'd grind
forever as 'no local bytes'. This finds them and either:
  - recovers the bytes from the source email attachment (same-size safe), or
  - quarantines the genuinely-gone ones (ingest_status='quarantined_nobytes')
so READ can actually reach zero instead of staying red on unrecoverable rows.
Deterministic, no Gemini quota used.
"""
import os, sys, base64, hashlib
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek")
sys.path.insert(0, "/root/landtek/scripts")
import blend_emails as be
from gmail_watcher import gmail_client

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn = psycopg2.connect(DSN); conn.autocommit = True
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""SELECT id, file_path, drive_file_id, original_filename, mime_type
  FROM documents WHERE master_form='digital'
   AND coalesce(ingest_status,'') NOT IN ('quarantined_dup','quarantined_ghost','quarantined_nobytes')
   AND coalesce(length(extracted_text),0) < 50""")
rows = cur.fetchall()

svc = None
ocrable = recovered = merged = 0
quarantined = []
for r in rows:
    fp = r["file_path"]
    if (fp and os.path.exists(fp)) or r["drive_file_id"]:
        ocrable += 1
        continue
    fn = r["original_filename"]
    handled = False
    if fn:
        cur.execute("""SELECT g.message_id, a AS ref, (a->>'size') sz
            FROM gmail_messages g, jsonb_array_elements(g.attachment_refs) a
            WHERE g.has_attachments AND lower(a->>'filename')=lower(%s)
              AND a->>'attachmentId' IS NOT NULL
            ORDER BY coalesce(g.sent_at,g.received_at) DESC NULLS LAST""", (fn,))
        matches = cur.fetchall()
        if matches and len({m["sz"] for m in matches}) == 1:
            if svc is None:
                svc = gmail_client()
            m = matches[0]; ref = m["ref"]; mime = ref.get("mime") or "application/pdf"
            data = None
            for aid in (ref.get("attachmentId"), be.fresh_attachment_id(svc, m["message_id"], fn)):
                if not aid:
                    continue
                try:
                    a = svc.users().messages().attachments().get(
                        userId="me", messageId=m["message_id"], id=aid).execute()
                    data = base64.urlsafe_b64decode(a["data"]); break
                except Exception:
                    continue
            if data:
                chash = hashlib.sha256(data).hexdigest()
                cur.execute("SELECT id FROM documents WHERE content_hash=%s AND id<>%s LIMIT 1",
                            (chash, r["id"]))
                dup = cur.fetchone()
                if dup:
                    be.merge_into(cur, r["id"], dup["id"]); merged += 1; handled = True
                else:
                    path = os.path.join(be.STORE, f"{m['message_id']}__{be.safe_name(fn)}")
                    with open(path, "wb") as fh:
                        fh.write(data)
                    txt = be.pdf_text(data) if "pdf" in mime else ""
                    cur.execute("""UPDATE documents SET file_path=%s,
                        content_hash=coalesce(content_hash,%s),
                        mime_type=coalesce(nullif(mime_type,''),%s),
                        extracted_text=coalesce(nullif(extracted_text,''),%s),
                        ingest_source='gmail_attachment' WHERE id=%s""",
                        (path, chash, mime, (txt or None), r["id"]))
                    recovered += 1; handled = True
    if not handled:
        cur.execute("UPDATE documents SET ingest_status='quarantined_nobytes' WHERE id=%s", (r["id"],))
        quarantined.append((r["id"], fn))

print(f"OCR-able (bytes present, leave for daemon): {ocrable}")
print(f"recovered bytes from email: {recovered}")
print(f"merged into canonical (dup): {merged}")
print(f"quarantined (no recoverable source): {len(quarantined)}")
for i, f in quarantined[:25]:
    print(f"  q doc#{i}  {(f or '')[:44]}")
cur.close(); conn.close()
