#!/usr/bin/env python3
"""imap_ingest.py — onboard a NON-Gmail mailbox (Outlook / Google-Workspace IMAP) into the corpus.

The corpus was single-account (jonzschoche@gmail via the Gmail API), which is why correspondence on
other mailboxes was invisible. This adds a GENERIC IMAP path so any mailbox feeds the SAME pipeline:
  envelope + body  -> gmail_messages (registry, matter-tagged)
  each email body  -> a dated 'correspondence' document (so it lands in case_file + cross-references)
  attachments      -> documents  (content-hash dedup, OCR-pending, separation-safe matter links)
Reuses blend_emails for text-extraction / dedup / storage / the client-separation guard.

Credentials live ONLY in /root/landtek/.env (chmod 600, NEVER committed):
  HOTMAIL_IMAP_USER / HOTMAIL_IMAP_PASS   (jonpeezee@hotmail.com — Outlook app password)
  HAYUMA_IMAP_USER  / HAYUMA_IMAP_PASS    (jonathan@hayuma.org   — Google-Workspace app password)

  imap_ingest.py --list-accounts
  imap_ingest.py --account hotmail --search balane --matter MWK-CV26360 --since 01-Jan-2023   # DRY-RUN
  imap_ingest.py --account hotmail --search balane --matter MWK-CV26360 --since 01-Jan-2023 --apply
  imap_ingest.py --account hayuma  --search "Zschoche OR Keesey OR Worrick" --apply
"""
from __future__ import annotations
import argparse, email, hashlib, imaplib, os, re, sys
import datetime as dt
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek"); sys.path.insert(0, "/root/landtek/scripts")
import blend_emails as B

ACCOUNTS = {
    "hotmail": {"host": "imap-mail.outlook.com", "port": 993, "email": "jonpeezee@hotmail.com",
                "user_env": "HOTMAIL_IMAP_USER", "pass_env": "HOTMAIL_IMAP_PASS",
                "folders": ["INBOX", "Sent"]},
    "hayuma":  {"host": "imap.gmail.com", "port": 993, "email": "jonathan@hayuma.org",
                "user_env": "HAYUMA_IMAP_USER", "pass_env": "HAYUMA_IMAP_PASS",
                "folders": ['"[Gmail]/All Mail"']},
}

# matter attribution (separation-safe — same dockets/signals as find_missing_record, + a Balane hook)
DOCKET_MAP = {"SL-2026-0209-1319": "MWK-ARTA-1319", "SL-2026-0209-1321": "MWK-ARTA-1321",
              "SL-2026-0128-1210": "MWK-ARTA-1210", "SL-2026-0128-1212": "MWK-ARTA-1212",
              "SL-2026-0218-1378": "MWK-ARTA-1378"}
DOCKET_RE = re.compile(r"SL-20\d\d-\d{4}-\d{3,4}")
MWK_SIGNAL = re.compile(r"lot 2-a|psd-221861|psd-229480|t-32911|t-4497|worrick|keesey|mercedes cadastre", re.I)
BALANE_SIGNAL = re.compile(r"balane", re.I)   # the 26-360 accion reinvindicatoria (an MWK matter)


def _dec(s):
    if not s:
        return ""
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s


def _attribute(blob, default_matter):
    """Matter tags from the message. --matter overrides; else docket-exact, then Balane, then MWK signal.
    Never crosses the client line (Balane -> MWK-CV26360 is an MWK matter)."""
    if default_matter:
        return [default_matter]
    m = sorted({DOCKET_MAP[k] for k in DOCKET_RE.findall(blob) if k in DOCKET_MAP})
    if not m and BALANE_SIGNAL.search(blob):
        m = ["MWK-CV26360"]
    if not m and MWK_SIGNAL.search(blob):
        m = ["MWK-001"]
    return m


