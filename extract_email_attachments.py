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

INGEST-TIME SIGNIFICANCE (the avant-garde layer, 2026-07-09): every new document is enriched at ingest with
GROUNDED signals — deterministic matches of the filename + parent-email envelope against live registries
(matters/dockets+deadlines, the 77-title map, the 20 transferees). NEVER an LLM opinion; every signal records
what matched and where. Writes: documents.reference_numbers + .parties (only when NULL — never clobber) +
analyst_memo.ingest_signals (versioned jsonb, provenance inferred_strong). A single DOCKET-EXACT matter hit in
the email's own client auto-sets matter_code (the doctrine-approved auto-link); multi-docket → flagged, never
dual-assigned. Registry hits from a DIFFERENT client are a cross_client FLAG (possible mis-file, A5/A54
tripwire), never significance. `composition_candidate` flags annex/exhibit bundles for document_parts.

MODES:
  (default)          extract attachments from case-relevant, not-yet-extracted emails
  --dry-run          fetch + hash but WRITE NOTHING; report NEW vs LINKED(existing hash) vs SKIPPED per file
  --backfill-linker  one-shot: create missing email_documents rows for gmail_messages.document_id links
  --enrich-backfill  apply ingest_signals enrichment to ALREADY-ingested email-attachment docs

TARGETING (for testing):
  --message-id ID    (repeatable) only these gmail message_ids
  --since YYYY-MM-DD / --until YYYY-MM-DD   received_at window
  --limit N          cap emails scanned (default 200)
