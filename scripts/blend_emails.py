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


sys.path.insert(0, "/root/landtek/scripts")
try:
    from execution_classify import classify_text
except Exception:
    classify_text = None

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_BORNE_RE = re.compile(
    rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?({_MONTHS})[,\s]+(\d{{4}})"
    rf"|({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_MONTHNUM = {m.lower(): i for i, m in enumerate(_MONTHS.split("|"), 1)}


def pdf_text(data):
    try:
        d = fitz.open(stream=data, filetype="pdf")
        t = "\n".join(p.get_text() for p in d)
        d.close()
        return t.strip()
    except Exception:
        return ""


def extract_text(data, mime, path):
    """Text by TYPE — PDF (fitz), .docx (python-docx), .xlsx (openpyxl if present). The ACTUAL content
    of the attachment, not just PDFs — the judicial affidavits + complaints arrive as .docx and were
    previously ingested textless."""
    m = (mime or "").lower(); p = (path or "").lower()
    if "pdf" in m or p.endswith(".pdf"):
        return pdf_text(data)
    if "word" in m or "officedocument.wordprocessing" in m or p.endswith(".docx"):
        try:
            from docx import Document
            return "\n".join(par.text for par in Document(path).paragraphs).strip()
        except Exception:
            return ""
    if "sheet" in m or "excel" in m or p.endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            rows = ["\t".join(str(c) for c in r if c is not None)
                    for ws in openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets
                    for r in ws.iter_rows(values_only=True)]
            return "\n".join(rows).strip()
        except Exception:
            return ""
    return ""


def borne_date(text):
    """The date the DOCUMENT bears, read from its OPENING text — a CLAIM, flagged weak. NEVER the email
    date: conflating 'the date on the letter' with 'when we received it' is the forensic error this whole
    pass exists to prevent. Returns 'YYYY-MM-DD' or None."""
    if not text:
        return None
    m = _BORNE_RE.search(text[:1500])
    if not m:
        return None
    try:
        if m.group(2):                                    # "8 May 2026" / "8th day of May, 2026"
            d, mon, y = int(m.group(1)), _MONTHNUM[m.group(2).lower()], int(m.group(3))
        else:                                             # "May 8, 2026"
            mon, d, y = _MONTHNUM[m.group(4).lower()], int(m.group(5)), int(m.group(6))
        return f"{y:04d}-{mon:02d}-{d:02d}"
    except Exception:
        return None


def fresh_attachment_id(svc, msg_id, filename):
    """Walk a message's parts to recover a current attachmentId for a filename
    (the stored one can be stale)."""
    try:
        msg = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
    except Exception:
        return None
    stack = [msg.get("payload", {})]
    while stack:
        p = stack.pop()
        if p.get("filename") == filename and p.get("body", {}).get("attachmentId"):
            return p["body"]["attachmentId"]
        stack.extend(p.get("parts", []) or [])
    return None


def merge_into(cur, stub, canon):
    """A hollow stub turned out to duplicate an existing canonical doc. Repoint
    its high-value citations to the canonical doc (no broken references), then
    quarantine the stub so it's never served as evidence. The stub ROW stays
    (so any FK still resolves) but leaves master_form='digital'."""
    # evidence_trail / proposals: move, dropping any that would duplicate
    for tbl in ("evidence_trail", "evidence_trail_proposals"):
        cur.execute(f"""UPDATE {tbl} e SET supporting_doc_id=%s
                         WHERE supporting_doc_id=%s
                           AND NOT EXISTS (SELECT 1 FROM {tbl} e2
                               WHERE e2.claim_id=e.claim_id AND e2.supporting_doc_id=%s)""",
                    (canon, stub, canon))
        cur.execute(f"DELETE FROM {tbl} WHERE supporting_doc_id=%s", (stub,))
    cur.execute("""INSERT INTO document_matter_links (doc_id, matter_code)
                   SELECT %s, matter_code FROM document_matter_links WHERE doc_id=%s
                   ON CONFLICT DO NOTHING""", (canon, stub))
    cur.execute("DELETE FROM document_matter_links WHERE doc_id=%s", (stub,))
    cur.execute("""INSERT INTO document_titles (doc_id, tct_number, mentions, source)
                   SELECT %s, tct_number, mentions, source FROM document_titles WHERE doc_id=%s
                   ON CONFLICT DO NOTHING""", (canon, stub))
    cur.execute("DELETE FROM document_titles WHERE doc_id=%s", (stub,))
    cur.execute("UPDATE gmail_messages SET document_id=%s WHERE document_id=%s", (canon, stub))
    cur.execute("""UPDATE email_documents e SET doc_id=%s WHERE doc_id=%s
                    AND NOT EXISTS (SELECT 1 FROM email_documents e2
                        WHERE e2.message_id=e.message_id AND e2.doc_id=%s)""", (canon, stub, canon))
    cur.execute("DELETE FROM email_documents WHERE doc_id=%s", (stub,))
    cur.execute("UPDATE documents SET ingest_status='quarantined_dup', ingest_source=%s WHERE id=%s",
                (f"dup_of:{canon}", stub))


def recover_hollow(cur, svc, limit=0, only_ids=None, latest_ok=False):
    """Refill hollow rows (no bytes) IN PLACE from their source email attachment,
    preserving the doc id so existing citations/links stay valid. SAFETY: only
    recover when the filename matches EXACTLY ONE email attachment — ambiguous
    names (image.png appears in many emails) are skipped, never mislinked."""
    cur.execute("""SELECT id, original_filename FROM documents
        WHERE master_form='digital' AND coalesce(file_path,'')='' AND coalesce(drive_file_id,'')=''
          AND original_filename IS NOT NULL ORDER BY id""")
    docs = [d for d in cur.fetchall() if not only_ids or d["id"] in only_ids]
    recovered, merged, failed = [], [], []
    for d in docs:
        if limit and len(recovered) >= limit:
            break
        fn = d["original_filename"]
        # SAFE match: a unique filename, OR the same file (identical size) across
        # several emails. Only DIFFERENT-size collisions are truly ambiguous.
        cur.execute("""SELECT g.message_id, g.sent_at, g.received_at, g.matter_codes,
                              a AS ref, (a->>'size') sz
                         FROM gmail_messages g, jsonb_array_elements(g.attachment_refs) a
                        WHERE g.has_attachments AND lower(a->>'filename')=lower(%s)
                          AND a->>'attachmentId' IS NOT NULL
                        ORDER BY coalesce(g.sent_at,g.received_at) DESC NULLS LAST""", (fn,))
        matches = cur.fetchall()
        if not matches:
            failed.append((d["id"], fn, "no email match")); continue
        sizes = {mm["sz"] for mm in matches}
        if len(sizes) > 1 and not latest_ok:
            failed.append((d["id"], fn, f"ambiguous ({len(matches)} differing versions)")); continue
        m = matches[0]  # most recent (matches ordered DESC by date)
        src = "gmail_attachment_latest" if len(sizes) > 1 else "gmail_attachment"
        ref = m["ref"]; mime = ref.get("mime") or "application/pdf"
        data = None
        for aid in (ref.get("attachmentId"), fresh_attachment_id(svc, m["message_id"], fn)):
            if not aid:
                continue
            try:
                a = svc.users().messages().attachments().get(
                    userId="me", messageId=m["message_id"], id=aid).execute()
                data = base64.urlsafe_b64decode(a["data"]); break
            except Exception:
                continue
        if not data:
            failed.append((d["id"], fn, "fetch fail")); continue
        chash = hashlib.sha256(data).hexdigest()
        cur.execute("SELECT id FROM documents WHERE content_hash=%s AND id<>%s LIMIT 1",
                    (chash, d["id"]))
        canon = cur.fetchone()
        if canon:
            merge_into(cur, d["id"], canon["id"])
            merged.append((d["id"], canon["id"], fn)); continue
        path = os.path.join(STORE, f"{m['message_id']}__{safe_name(fn)}")
        with open(path, "wb") as fh:
            fh.write(data)
        txt = pdf_text(data) if "pdf" in mime else ""
        ed = m["sent_at"] or m["received_at"]
        cur.execute("""UPDATE documents SET file_path=%s, content_hash=coalesce(content_hash,%s),
              mime_type=coalesce(nullif(mime_type,''),%s),
              extracted_text=coalesce(nullif(extracted_text,''),%s),
              ingest_source=%s, doc_date=coalesce(doc_date,%s)
            WHERE id=%s""", (path, chash, mime, (txt or None), src,
                             (str(ed) if ed else None), d["id"]))
        cur.execute("""INSERT INTO email_documents (message_id, doc_id, role, filename)
              VALUES (%s,%s,'recovered',%s) ON CONFLICT DO NOTHING""", (m["message_id"], d["id"], fn))
        for mc in (m["matter_codes"] or []):
            cur.execute("INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        (d["id"], mc))
        recovered.append((d["id"], fn, f"{len(txt)}c text" if txt else "ocr_pending"))
    return recovered, merged, failed


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


CLIENT_OF = {"MWK": "MWK-001", "PAR": "Paracale-001", "NIBDC": "NIBDC-001"}


def blend_email(cur, svc, g):
    msg_id = g["message_id"]
    refs = g["attachment_refs"] or []
    matters = list(g["matter_codes"] or [])
    matter1 = matters[0] if matters else None
    # SEPARATION GUARD: the client comes from the VALIDATED matter tags, NEVER from a weak email
    # case_file. A 'DELAYED REGISTRATION OF BIRTH' email was tagged Paracale (because Allan Inocalla
    # appears only as the WITNESS) and blindly inheriting that misfiled Patricia's MWK birth docs across
    # the sacred client line. No matter_codes → leave the doc UNCLASSIFIED (NULL) for proper downstream
    # classification, rather than guess a client and risk a cross-client misfile.
    case_file = None
    if matter1:
        case_file = next((c for p, c in CLIENT_OF.items() if matter1.startswith(p)), g["case_file"])
    made, linked, skipped = [], [], []
    for ref in refs:
        fn = ref.get("filename") or "attachment"
        att_id = ref.get("attachmentId")
        mime = ref.get("mime") or "application/octet-stream"
        if is_noise(ref):
            skipped.append((fn, "inline/noise image"))
            continue
        # fetch bytes — try the stored attachmentId, then a FRESHLY-resolved one (stored IDs go stale,
        # which is why much of the backlog silently failed to extract)
        data = None
        for aid in (att_id, fresh_attachment_id(svc, msg_id, fn)):
            if not aid:
                continue
            try:
                a = svc.users().messages().attachments().get(
                    userId="me", messageId=msg_id, id=aid).execute()
                data = base64.urlsafe_b64decode(a["data"]); break
            except Exception:
                continue
        if data is None:
            skipped.append((fn, "fetch fail (stale id + refresh failed)"))
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
            txt = extract_text(data, mime, path)
            need_ocr = (not txt) and (mime.startswith("image/") or "pdf" in mime)
            # FORENSIC: doc_date = the BORNE date read from CONTENT (a claim, flagged weak), NEVER the
            # email date. execution_status = draft/executed/received from the text. The email envelope
            # (claimed-send + the TRUE Gmail receipt) is recorded distinctly in execution_metadata so
            # receipt ≠ borne is preserved end-to-end.
            bdate = borne_date(txt)
            est, emeta, _conf = (classify_text(txt, mime_type=mime, smart_filename=fn)
                                 if (classify_text and txt) else (None, {}, 0.0))
            emeta = dict(emeta or {})
            emeta.update({"source": "gmail_attachment", "email_message_id": msg_id,
                          "email_from": g.get("from_name"),
                          "email_sent_at": str(g["sent_at"]) if g["sent_at"] else None,
                          "email_received_at": str(g["received_at"]) if g["received_at"] else None})
            cur.execute("""
                INSERT INTO documents
                  (master_form, ingest_source, original_filename, smart_filename, mime_type,
                   file_path, content_hash, doc_date, doc_date_quality, case_file, matter_code,
                   classification, extracted_text, execution_status, execution_metadata)
                VALUES ('digital','gmail_attachment',%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s)
                RETURNING id""",
                (fn, fn, mime, path, chash, bdate, ("content_weak" if bdate else None),
                 case_file, matter1, None, (txt or None), est, psycopg2.extras.Json(emeta)))
            doc_id = cur.fetchone()["id"]
            role = "draft" if est in ("draft_unsigned", "template") else "attachment"
            cur.execute("""INSERT INTO email_documents (message_id, doc_id, role, filename)
                           VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                        (msg_id, doc_id, role, fn))
            made.append((fn, doc_id, f"{est or 'unclassified'}·{len(txt)}c" if txt else "ocr_pending"))
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
    ap.add_argument("--recover-hollow", action="store_true",
                    help="refill hollow rows in place from their source email attachment")
    ap.add_argument("--ids", help="comma-separated doc ids to recover (with --recover-hollow)")
    ap.add_argument("--latest-ok", action="store_true",
                    help="for ambiguous (multi-version) filenames, recover the most recent")
    args = ap.parse_args()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)

    if getattr(args, "recover_hollow", False):
        only = {int(x) for x in args.ids.split(",")} if args.ids else None
        svc = gmail_client()
        rec, merged, fail = recover_hollow(cur, svc, limit=args.limit, only_ids=only,
                                           latest_ok=getattr(args, "latest_ok", False))
        print(f"[recover] {len(rec)} refilled in place · {len(merged)} merged into canonical (dedup) · {len(fail)} not recovered")
        for did, fn, note in rec:
            print(f"    ↻ doc#{did}  {fn[:50]}  ({note})")
        for did, canon, fn in merged:
            print(f"    ⇒ doc#{did} merged into canonical doc#{canon}  {fn[:40]}")
        for did, fn, why in fail[:25]:
            print(f"    · skip doc#{did}  {fn[:42]}  ({why})")
        cur.close(); conn.close(); return

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
