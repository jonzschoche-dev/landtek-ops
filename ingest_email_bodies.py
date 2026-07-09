#!/usr/bin/env python3
"""ingest_email_bodies.py — case-relevant email BODIES become first-class documents (type='Email').

COMPOSITION_MODEL_DRAFT §2.2 (approved) + LEGAL_FINDABILITY directive. The cover email ("here's the Resolution
— note the 15-day deadline") becomes searchable/embeddable NEXT TO its attachments, closing the continuity gap:
body + attachments are siblings under one email via the canonical `email_documents` linker.

ARCHITECTURE (natural extension of extract_email_attachments.py, whose enrichment engine this REUSES):
  • One `documents` row per case-relevant email (case_file IS NOT NULL) with a substantive body.
  • extracted_text = a small FORENSIC HEADER + body_plain. The header keeps the three-dates discipline
    ([[feedback-forensic-email-integration]]): Sent = the sender's CLAIM, Received = Gmail internalDate = FACT.
    Born-digital text → no OCR needed → flows straight to the standing embed pipeline.
  • Canonical link: email_documents(message_id, doc_id, role='body'). Attachments keep role='attachment'.
  • No binary file by default (extension point: --store-eml for raw RFC-822 forensic capture, not built in v1).
  • Inherits case_file + account (structurally, via the linker). matter_code NULL unless the significance
    engine's single same-client docket-exact hit auto-sets it — same A5/A54 rules as attachments.
  • Enrichment at ingest (deploy_809 engine, SIGNALS_VERSION shared): docket/title/party hits, urgency,
    cross-client tripwire — plus a body-specific `cover_message` flag (email carries attachments AND its text
    references them) = composition relevance for exhibit bundling.
  • deterministic-now vs agent-later: this script does registry matching ONLY; deeper reading of the body
    (claims, deadlines-in-prose, tone) is the post-OCR/agentic layer's job.

IDEMPOTENCY: an email with an existing role='body' link is skipped; the composed text is content-hashed
(header includes message-specific dates → distinct per message; a true hash collision links, never duplicates).

USAGE: python3 ingest_email_bodies.py [--dry-run] [--limit N] [--message-id ID ...] [--since/--until YYYY-MM-DD]
"""
import argparse, hashlib, re, sys
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek")
from extract_email_attachments import (DSN, load_registries, extract_signals, apply_enrichment, _sig_summary)

MIN_BODY = 40           # skip degenerate bodies (bare "Thanks." forwards carry no findable signal)
ATTACH_REF_RE = re.compile(r"\b(attach|annex|exhibit|enclos|herewith|kindly find)\w*", re.IGNORECASE)


def _compose_text(m):
    """Forensic header + body. Sent = sender's CLAIM; Received = Gmail internalDate = the FACT."""
    hdr = [f"EMAIL — {m['subject'] or '(no subject)'}",
           f"From: {m['from_name'] or ''} <{m['from_addr'] or ''}>".strip(),
           f"To: {', '.join(m['to_addrs'] or [])}"]
    if m.get("cc_addrs"):
        hdr.append(f"Cc: {', '.join(m['cc_addrs'])}")
    hdr += [f"Sent (claimed, sender header): {m['sent_at'] or 'unknown'}",
            f"Received (fact, Gmail internalDate): {m['received_at'] or 'unknown'}",
            f"Mailbox: {m['account']}   Gmail message: {m['message_id']}   thread: {m['thread_id']}",
            "-" * 72, ""]
    return "\n".join(hdr) + (m["body_plain"] or "").strip() + "\n"