"""
import argparse, base64, hashlib, json, os, re, sys
from datetime import date, timedelta
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
UPLOADS = "/root/landtek/uploads"          # legacy landing zone (pre-2026-07-09 ingests live here)
FILES_ROOT = "/root/landtek/files"         # canonical: files/{case_file}/{year}/general/original/
MAX_WARN_BYTES = 25 * 1024 * 1024  # log (don't skip) attachments larger than this
URGENT_WINDOW_DAYS = 45            # a matched matter with a deadline inside this window is flagged urgent
SIGNALS_VERSION = 4  # v2: aliases (810) · v3: text pool + leads + text_hash (812) · v4: multi-client registry scoping + ...2126 et al added (813)
TEXT_POOL_CAP = 250_000  # chars of extracted_text scanned per doc (guards degenerate mega-docs)


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


# ────────────────────────────────────────────────────────────────────────────────────────────────
# INGEST-TIME SIGNIFICANCE ENGINE — deterministic, registry-grounded, zero LLM calls.
# ────────────────────────────────────────────────────────────────────────────────────────────────

def load_registries(cur):
    """Load the live registries the significance engine matches against. Once per run.
    Each matter expands into docket_number + docket_aliases needles (aliases are CURATED exact strings —
    court-caption phrasing like 'Civil Case No. 26-360' for registry docket 'CV-2026-360' — so the
    docket-exact discipline holds; deploy_810)."""
    cur.execute("""SELECT matter_code, case_file, docket_number, status, next_deadline, next_event, title,
                          coalesce(docket_aliases, '{}') AS docket_aliases
                     FROM matters
                    WHERE (docket_number IS NOT NULL AND docket_number <> '')
                       OR coalesce(array_length(docket_aliases, 1), 0) > 0""")
    matters = cur.fetchall()
    # titles/transferees carry their OWN case_file (deploy_813: the registry is no longer all-MWK — e.g.
    # T-1722 is Inocalla/Paracale-001) → matching is scoped per-row, cross-client hits become tripwire flags.
    cur.execute("SELECT tct_number, coalesce(case_file,'MWK-001') AS case_file FROM titles WHERE tct_number IS NOT NULL")
    tcts = cur.fetchall()
    cur.execute("SELECT canonical_name, coalesce(case_file,'MWK-001') AS case_file FROM transferees WHERE canonical_name IS NOT NULL")
    names = cur.fetchall()
    return {"matters": matters, "tcts": tcts, "transferees": names}


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).upper().strip()


# Post-OCR text extras (v3): patterns that only make sense INSIDE document text. Still deterministic —
# these produce LEADS (unknown refs = registry-expansion candidates), clearly separated from registry hits.
TCT_PAT = re.compile(r"\b(?:0?79-\d{10,13}|[TO]-\d{4,6})\b")
DOCKET_PAT = re.compile(r"\b(?:CTN\s+SL-\d{4}-\d{4}-\d{3,4}|SL-\d{4}-\d{4}-\d{3,4}"
                        r"|CIVIL CASE NO\.?\s*[\w-]{2,12}|SP(?:EC(?:IAL)?\.?)?\s*PROC(?:EEDING)?\.?\s*(?:NO\.?\s*)?\d{2,6}"
                        r"|CRIMINAL CASE NO\.?\s*[\w-]{2,12}|G\.?R\.?\s*NO\.?\s*\d{4,7})\b")
EXHIBIT_SERIES_PAT = re.compile(r"\b(?:ANNEX|EXHIBIT)\s+[\"“']?([A-Z]{1,2}(?:-\d{1,3})?|\d{1,3}(?:-[A-Z])?)[\"”']?\b")


def extract_text_extras(sig, text, known_tcts, known_dockets):
    """v3 depth: scan extracted_text for structured references BEYOND the registries.
    unknown_titles/unknown_dockets are LEADS for registry expansion (never treated as verified links);
    references_exhibits = the exhibit/annex series the text itself cites → bundle/composition depth."""
    t = _norm(text[:TEXT_POOL_CAP])
    if not t:
        return sig
    known_t = {_norm(k) for k in known_tcts}
    known_d = {_norm(k) for k in known_dockets}
    unk_t = sorted({m for m in TCT_PAT.findall(t) if _norm(m) not in known_t})[:25]
    unk_d = sorted({m.strip() for m in DOCKET_PAT.findall(t)
                    if not any(kd in _norm(m) or _norm(m) in kd for kd in known_d)})[:25]
    series = []
    for lab in EXHIBIT_SERIES_PAT.findall(t):
        if lab not in series:
            series.append(lab)
    if unk_t:
        sig["unknown_titles"] = unk_t          # title-map expansion leads
    if unk_d:
        sig["unknown_dockets"] = unk_d         # matter-registry expansion leads
    if len(series) >= 2:                       # a doc citing an exhibit SERIES is a bundle/filing-main candidate
        sig["references_exhibits"] = series[:40]
        sig["flags"]["cites_exhibit_series"] = True
    return sig


def extract_signals(regs, case_file, texts):
    """Match the doc's textual envelope against the registries. `texts` = {'filename':…,'subject':…,'body':…}.
    Returns a signals dict where EVERY entry is a grounded observation (registry value + where it matched).
    Client scope (A5/A54): a hit whose registry row belongs to a DIFFERENT client than the email is recorded
    under cross_client (a possible-mis-file tripwire), never as significance."""
    pools = {k: _norm(v[:TEXT_POOL_CAP] if k == "text" else v) for k, v in texts.items() if v}
    sig = {"version": SIGNALS_VERSION, "provenance": "inferred_strong",
           "basis": "deterministic registry match (filename + parent-email envelope)",
           "matter_hits": [], "title_hits": [], "party_hits": [], "flags": {}, "cross_client": []}

    # 1. Matters — DOCKET-EXACT only (docket_number OR a curated alias; never fuzzy-title matching).
    for mt in regs["matters"]:
        needles = [mt["docket_number"]] + list(mt.get("docket_aliases") or [])
        matched_needle, where = None, []
        for nd in needles:
            ndn = _norm(nd)
            if len(ndn) < 6:       # refuse degenerate dockets (e.g. 'T-4497' handled by title matching)
                continue
            w = [k for k, p in pools.items() if ndn in p]
            if w:
                matched_needle, where = nd, w
                break
        if not where:
            continue
        hit = {"matter_code": mt["matter_code"], "docket": matched_needle, "status": mt["status"],
               "next_deadline": str(mt["next_deadline"]) if mt["next_deadline"] else None,
               "matched_in": where}
        if mt["case_file"] and case_file and mt["case_file"] != case_file:
            sig["cross_client"].append({"kind": "matter", **hit, "owner_case_file": mt["case_file"]})
        else:
            if mt["next_deadline"] and mt["next_deadline"] <= date.today() + timedelta(days=URGENT_WINDOW_DAYS):
                hit["urgent"] = True
            sig["matter_hits"].append(hit)

    # 2. Known titles — matched per the TITLE's own client (registry is multi-client since deploy_813).
    for tr in regs["tcts"]:
        tn = _norm(tr["tct_number"])
        if len(tn) < 5:
            continue
        where = [k for k, p in pools.items() if tn in p]
        if where:
            entry = {"tct": tr["tct_number"], "matched_in": where}
            if case_file == tr["case_file"]:
                sig["title_hits"].append(entry)
            else:
                sig["cross_client"].append({"kind": "title", **entry, "owner_case_file": tr["case_file"]})

    # 3. Transferees (named parties of interest) — same per-row client scoping.
    for nr in regs["transferees"]:
        nn = _norm(nr["canonical_name"])
        where = [k for k, p in pools.items() if nn in p]
        if where:
            entry = {"name": nr["canonical_name"], "matched_in": where}
            if case_file == nr["case_file"]:
                sig["party_hits"].append(entry)
            else:
                sig["cross_client"].append({"kind": "party", **entry, "owner_case_file": nr["case_file"]})

    # 4. Composition + integrity flags.
    fn_subj = (pools.get("filename", "") + " " + pools.get("subject", ""))
    if re.search(r"ANNEX|EXHIBIT|BUNDLE|ENCLOSURE", fn_subj):
        sig["flags"]["composition_candidate"] = True     # likely multi-part → document_parts later
    own_dockets = {h["matter_code"] for h in sig["matter_hits"]}
    if len(own_dockets) > 1:
        sig["flags"]["multi_docket"] = sorted(own_dockets)  # flag, NEVER dual-assign (docket-exact rule)
    if sig["cross_client"]:
        sig["flags"]["cross_client"] = True
    return sig


def apply_enrichment(cur, doc_id, sig, dry):
    """Persist signals. reference_numbers/parties are refreshed when WE own them (the doc already carries
    ingest_signals) or when NULL — a pre-engine hand-written value is never clobbered. analyst_memo.ingest_signals
    is replaced with the newest version; matter_code auto-set ONLY on a single same-client docket hit."""
    refs = {}
    if sig["matter_hits"] or sig["title_hits"]:
        refs = {"dockets": [h["docket"] for h in sig["matter_hits"]],
                "tct_numbers": [h["tct"] for h in sig["title_hits"]]}
    parties = {"transferees": [h["name"] for h in sig["party_hits"]]} if sig["party_hits"] else {}
    auto_matter = None
    own = {h["matter_code"] for h in sig["matter_hits"]}
    if len(own) == 1 and "multi_docket" not in sig["flags"]:
        auto_matter = own.pop()

    if dry:
        return auto_matter
    cur.execute("""
        UPDATE documents SET
          reference_numbers = CASE WHEN (reference_numbers IS NULL OR analyst_memo ? 'ingest_signals')
                                    AND %s::jsonb <> '{}'::jsonb
                                   THEN %s::jsonb ELSE reference_numbers END,
          parties           = CASE WHEN (parties IS NULL OR analyst_memo ? 'ingest_signals')
                                    AND %s::jsonb <> '{}'::jsonb
                                   THEN %s::jsonb ELSE parties END,
          analyst_memo      = coalesce(analyst_memo,'{}'::jsonb) || jsonb_build_object('ingest_signals', %s::jsonb),
          matter_code       = coalesce(matter_code, %s)
        WHERE id = %s
    """, (json.dumps(refs), json.dumps(refs), json.dumps(parties), json.dumps(parties),
          json.dumps(sig, default=str), auto_matter, doc_id))
    return auto_matter


def _sig_summary(sig, auto_matter):
    bits = []
    if sig["matter_hits"]:
        bits.append("matters:" + ",".join(h["matter_code"] + ("⚠" if h.get("urgent") else "") for h in sig["matter_hits"]))
    if sig["title_hits"]:
        bits.append("titles:" + ",".join(h["tct"] for h in sig["title_hits"][:4]))
    if sig["party_hits"]:
        bits.append("parties:" + ",".join(h["name"].split()[-1] for h in sig["party_hits"][:4]))
    for f in sig["flags"]:
        bits.append("FLAG:" + f)
    if auto_matter:
        bits.append("→matter_code=" + auto_matter)
    return "; ".join(bits) if bits else "no registry signals"


def enrich_backfill(cur, dry, limit, refresh=False):
    """Enrich ALREADY-ingested email-attachment docs (all linked emails' envelopes pooled per doc).
    refresh=True re-computes signals for docs whose ingest_signals are from an older SIGNALS_VERSION."""
    regs = load_registries(cur)
    gate = ("AND coalesce((d.analyst_memo->'ingest_signals'->>'version')::int, 0) < %s" if refresh
            else "AND (d.analyst_memo IS NULL OR NOT d.analyst_memo ? 'ingest_signals')")
    params = ([SIGNALS_VERSION, limit] if refresh else [limit])
    cur.execute(f"""
        SELECT d.id, d.case_file, d.original_filename,
               string_agg(DISTINCT g.subject, ' | ')   AS subjects,
               string_agg(g.body_plain, ' ')           AS bodies
          FROM documents d
          JOIN email_documents e ON e.doc_id = d.id
          JOIN gmail_messages g  ON g.message_id = e.message_id
         WHERE (d.ingest_source = 'gmail_attachment' OR d.status = 'ingested_from_email')
           {gate}
         GROUP BY d.id ORDER BY d.id LIMIT %s""", params)
    docs = cur.fetchall()
    mode = "DRY-RUN" if dry else "LIVE"
    print(f"  [enrich-backfill {mode}] {len(docs)} email-attachment doc(s) lacking ingest_signals\n")
    for d in docs:
        sig = extract_signals(regs, d["case_file"],
                              {"filename": d["original_filename"], "subject": d["subjects"], "body": d["bodies"]})
        am = apply_enrichment(cur, d["id"], sig, dry)
        print(f"    doc {d['id']:<5} {(d['original_filename'] or '')[:42]:<44} {_sig_summary(sig, am)}")
    if dry:
        print("\n  DRY-RUN — nothing written.")


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
    ap.add_argument("--enrich-backfill", action="store_true",
                    help="apply ingest_signals enrichment to already-ingested email-attachment docs")
    ap.add_argument("--refresh", action="store_true",
                    help="with --enrich-backfill: re-enrich docs whose signals predate SIGNALS_VERSION")
    args = ap.parse_args()
    dry = args.dry_run

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.backfill_linker:
        backfill_linker(cur, dry)
        cur.close(); conn.close(); return
    if args.enrich_backfill:
        enrich_backfill(cur, dry, args.limit, refresh=args.refresh)
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
        SELECT id, message_id, subject, body_plain, from_addr, attachment_refs, case_file, received_at,
               coalesce(account, 'jonathan@hayuma.org') AS account
          FROM gmail_messages
         WHERE {' AND '.join(where)}
         ORDER BY received_at DESC LIMIT %s
    """, params)
    msgs = cur.fetchall()
    regs = load_registries(cur)  # significance registries, once per run
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

            # significance signals from the doc's textual envelope (grounded; also shown in dry-run)
            sig = extract_signals(regs, m["case_file"],
                                  {"filename": fn, "subject": m["subject"], "body": m["body_plain"]})

            if dry:
                am = apply_enrichment(cur, None, sig, dry=True)  # no writes; just resolve auto-matter
                print(f"    NEW   {m['case_file']:<12} {(fn or 'unnamed')[:44]}  ({size} b){big}")
                print(f"          ↳ {_sig_summary(sig, am)}")
                inserted += 1
                continue

            # CANONICAL storage: files/{case_file}/{year}/general/original/ (original bytes, never modified;
            # derived/stamped versions are generated later by the exhibit builder, not here)
            safe_fn = _safe_name(fn, idx)
            yr = str(m["received_at"].year) if m.get("received_at") else "undated"
            target_dir = os.path.join(FILES_ROOT, m["case_file"], yr, "general", "original")
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
            am = apply_enrichment(cur, new_id, sig, dry)
            print(f"    ✓ doc {new_id} {(fn or 'unnamed')[:40]} — {_sig_summary(sig, am)}")
            inserted += 1

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
