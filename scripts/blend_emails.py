#!/usr/bin/env python3
"""blend_emails.py — blend the unblended email TRAIL into the canonical corpus.

For every relevant email with attachments that aren't yet in the corpus, this:
  1. fetches the attachment bytes via the Gmail API (reuses gmail_watcher auth)
  2. stores them locally  -> REACHABLE invariant (no hollow rows)
  3. extracts text with fitz for text-layer PDFs (free, no Gemini); honestly
     flags scanned/image attachments for OCR instead of faking text -> READ
  4. dedups by content_hash / filename so we never duplicate an existing doc
  5. inserts a canonical documents row (ingest_source='gmail_attachment') -> SOURCED
  6. links it to the email (email_documents junction) and the matter
     (document_matter_links + case_file/matter_code) -> LINKED

It NEVER creates a hollow row. Embedding (SEARCHABLE) is a separate backfill.

  python3 blend_emails.py --limit 3            # sample (verify first)
  python3 blend_emails.py --message <gmail_id> # one specific email
  python3 blend_emails.py --all                # the whole relevant trail
"""
from __future__ import annotations
import argparse, base64, hashlib, os, re, sys
import psycopg2, psycopg2.extras
import fitz  # PyMuPDF

sys.path.insert(0, "/root/landtek")
from gmail_watcher import gmail_client

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
STORE = "/root/landtek/corpus_store/gmail"


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", (s or "attachment"))[:120]


def ensure_schema(cur):
    os.makedirs(STORE, exist_ok=True)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS email_documents (
            id serial PRIMARY KEY,
            message_id text NOT NULL,
            doc_id int NOT NULL,
            role text DEFAULT 'attachment',
            filename text,
            created_at timestamptz DEFAULT now(),
            UNIQUE (message_id, doc_id)
        )""")


def pdf_text(data):
    try:
        d = fitz.open(stream=data, filetype="pdf")
        t = "\n".join(p.get_text() for p in d)
        d.close()
        return t.strip()
    except Exception:
        return ""


def find_existing(cur, content_hash):
    """Dedup by CONTENT only. Filename dedup is banned — generic names like
    'image.png' collapse distinct files onto one doc (a mislink)."""
    cur.execute("SELECT id FROM documents WHERE content_hash=%s LIMIT 1", (content_hash,))
    r = cur.fetchone()
    return (r["id"], "content_hash") if r else (None, None)


GENERIC = {"image.png", "image.jpg", "image.jpeg", "image.gif",
           "image001.png", "image002.png", "image003.png", "logo.png"}


def is_noise(ref):
    """Inline signature/logo images are not evidence. Keep all PDFs; keep large
    images (could be a photographed document); drop small/inline/generic images."""
    mime = (ref.get("mime") or "").lower()
    size = ref.get("size") or 0
    fn = (ref.get("filename") or "").lower()
    if "pdf" in mime:
        return False
    if mime.startswith("image/") and size < 120_000:
        return True
    if fn in GENERIC and size < 200_000:
        return True
    if size and size < 3000:
        return True
    return False


def blend_email(cur, svc, g):
    msg_id = g["message_id"]
    refs = g["attachment_refs"] or []
    case_file = g["case_file"] or "MWK-001"
    matters = list(g["matter_codes"] or [])
    matter1 = matters[0] if matters else None
    ddate = g["sent_at"] or g["received_at"]
    made, linked, skipped = [], [], []
    for ref in refs:
        fn = ref.get("filename") or "attachment"
        att_id = ref.get("attachmentId")
        mime = ref.get("mime") or "application/octet-stream"
        if not att_id:
            skipped.append((fn, "no attachmentId"))
            continue
        if is_noise(ref):
            skipped.append((fn, "inline/noise image"))
            continue
        # fetch bytes
        try:
            a = svc.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=att_id).execute()
            data = base64.urlsafe_b64decode(a["data"])
        except Exception as e:
            skipped.append((fn, f"fetch fail {type(e).__name__}"))
            continue
        chash = hashlib.sha256(data).hexdigest()
        existing, how = find_existing(cur, chash)
        if existing:
            cur.execute("""INSERT INTO email_documents (message_id, doc_id, role, filename)
                           VALUES (%s,%s,'attachment',%s) ON CONFLICT DO NOTHING""",
                        (msg_id, existing, fn))
            linked.append((fn, existing, how))
            doc_id = existing
        else:
            path = os.path.join(STORE, f"{msg_id}__{safe_name(fn)}")
            with open(path, "wb") as fh:
                fh.write(data)
            txt = pdf_text(data) if "pdf" in mime else ""
            need_ocr = len(txt) < 50
            cur.execute("""
                INSERT INTO documents
                  (master_form, ingest_source, original_filename, smart_filename, mime_type,
                   file_path, content_hash, doc_date, case_file, matter_code,
                   classification, extracted_text)
                VALUES ('digital','gmail_attachment',%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s)
                RETURNING id""",
                (fn, fn, mime, path, chash, ddate, case_file, matter1,
                 None, (txt or None)))
            doc_id = cur.fetchone()["id"]
            cur.execute("""INSERT INTO email_documents (message_id, doc_id, role, filename)
                           VALUES (%s,%s,'attachment',%s) ON CONFLICT DO NOTHING""",
                        (msg_id, doc_id, fn))
            made.append((fn, doc_id, "ocr_pending" if need_ocr else f"{len(txt)}c text"))
        # matter links
        for mc in matters:
            cur.execute("""INSERT INTO document_matter_links (doc_id, matter_code)
                           VALUES (%s,%s) ON CONFLICT DO NOTHING""", (doc_id, mc))
    # set the email's primary document_id if still null
    if (made or linked) and g["document_id"] is None:
        primary = (made[0][1] if made else linked[0][1])
        cur.execute("UPDATE gmail_messages SET document_id=%s WHERE message_id=%s",
                    (primary, msg_id))
    return made, linked, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--message")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)

    where = ("has_attachments=true AND attachment_refs IS NOT NULL "
             "AND (coalesce(relevance_score,0)>=0.5 OR relevance_status IN ('relevant','confirmed','kept'))")
    params = []
    if args.message:
        where = "message_id=%s"; params = [args.message]
    elif not args.all:
        where += " AND document_id IS NULL"
    sql = f"""SELECT message_id, subject, from_name, sent_at, received_at, case_file,
                     matter_codes, attachment_refs, document_id
                FROM gmail_messages WHERE {where}
               ORDER BY coalesce(sent_at,received_at) DESC"""
    if args.limit:
        sql += f" LIMIT {args.limit}"
    cur.execute(sql, params)
    emails = cur.fetchall()
    print(f"[blend] {len(emails)} emails to process")

    svc = gmail_client()
    tot_made = tot_linked = tot_skip = 0
    for g in emails:
        made, linked, skipped = blend_email(cur, svc, g)
        tot_made += len(made); tot_linked += len(linked); tot_skip += len(skipped)
        if made or linked or skipped:
            print(f"\n• {(g['subject'] or '')[:54]}  [{','.join(g['matter_codes'] or []) or '—'}]")
            for fn, did, note in made:
                print(f"    + NEW doc#{did}  {fn[:48]}  ({note})")
            for fn, did, how in linked:
                print(f"    = linked existing doc#{did}  {fn[:48]}  (dedup:{how})")
            for fn, why in skipped:
                print(f"    ! skipped {fn[:48]}  ({why})")
    print(f"\n[blend] {tot_made} new docs · {tot_linked} deduped-links · {tot_skip} skipped")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
