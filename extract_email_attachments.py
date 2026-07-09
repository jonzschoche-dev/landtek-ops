#!/usr/bin/env python3
"""extract_email_attachments.py — pull PDF attachments from case-relevant emails into `documents`,
linked through `email_documents` (the CANONICAL email↔doc spine).

Priority-1 build-out under docs/LEGAL_FINDABILITY_COMPLETENESS_DIRECTIVE.md + docs/COMPOSITION_MODEL_DRAFT.md.
This EXTENDS the working deploy_799 extractor (it is NOT a rebuild) with: a canonical-linker write, a real
`--dry-run`, a case-relevant-only gate, PDF-focus, stronger idempotency, provenance/source stamping, and
targeting flags for testing.

DESIGN DECISIONS (grounded 2026-07-09 against the live schema):
  • CANONICAL LINKER = `email_documents(message_id, doc_id, role, filename)` (UNIQUE(message_id, doc_id)).
    `gmail_messages.document_id` is kept ONLY as a denormalised 1:1 cache (legacy). Every extract writes BOTH.
  • CASE-RELEVANT ONLY — process emails with `case_file IS NOT NULL` (targeted; no personal-inbox flood).
  • A5 CLIENT SEPARATION — a new document inherits `case_file` (the CLIENT boundary) from its parent email.
    It DOES NOT inherit `matter_code`: within one client, case_file→matter_code is one-to-many and the fine
    matter is a property of the document's CONTENT, not the carrier email — so matter_code is left NULL for the
    standing content-based matter pipeline to assign. `account` is inherited structurally via the
    email_documents.message_id → gmail_messages.account link (documents has no account column).
  • IDEMPOTENCY (safe to re-run): a document is deduped by `content_hash`; the same PDF appearing in two emails
    becomes ONE `documents` row with TWO `email_documents` links (true many-to-many). Link dedup is the
    UNIQUE(message_id, doc_id). Re-running creates nothing new.
  • PDF FOCUS (v1) — only application/pdf (or *.pdf) attachments; non-PDF are counted and logged, never
    silently dropped.
  • DO NOT OCR/EMBED here — new rows carry ingest_status='ingested' and the standing OCR+embed pipelines pick
    them up. Fully reversible: rows are content-hashed and linked; rollback = delete the doc + its ED links.

MODES:
  (default)          extract attachments from case-relevant, not-yet-extracted emails
  --dry-run          fetch + hash but WRITE NOTHING; report NEW vs LINKED(existing hash) vs SKIPPED per file
  --backfill-linker  one-shot: create missing email_documents rows for gmail_messages.document_id links

TARGETING (for testing):
  --message-id ID    (repeatable) only these gmail message_ids
  --since YYYY-MM-DD / --until YYYY-MM-DD   received_at window
  --limit N          cap emails scanned (default 200)
"""
import argparse, base64, hashlib, json, os, re, sys
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
UPLOADS = "/root/landtek/uploads"
MAX_WARN_BYTES = 25 * 1024 * 1024  # log (don't skip) attachments larger than this


def _is_pdf(a):
    mime = (a.get("mime") or "").lower()
    fn = (a.get("filename") or "").lower()
    return mime == "application/pdf" or fn.endswith(".pdf")


def _safe_name(fn, idx):
    """Filename fallback for attachments that arrive without one (edge case)."""
    if not fn:
        fn = f"attachment_{idx}.pdf"
    return re.sub(r"[^A-Za-z0-9._-]", "_", fn)[:120]


def _find_attid(payload, fname_lower):
    """Walk a fresh message payload for the CURRENT attachmentId of a filename (ids expire/rotate)."""
    def walk(p):
        for part in (p.get("parts") or []):
            yield part
            yield from walk(part)
    first_pdf = None
    for part in walk(payload):
        aid = (part.get("body") or {}).get("attachmentId")
        if not aid:
            continue
        pf = (part.get("filename") or "").lower()
        if fname_lower and pf == fname_lower:
            return aid
        if pf.endswith(".pdf") and first_pdf is None:
            first_pdf = aid
    return first_pdf