def _parse(raw, meta_line):
    msg = email.message_from_bytes(raw)
    mid = (msg.get("Message-ID") or "").strip() or "imap-" + hashlib.sha256(raw).hexdigest()[:24]
    try:
        sent = parsedate_to_datetime(msg.get("Date")).replace(tzinfo=None)
    except Exception:
        sent = None
    recv = None                                  # the TRUE receipt = IMAP INTERNALDATE (never the borne date)
    try:
        tup = imaplib.Internaldate2tuple(meta_line)
        if tup:
            recv = dt.datetime(*tup[:6])
    except Exception:
        recv = None
    body, atts = "", []
    for part in msg.walk():
        if part.is_multipart():
            continue
        fn = _dec(part.get_filename())
        disp = (part.get("Content-Disposition") or "").lower()
        if fn or "attachment" in disp:
            try:
                data = part.get_payload(decode=True)
            except Exception:
                data = None
            if data:
                atts.append({"filename": fn or "attachment", "mime": part.get_content_type(),
                             "size": len(data), "data": data})
        elif part.get_content_type() == "text/plain" and not body:
            try:
                body = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "ignore")
            except Exception:
                body = ""
    return {"message_id": mid, "thread_id": msg.get("In-Reply-To") or None, "subject": _dec(msg.get("Subject")),
            "from_addr": _dec(msg.get("From")), "from_name": _dec(msg.get("From")), "to_addrs": _dec(msg.get("To")),
            "sent_at": sent, "received_at": recv, "body": (body or "").strip(), "attachments": atts}


def _upsert_msg(cur, g, matters):
    cur.execute("""INSERT INTO gmail_messages
          (message_id, thread_id, from_addr, to_addrs, subject, body_plain, sent_at, received_at,
           has_attachments, matter_codes, relevance_score, relevance_status, provenance_level, ingested_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1.0,'imap_ingest','inferred_strong',now())
        ON CONFLICT (message_id) DO UPDATE SET
          body_plain = COALESCE(gmail_messages.body_plain, EXCLUDED.body_plain),
          matter_codes = CASE WHEN COALESCE(array_length(gmail_messages.matter_codes,1),0) > 0
                              THEN gmail_messages.matter_codes ELSE EXCLUDED.matter_codes END""",
        (g["message_id"], g["thread_id"], g["from_addr"], ([g["to_addrs"]] if g["to_addrs"] else None),
         g["subject"], g["body"] or None, g["sent_at"], g["received_at"], bool(g["attachments"]), matters))


