#!/usr/bin/env python3
"""harvest_email_threads.py — materialize matter-tagged EMAIL BODIES into the canonical corpus,
so the existing doc-lane harvester (harvest_facts.py) can lift their content into facts through
the normal gates. Closes the Botor/CV6839 gap class: blend_emails.py blends ATTACHMENTS only —
bodies (engagement letters, conformes, counsel instructions) never became documents, so the fact
layer stayed silent while the truth sat in gmail_messages.

Per email (matter-tagged, no body-doc yet):
  1. A5 wall FIRST: if the email's matter_codes span >1 CLIENT → SKIP + report (multi-client
     mention is flagged, never auto-assigned — the place-keyword-leak lesson).
  2. documents row for the BODY: ingest_source='gmail_body', extracted_text=body_plain,
     dedup by body content_hash. FORENSIC dates preserved distinctly (never collapsed):
     doc_date=NULL (an email body's borne date is its envelope, not a claimed instrument date);
     claimed sent_at + TRUE Gmail received_at recorded in execution_metadata.
  3. email_documents link (role='body') + document_matter_links per tagged matter +
     gmail_messages.document_id set if still NULL.
Then run:  python3 scripts/harvest_facts.py --all --go   (the existing gated fact lane)
and blend_emails.py --all for the attachment side. Embedding catches up via the backfill daemon.

  python3 scripts/harvest_email_threads.py --limit 5     # sample (verify first)
  python3 scripts/harvest_email_threads.py --all --go
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _client_of_matter(cur, mc):
    cur.execute("SELECT client_code FROM matters WHERE matter_code=%s", (mc,))
    r = cur.fetchone()
    if r:
        return r["client_code"]
    cur.execute("SELECT client_code FROM clients WHERE client_code=%s", (mc,))
    r = cur.fetchone()
    return r["client_code"] if r else None


def worklist(cur, limit=None):
    cur.execute("""
        SELECT g.id, g.message_id, g.subject, g.from_name, g.from_addr, g.sent_at, g.received_at,
               g.body_plain, g.matter_codes, g.document_id, g.case_file
        FROM gmail_messages g
        WHERE g.matter_codes IS NOT NULL AND array_length(g.matter_codes,1) > 0
          AND coalesce(length(g.body_plain),0) >= 80
          AND NOT EXISTS (SELECT 1 FROM email_documents ed
                          WHERE ed.message_id = g.message_id AND ed.role = 'body')
        ORDER BY g.received_at DESC NULLS LAST""" + (f" LIMIT {int(limit)}" if limit else ""))
    return cur.fetchall()


def materialize(cur, g, go=False):
    matters = list(dict.fromkeys(g["matter_codes"] or []))
    clients = {c for c in (_client_of_matter(cur, m) for m in matters) if c}
    if len(clients) > 1:
        return None, f"MULTI-CLIENT {sorted(clients)} — flagged, never auto-assigned (A5)"
    body = g["body_plain"].strip()
    chash = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()
    cur.execute("SELECT id FROM documents WHERE content_hash=%s LIMIT 1", (chash,))
    dup = cur.fetchone()
    if not go:
        return ("DUP->" + str(dup["id"])) if dup else "would-create", None
    if dup:
        doc_id = dup["id"]
    else:
        emeta = {"source": "gmail_body", "email_message_id": g["message_id"],
                 "email_from": g["from_name"] or g["from_addr"],
                 "email_sent_at_claimed": str(g["sent_at"]) if g["sent_at"] else None,
                 "email_received_at_true": str(g["received_at"]) if g["received_at"] else None,
                 "subject": g["subject"]}
        fname = f"EMAIL {str(g['received_at'])[:10] if g['received_at'] else '?'} — {(g['subject'] or 'no subject')[:80]}"
        cur.execute("""
            INSERT INTO documents
              (master_form, ingest_source, original_filename, smart_filename, mime_type,
               content_hash, case_file, matter_code, extracted_text, execution_metadata)
            VALUES ('digital','gmail_body',%s,%s,'text/plain',%s,%s,%s,%s,%s)
            RETURNING id""",
            (fname, fname, chash, g["case_file"], matters[0], body,
             psycopg2.extras.Json(emeta)))
        doc_id = cur.fetchone()["id"]
    cur.execute("""INSERT INTO email_documents (message_id, doc_id, role, filename)
                   VALUES (%s,%s,'body',%s) ON CONFLICT DO NOTHING""",
                (g["message_id"], doc_id, (g["subject"] or "email body")[:120]))
    for mc in matters:
        cur.execute("""INSERT INTO document_matter_links (doc_id, matter_code)
                       VALUES (%s,%s) ON CONFLICT DO NOTHING""", (doc_id, mc))
    if g["document_id"] is None:
        cur.execute("UPDATE gmail_messages SET document_id=%s WHERE message_id=%s",
                    (doc_id, g["message_id"]))
    return doc_id, None


def main():
    ap = argparse.ArgumentParser(description="materialize matter-tagged email bodies into documents")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--go", action="store_true", help="write (default: dry report)")
    a = ap.parse_args()
    if not (a.all or a.limit):
        a.limit = 5
    conn, cur = _conn()
    rows = worklist(cur, None if a.all else a.limit)
    made = dups = skipped = 0
    for g in rows:
        res, why = materialize(cur, g, go=a.go)
        if why:
            skipped += 1
            print(f"  SKIP gmail#{g['id']}: {why}")
        elif a.go:
            made += 1
        else:
            dups += 1 if str(res).startswith("DUP") else 0
    mode = "GO" if a.go else "DRY"
    print(f"[harvest_email_threads {mode}] {len(rows)} body-less tagged emails examined · "
          f"{'materialized ' + str(made) if a.go else 'would-create ' + str(len(rows) - dups - skipped) + ', dups ' + str(dups)}"
          f" · multi-client skipped {skipped}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