def _slug(s, n=70):
    return re.sub(r"[^A-Za-z0-9]+", "_", (s or "no_subject")).strip("_")[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--message-id", action="append", default=None)
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    args = ap.parse_args()
    dry = args.dry_run

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    regs = load_registries(cur)

    where = ["g.case_file IS NOT NULL",
             "length(trim(coalesce(g.body_plain,''))) >= %s",
             """NOT EXISTS (SELECT 1 FROM email_documents e
                             WHERE e.message_id = g.message_id AND e.role = 'body')"""]
    params = [MIN_BODY]
    if args.message_id:
        where.append("g.message_id = ANY(%s)"); params.append(args.message_id)
    if args.since:
        where.append("g.received_at >= %s"); params.append(args.since)
    if args.until:
        where.append("g.received_at < %s"); params.append(args.until)
    params.append(args.limit)

    cur.execute(f"""
        SELECT g.id, g.message_id, g.thread_id, g.subject, g.body_plain, g.from_addr, g.from_name,
               g.to_addrs, g.cc_addrs, g.sent_at, g.received_at, g.case_file, g.has_attachments,
               coalesce(g.account, 'jonathan@hayuma.org') AS account,
               EXISTS (SELECT 1 FROM email_documents ea
                        WHERE ea.message_id = g.message_id AND ea.role = 'attachment') AS has_attach_links
          FROM gmail_messages g
         WHERE {' AND '.join(where)}
         ORDER BY g.received_at DESC LIMIT %s""", params)
    msgs = cur.fetchall()
    mode = "DRY-RUN (no writes)" if dry else "LIVE"
    print(f"  [email-bodies {mode}] {len(msgs)} case-relevant email(s) without a body document\n")

    created = linked = covers = 0
    for m in msgs:
        text = _compose_text(m)
        chash = hashlib.sha256(text.encode()).hexdigest()
        title = f"Email — {(m['subject'] or '(no subject)')[:140]}"
        fname = f"EMAIL_{(m['received_at'] or m['sent_at'] or '').__str__()[:10]}_{_slug(m['subject'])}.txt"

        # significance: same engine as attachments; body-specific cover_message flag on top
        sig = extract_signals(regs, m["case_file"], {"subject": m["subject"], "body": m["body_plain"]})
        if m["has_attach_links"] and ATTACH_REF_RE.search((m["subject"] or "") + " " + (m["body_plain"] or "")):
            sig["flags"]["cover_message"] = True     # composition relevance: cover message for exhibits
            covers += 1

        if dry:
            am = apply_enrichment(cur, None, sig, dry=True)
            tag = "COVER" if sig["flags"].get("cover_message") else "body "
            print(f"    NEW {tag} {m['case_file']:<12} {(m['subject'] or '')[:52]:<54} {_sig_summary(sig, am)}")
            created += 1
            continue

        cur.execute("SELECT id FROM documents WHERE content_hash = %s LIMIT 1", (chash,))
        ex = cur.fetchone()
        if ex:  # identical composed text already a document → just link this message to it
            doc_id = ex["id"]; linked += 1
        else:
            cur.execute("""
                INSERT INTO documents
                  (case_file, matter_code, original_filename, smart_filename, document_title, document_type,
                   extracted_text, text_length, content_hash, sha256, mime_type, status, master_form,
                   ingest_status, ingest_source, ocr_used, doc_date, doc_date_norm, doc_date_quality, created_at)
                VALUES (%s, NULL, %s, %s, %s, 'Email',
                        %s, %s, %s, %s, 'text/plain', 'ingested_from_email', 'digital',
                        'ingested', 'gmail_body', false, %s, %s, 'email_header', now())
                RETURNING id
            """, (m["case_file"], fname, fname, title, text, len(text), chash, chash,
                  str(m["sent_at"].date()) if m["sent_at"] else None,
                  m["sent_at"].date() if m["sent_at"] else None))
            doc_id = cur.fetchone()["id"]; created += 1
        cur.execute("""INSERT INTO email_documents (message_id, doc_id, role, filename)
                       VALUES (%s, %s, 'body', %s)
                       ON CONFLICT (message_id, doc_id) DO NOTHING""",
                    (m["message_id"], doc_id, fname))
        am = apply_enrichment(cur, doc_id, sig, dry)
        if created % 50 == 0 and created:
            print(f"    ✓ {created} body documents...")

    verb = "would be created" if dry else "created"
    print(f"\n  Summary [{mode}]:")
    print(f"    body documents {verb}: {created}")
    print(f"    linked to existing doc (same composed text): {linked}")
    print(f"    cover messages flagged (composition relevance): {covers}")
    if dry:
        print("\n  DRY-RUN — nothing written.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