def fetch_attachment_bytes(client_for, all_accounts, m, a):
    """Robustly fetch attachment bytes. Handles the two real failure modes found 2026-07-09:
      (1) MIS-TAGGED account — a message tagged primary that actually lives in the backup mailbox (pre-`account`
          ingests default to primary); try the tagged account first, then the others.
      (2) STALE/EXPIRED attachmentId — Gmail rotates ids; on failure, re-resolve the id from a fresh message
          fetch and retry.
    Returns (data|None, resolved_account|None, note). None means the message is gone from every mailbox."""
    fn = (a.get("filename") or "").lower()
    att_id = a.get("attachmentId")
    tagged = m["account"]
    order = [tagged] + [acct for acct in all_accounts if acct != tagged]
    last = "no attachmentId"
    for acct in order:
        try:
            g = client_for(acct)
        except Exception as e:
            last = f"client({acct}): {str(e)[:60]}"; continue
        if att_id:  # 1) try the stored id on this account
            try:
                r = g.users().messages().attachments().get(
                    userId="me", messageId=m["message_id"], id=att_id).execute()
                return base64.urlsafe_b64decode(r["data"]), acct, "stored"
            except Exception as e:
                last = str(e)[:80]
        try:  # 2) message not fetchable here → try next account; else re-resolve a fresh id
            msg = g.users().messages().get(userId="me", id=m["message_id"], format="full").execute()
        except Exception as e:
            last = str(e)[:80]; continue
        fresh = _find_attid(msg.get("payload", {}), fn)
        if fresh:
            try:
                r = g.users().messages().attachments().get(
                    userId="me", messageId=m["message_id"], id=fresh).execute()
                return base64.urlsafe_b64decode(r["data"]), acct, "refreshed-id"
            except Exception as e:
                last = str(e)[:80]
    return None, None, last


def backfill_linker(cur, dry):
    """Create the missing canonical email_documents rows for existing 1:1 document_id caches."""
    cur.execute("""
        SELECT g.message_id, g.document_id, d.original_filename
          FROM gmail_messages g JOIN documents d ON d.id = g.document_id
         WHERE g.document_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM email_documents e
                            WHERE e.message_id = g.message_id AND e.doc_id = g.document_id)
    """)
    gap = cur.fetchall()
    print(f"  [backfill-linker] {len(gap)} cache links missing a canonical email_documents row")
    if dry:
        for r in gap[:20]:
            print(f"    would link msg {r['message_id'][:24]} -> doc {r['document_id']} ({(r['original_filename'] or '')[:40]})")
        return
    for r in gap:
        cur.execute("""INSERT INTO email_documents (message_id, doc_id, role, filename)
                       VALUES (%s, %s, 'attachment', %s)
                       ON CONFLICT (message_id, doc_id) DO NOTHING""",
                    (r["message_id"], r["document_id"], r["original_filename"]))
    print(f"  [backfill-linker] created {len(gap)} canonical link(s)")


