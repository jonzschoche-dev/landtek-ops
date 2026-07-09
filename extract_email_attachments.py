#!/usr/bin/env python3
"""Pull email attachments into documents table (deploy 119)."""
import argparse, base64, hashlib, json, os, re, sys
from datetime import datetime
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
UPLOADS = "/root/landtek/uploads"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default=None)
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    sys.path.insert(0, "/root/landtek")
    from gmail_watcher import gmail_client, ACCOUNT_ADDR
    # PER-ACCOUNT clients: an attachmentId is only fetchable via the mailbox that holds the message. Using the
    # primary (hayuma) client for a backup (jonzschoche) message fails — that was why backup attachments never
    # became documents. Map the email's account back to primary|backup and lazily build one client each.
    _addr2acct = {v: k for k, v in ACCOUNT_ADDR.items()}
    _clients = {}

    def client_for(account_addr):
        acct = _addr2acct.get(account_addr, "primary")
        if acct not in _clients:
            _clients[acct] = gmail_client(acct)
        return _clients[acct]

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, message_id, subject, from_addr, attachment_refs, case_file, received_at,
               coalesce(account, 'jonathan@hayuma.org') AS account
          FROM gmail_messages
         WHERE has_attachments = true AND attachment_refs IS NOT NULL AND document_id IS NULL
         ORDER BY received_at DESC LIMIT %s
    """, (args.limit,))
    msgs = cur.fetchall()
    print(f"  {len(msgs)} emails with attachments")

    inserted = linked = skipped = 0
    for m in msgs:
        refs = m["attachment_refs"] if isinstance(m["attachment_refs"], list) else json.loads(m["attachment_refs"] or "[]")
        for a in refs:
            fn = a.get("filename") or ""
            if not fn: continue
            # Skip embedded images
            if (a.get("mime") or "").startswith("image/") and a.get("size", 0) < 100_000:
                skipped += 1; continue
            att_id = a.get("attachmentId")
            if not att_id: skipped += 1; continue
            try:
                resp = client_for(m["account"]).users().messages().attachments().get(
                    userId="me", messageId=m["message_id"], id=att_id).execute()
                data = base64.urlsafe_b64decode(resp["data"])
            except Exception as e:
                print(f"  ✗ {fn[:40]}: {str(e)[:80]}")
                skipped += 1; continue

            content_hash = hashlib.sha256(data).hexdigest()
            # Skip if already in DB by hash
            cur.execute("SELECT id FROM documents WHERE content_hash = %s LIMIT 1", (content_hash,))
            ex = cur.fetchone()
            if ex:
                cur.execute("UPDATE gmail_messages SET document_id = %s WHERE id = %s",
                            (ex["id"], m["id"]))
                linked += 1
                continue

            # Save locally
            safe_fn = re.sub(r"[^A-Za-z0-9._-]", "_", fn)[:120]
            case_subdir = (m.get("case_file") or "uncorrelated")
            target_dir = os.path.join(UPLOADS, case_subdir, "email_attachments")
            os.makedirs(target_dir, exist_ok=True)
            local_path = os.path.join(target_dir, f"em{m['id']}_{safe_fn}")
            with open(local_path, "wb") as f:
                f.write(data)

            cur.execute("""
                INSERT INTO documents
                  (case_file, original_filename, smart_filename, content_hash,
                   mime_type, status, file_path, master_form, ingest_status,
                   drive_file_id, conversation_id, text_length, created_at)
                VALUES (%s, %s, %s, %s, %s, 'ingested_from_email', %s, 'digital', 'ingested',
                        NULL, NULL, NULL, now())
                RETURNING id
            """, (m.get("case_file"), fn, fn, content_hash, a.get("mime"), local_path))
            new_id = cur.fetchone()["id"]
            cur.execute("UPDATE gmail_messages SET document_id = %s WHERE id = %s",
                        (new_id, m["id"]))
            inserted += 1
            if inserted % 10 == 0:
                print(f"  ✓ ingested {inserted} attachments...")

    print(f"\n  Summary:")
    print(f"    inserted: {inserted}")
    print(f"    linked (already had hash): {linked}")
    print(f"    skipped: {skipped}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