def _ingest_doc(cur, g, matters, src, *, fn, data, mime, is_body=False):
    """Insert/dedup ONE artifact (an attachment, or the email body as a correspondence doc).
    Mirrors blend_emails.blend_email's insert + the separation guard (client from validated matter tags)."""
    raw = data if isinstance(data, bytes) else (data or "").encode("utf-8", "ignore")
    chash = hashlib.sha256(raw).hexdigest()
    existing, how = B.find_existing(cur, chash)
    matter1 = matters[0] if matters else None
    case_file = next((c for p, c in B.CLIENT_OF.items() if matter1 and matter1.startswith(p)), None)
    if existing:
        for mc in matters:
            cur.execute("INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s) ON CONFLICT DO NOTHING", (existing, mc))
        return existing, "dedup"
    path = os.path.join(B.STORE, f"{B.safe_name(g['message_id'])}__{B.safe_name(fn)}")
    with open(path, "wb") as fh:
        fh.write(raw)
    if is_body:
        txt, classification, mime = (data or ""), "correspondence", "text/plain"
    else:
        txt, classification = B.extract_text(data, mime, path), None
    bdate = B.borne_date(txt)
    emeta = {"source": src, "email_message_id": g["message_id"], "email_from": g["from_name"],
             "email_sent_at": str(g["sent_at"]) if g["sent_at"] else None,
             "email_received_at": str(g["received_at"]) if g["received_at"] else None}
    cur.execute("""INSERT INTO documents
        (master_form, ingest_source, original_filename, smart_filename, mime_type, file_path, content_hash,
         doc_date, doc_date_quality, case_file, matter_code, classification, extracted_text, execution_metadata)
        VALUES ('digital',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (src, fn, fn, mime, path, chash, bdate, ("content_weak" if bdate else None), case_file,
         matter1, classification, (txt or None), psycopg2.extras.Json(emeta)))
    did = cur.fetchone()["id"]
    cur.execute("INSERT INTO email_documents (message_id, doc_id, role, filename) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (g["message_id"], did, "body" if is_body else "attachment", fn))
    for mc in matters:
        cur.execute("INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s) ON CONFLICT DO NOTHING", (did, mc))
    return did, ("body" if is_body else "attachment")


def scrape(acct_name, search, matter, since, apply):
    acct = ACCOUNTS[acct_name]
    user = os.environ.get(acct["user_env"]); pwd = os.environ.get(acct["pass_env"])
    if not (user and pwd):
        sys.exit(f"[imap] missing {acct['user_env']} / {acct['pass_env']} in /root/landtek/.env")
    conn = psycopg2.connect(B.DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor); B.ensure_schema(cur)
    mode = "APPLY" if apply else "DRY-RUN"
    M = imaplib.IMAP4_SSL(acct["host"], acct["port"]); M.login(user, pwd)
    crit = []
    if since:
        crit += ["SINCE", since]
    if search:
        crit += ["TEXT", search]
    crit = crit or ["ALL"]
    print(f"[imap] {acct_name} ({acct['email']}) search={crit} ({mode})")
    seen = set(); msgs = made = link = 0
    for folder in acct["folders"]:
        try:
            typ, _ = M.select(folder, readonly=True)
            if typ != "OK":
                continue
        except Exception:
            continue
        typ, res = M.search(None, *crit)
        uids = res[0].split() if (res and res[0]) else []
        print(f"  [{folder}] {len(uids)} match")
        for uid in uids:
            typ, d = M.fetch(uid, "(RFC822 INTERNALDATE)")
            raw = next((p[1] for p in d if isinstance(p, tuple) and isinstance(p[1], (bytes, bytearray))), None)
            meta_line = next((p[0].decode("utf-8", "ignore") for p in d if isinstance(p, tuple) and isinstance(p[0], (bytes, bytearray))), "")
            if not raw:
                continue
            g = _parse(raw, meta_line)
            if g["message_id"] in seen:
                continue
            seen.add(g["message_id"]); msgs += 1
            blob = " ".join(filter(None, [g["subject"], g["body"][:2500], " ".join(a["filename"] for a in g["attachments"])]))
            matters = _attribute(blob, matter)
            tag = ",".join(matters) or "—"
            if not apply:
                print(f"    · {str(g['sent_at'])[:10]} [{tag}] atts={len(g['attachments'])} | {g['from_addr'][:26]} | {g['subject'][:38]}")
                continue
            _upsert_msg(cur, g, matters)
            if g["body"] and len(g["body"]) > 40:
                _, how = _ingest_doc(cur, g, matters, f"imap_{acct_name}",
                                     fn=(B.safe_name(g["subject"])[:50] or "email") + ".txt", data=g["body"], mime="text/plain", is_body=True)
                made += (how != "dedup")
            for a in g["attachments"]:
                if B.is_noise(a):
                    continue
                _, how = _ingest_doc(cur, g, matters, f"imap_{acct_name}", fn=a["filename"], data=a["data"], mime=a["mime"])
                made += (how != "dedup"); link += (how == "dedup")
            print(f"    • [{tag}] {g['subject'][:46]}")
    M.logout()
    print(f"[imap] {acct_name}: {msgs} messages, {made} new docs, {link} dedup-linked ({mode})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", choices=list(ACCOUNTS))
    ap.add_argument("--search", default="")
    ap.add_argument("--matter")
    ap.add_argument("--since", help="IMAP date, e.g. 01-Jan-2023")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--list-accounts", action="store_true")
    a = ap.parse_args()
    if a.list_accounts or not a.account:
        for n, c in ACCOUNTS.items():
            have = bool(os.environ.get(c["user_env"]) and os.environ.get(c["pass_env"]))
            print(f"  {n:8} {c['email']:26} {c['host']}  creds={'SET' if have else 'MISSING ('+c['pass_env']+')'}")
        return
    scrape(a.account, a.search, a.matter, a.since, a.apply)


if __name__ == "__main__":
    main()