def link_canonical(cur, message_id, doc_id, filename, dry):
    """Write BOTH the canonical email_documents row and the legacy gmail_messages.document_id cache."""
    if dry:
        return
    cur.execute("""INSERT INTO email_documents (message_id, doc_id, role, filename)
                   VALUES (%s, %s, 'attachment', %s)
                   ON CONFLICT (message_id, doc_id) DO NOTHING""",
                (message_id, doc_id, filename))
    cur.execute("UPDATE gmail_messages SET document_id = %s WHERE message_id = %s AND document_id IS NULL",
                (doc_id, message_id))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--message-id", action="append", default=None, help="target specific gmail message_id(s)")
    ap.add_argument("--since", default=None, help="received_at >= YYYY-MM-DD")
    ap.add_argument("--until", default=None, help="received_at < YYYY-MM-DD")
    ap.add_argument("--backfill-linker", action="store_true",
                    help="one-shot: create missing email_documents rows for existing document_id caches")
    args = ap.parse_args()
    dry = args.dry_run

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.backfill_linker:
        backfill_linker(cur, dry)
        cur.close(); conn.close(); return

    sys.path.insert(0, "/root/landtek")
    from gmail_watcher import gmail_client, ACCOUNT_ADDR
    # PER-ACCOUNT clients: an attachmentId is only fetchable via the mailbox that holds the message.
    _addr2acct = {v: k for k, v in ACCOUNT_ADDR.items()}
    _clients = {}
    ALL_ACCOUNTS = list(ACCOUNT_ADDR.values())

    def client_for(account_addr):
        acct = _addr2acct.get(account_addr, "primary")
        if acct not in _clients:
            _clients[acct] = gmail_client(acct)
        return _clients[acct]

    # CASE-RELEVANT ONLY (case_file IS NOT NULL) + not-yet-extracted (document_id IS NULL email-level dedup).
    where = ["has_attachments = true", "attachment_refs IS NOT NULL",
             "document_id IS NULL", "case_file IS NOT NULL"]
    params = []
    if args.message_id:
        where.append("message_id = ANY(%s)"); params.append(args.message_id)
    if args.since:
        where.append("received_at >= %s"); params.append(args.since)
    if args.until:
        where.append("received_at < %s"); params.append(args.until)
    params.append(args.limit)

    cur.execute(f"""
        SELECT id, message_id, subject, from_addr, attachment_refs, case_file, received_at,
               coalesce(account, 'jonathan@hayuma.org') AS account
          FROM gmail_messages
         WHERE {' AND '.join(where)}
         ORDER BY received_at DESC LIMIT %s
    """, params)
    msgs = cur.fetchall()
    mode = "DRY-RUN (no writes)" if dry else "LIVE"
    print(f"  [{mode}] {len(msgs)} case-relevant email(s) with attachments to scan\n")

    inserted = linked = skipped_nonpdf = skipped_gone = 0
    for m in msgs:
        refs = m["attachment_refs"] if isinstance(m["attachment_refs"], list) else json.loads(m["attachment_refs"] or "[]")
        pdfs = [a for a in refs if _is_pdf(a)]
        skipped_nonpdf += len(refs) - len(pdfs)
        for idx, a in enumerate(pdfs):
            fn = a.get("filename") or ""
            size = a.get("size", 0) or 0
            data, resolved_acct, note = fetch_attachment_bytes(client_for, ALL_ACCOUNTS, m, a)
            if data is None:
                print(f"    ✗ GONE {(fn or 'unnamed')[:40]}: not fetchable in any mailbox ({note})")
                skipped_gone += 1; continue
            if resolved_acct != m["account"] or note == "refreshed-id":
                print(f"    ↻ recovered {(fn or 'unnamed')[:40]} via {resolved_acct} ({note})")
                if not dry and resolved_acct != m["account"]:  # self-heal the mis-tagged account
                    cur.execute("UPDATE gmail_messages SET account=%s WHERE id=%s", (resolved_acct, m["id"]))

            content_hash = hashlib.sha256(data).hexdigest()
            big = " [LARGE]" if len(data) > MAX_WARN_BYTES else ""
            cur.execute("SELECT id FROM documents WHERE content_hash = %s LIMIT 1", (content_hash,))
            ex = cur.fetchone()

            if ex:  # dedup: same bytes already a document → just add the canonical link (many-to-many)
                link_canonical(cur, m["message_id"], ex["id"], fn or None, dry)
                linked += 1
                if dry:
                    print(f"    LINK  {m['case_file']:<12} {(fn or 'unnamed')[:44]}  -> existing doc {ex['id']}{big}")
                continue

            if dry:
                print(f"    NEW   {m['case_file']:<12} {(fn or 'unnamed')[:44]}  ({size} b){big}")
                inserted += 1
                continue

            safe_fn = _safe_name(fn, idx)
            target_dir = os.path.join(UPLOADS, m["case_file"], "email_attachments")
            os.makedirs(target_dir, exist_ok=True)
            local_path = os.path.join(target_dir, f"em{m['id']}_{safe_fn}")
            with open(local_path, "wb") as f:
                f.write(data)

            cur.execute("""
                INSERT INTO documents
                  (case_file, matter_code, original_filename, smart_filename, content_hash, sha256,
                   mime_type, status, file_path, master_form, ingest_status, ingest_source,
                   text_length, created_at)
                VALUES (%s, NULL, %s, %s, %s, %s, %s, 'ingested_from_email', %s, 'digital', 'ingested',
                        'gmail_attachment', NULL, now())
                RETURNING id
            """, (m["case_file"], fn or safe_fn, fn or safe_fn, content_hash, content_hash,
                  a.get("mime"), local_path))
            new_id = cur.fetchone()["id"]
            link_canonical(cur, m["message_id"], new_id, fn or None, dry)
            inserted += 1
            if inserted % 10 == 0:
                print(f"    ✓ ingested {inserted} attachments...")

    verb = "would be created" if dry else "inserted"
    print(f"\n  Summary [{mode}]:")
    print(f"    NEW documents {verb}: {inserted}")
    print(f"    LINKED to existing doc (same hash): {linked}")
    print(f"    skipped non-PDF (v1 scope): {skipped_nonpdf}")
    print(f"    skipped GONE (not in any mailbox): {skipped_gone}")
    if dry:
        print(f"\n  DRY-RUN — nothing written. Re-run without --dry-run to apply.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
