#!/usr/bin/env python3
"""Gmail watcher — pull new messages, classify, file appropriately (deploy 119).

Usage:
  python3 gmail_watcher.py                              # incremental pull (since last_ingested)
  python3 gmail_watcher.py --query 'ARTA OR DILG'       # focused pull
  python3 gmail_watcher.py --since 2026-04-01           # explicit since
  python3 gmail_watcher.py --max 200                    # cap

Categories assigned:
  legal_correspondence, bill, receipt, bank_statement, client_inquiry,
  system_alert, personal, promotional, uncategorized
"""
import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN_TG_ID = "6513067717"  # legacy reference; outbound now uses comms_recipients
import sys as _sys
_sys.path.insert(0, "/root/landtek")
from comms_recipients import MWK_001_RECIPIENTS

# ── Category detection patterns ────────────────────────────────────────
CATEGORY_PATTERNS = [
    # (category, subject_or_body_regex, signal_weight)
    ("bill", r"(?i)(invoice|amount due|payment due|statement of account|your bill|monthly statement)", 3),
    ("bill", r"(?i)(meralco|globe|pldt|smart|maynilad|manila water|aws|amazon web services|anthropic|openai|google cloud|godaddy|namecheap|digitalocean)", 2),
    ("receipt", r"(?i)(payment received|payment successful|order confirmation|your receipt|transaction completed|or\s*no\.?\s*\d|official receipt)", 3),
    ("bank_statement", r"(?i)(account statement|monthly statement|bpi|bdo|rcbc|security bank|metrobank|landbank|chinabank|unionbank)", 3),
    ("legal_correspondence", r"(?i)(notice of|pre-trial|pretrial|hearing|civil case|motion|affidavit|complaint|judicial|atty\.|attorney|counsel|barandon|botor|RTC|MTC|court order|judgment|decision|deed|special power of attorney|SPA|TCT|OCT)", 3),
    ("legal_correspondence", r"(?i)(arta|dilg|anti-red tape|CTN SL-|pajarillo|macale|mayor of mercedes|land registration authority|register of deeds|RD\s|assessor|treasurer)", 2),
    ("client_inquiry", r"(?i)(would like to (?:hire|engage|retain)|need(?:ing)? legal help|land case|property dispute|inquiry about)", 2),
    ("system_alert", r"(?i)(github|gitlab|aws|cloudwatch|monitor|alert|incident|outage|server)", 1),
    ("promotional", r"(?i)(newsletter|unsubscribe|special offer|discount|promotion|webinar invitation|marketing)", 2),
]


def load_env_credentials():
    env = {}
    with open("/root/landtek/.env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, _, v = line.strip().partition("=")
                env[k.strip()] = v.strip()
    return env


def gmail_client():
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    env = load_env_credentials()
    refresh_token = env["GMAIL_REFRESH_TOKEN"]
    with open("/root/landtek/gmail_oauth_client.json") as f:
        oauth = json.load(f)
    web = oauth.get("web") or oauth.get("installed")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=web["client_id"],
        client_secret=web["client_secret"],
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    from google.auth.transport.requests import Request
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def classify_email(subject, body, from_addr):
    """Return (category, confidence). Multi-vote across patterns."""
    text = f"{subject or ''}\n{(body or '')[:4000]}\n{from_addr or ''}"
    scores = {}
    for cat, pattern, weight in CATEGORY_PATTERNS:
        if re.search(pattern, text):
            scores[cat] = scores.get(cat, 0) + weight
    if not scores:
        return ("uncategorized", 0.3)
    best = max(scores.items(), key=lambda x: x[1])
    total = sum(scores.values())
    return (best[0], min(1.0, best[1] / max(total, 1)))


def extract_bill_metadata(subject, body):
    """For category=bill: extract vendor, amount, due_date."""
    t = f"{subject}\n{body[:6000]}"
    meta = {}
    m = re.search(r"\$\s?([\d,]+\.\d{2})", t) or re.search(r"₱\s?([\d,]+\.\d{2})", t) \
        or re.search(r"PHP\s?([\d,]+\.\d{2})", t, re.IGNORECASE) \
        or re.search(r"(?:total|amount due|balance)[:\s]+(?:php\s?|₱\s?|\$\s?)?([\d,]+\.\d{2})", t, re.IGNORECASE)
    if m:
        meta["amount"] = float(m.group(1).replace(",", ""))
    m = re.search(r"(?:due\s+(?:on|by)|payment due|due date)[:\s]+(?:on\s+)?([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", t, re.IGNORECASE) \
        or re.search(r"(?:due\s+(?:on|by)|due date)[:\s]+(\d{4}-\d{2}-\d{2})", t, re.IGNORECASE)
    if m:
        meta["due_date_raw"] = m.group(1).strip()
        try:
            meta["due_date"] = datetime.strptime(m.group(1).strip().replace(",", ""), "%B %d %Y").date().isoformat()
        except: pass
    # Vendor — try from-domain or common-keyword
    for v in ("Meralco", "Globe", "PLDT", "Smart", "Maynilad", "AWS", "Anthropic", "OpenAI",
              "Google Cloud", "GoDaddy", "DigitalOcean", "BPI", "BDO", "RCBC"):
        if v.lower() in t.lower():
            meta["vendor"] = v; break
    return meta


def decode_part(part):
    """Decode a Gmail message part's body."""
    body = part.get("body", {})
    if body.get("data"):
        try:
            return base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="ignore")
        except: pass
    return ""


def extract_body(payload):
    """Walk payload tree, return (plain, html)."""
    plain, html = "", ""
    parts = payload.get("parts") or [payload]
    stack = list(parts)
    while stack:
        p = stack.pop(0)
        mime = p.get("mimeType", "")
        if mime == "text/plain" and not plain:
            plain = decode_part(p)
        elif mime == "text/html" and not html:
            html = decode_part(p)
        if p.get("parts"):
            stack.extend(p["parts"])
    if not plain and not html and payload.get("body", {}).get("data"):
        plain = decode_part(payload)
    return plain, html


def get_case_keywords(cur):
    cur.execute("SELECT case_file, keyword, weight FROM case_keywords")
    by_case = {}
    for r in cur.fetchall():
        by_case.setdefault(r["case_file"], []).append((r["keyword"].lower(), float(r["weight"])))
    return by_case


def correlate_case(text, by_case):
    """Score email body against case_keywords."""
    text_lower = text.lower()
    scores = {}
    for case, kws in by_case.items():
        if case == "Owner": continue
        score = 0
        for kw, w in kws:
            if kw in text_lower:
                score += text_lower.count(kw) * w
        if score >= 2.0:
            scores[case] = score
    if not scores: return None
    return max(scores.items(), key=lambda x: x[1])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default=None, help="Gmail query (e.g. 'ARTA OR DILG')")
    ap.add_argument("--since", default=None, help="YYYY-MM-DD lower bound")
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--send-tg", action="store_true")
    args = ap.parse_args()

    svc = gmail_client()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Determine since
    since = args.since
    if not since and not args.query:
        cur.execute("SELECT max(received_at) AS m FROM gmail_messages")
        m = cur.fetchone()["m"]
        since = (m - timedelta(days=1)).strftime("%Y/%m/%d") if m else "2025/01/01"
    # Build base query
    base_q = args.query or ""
    if since:
        base_q = f"after:{since.replace('-', '/')} " + base_q if base_q else f"after:{since.replace('-', '/')}"

    # TWO-STREAM PULL per architecture review 2026-05-16:
    # Default `q=after:DATE` returns newest first across all labels — with a 500 cap
    # SENT items can fall off the bottom. Do an explicit `in:sent` pull as well so
    # we never miss outbound case correspondence.
    streams = [
        ("default", base_q),
        ("sent",    f"in:sent {base_q}".strip()),
    ]
    print(f"  base query: {base_q!r}  max per stream: {args.max}")

    msgs = []
    seen_ids = set()
    for label, q in streams:
        try:
            resp = svc.users().messages().list(userId="me", q=q, maxResults=min(500, args.max)).execute()
            stream_msgs = resp.get("messages", [])
            new = [m for m in stream_msgs if m["id"] not in seen_ids]
            seen_ids.update(m["id"] for m in stream_msgs)
            msgs.extend(new)
            print(f"  [{label}] matched: {len(stream_msgs)} ({len(new)} new this stream)")
        except Exception as e:
            print(f"  [{label}] FAILED: {e!r}")
    print(f"  total unique: {len(msgs)} messages")

    by_case = get_case_keywords(cur)
    stats = {}
    inserted = updated = skipped = 0
    actionable = []  # for Telegram digest

    for i, m in enumerate(msgs[:args.max]):
        full = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "")
        from_addr = headers.get("From", "")
        to_addrs = [a.strip() for a in (headers.get("To", "")).split(",") if a.strip()]
        cc_addrs = [a.strip() for a in (headers.get("Cc", "")).split(",") if a.strip()]
        date_str = headers.get("Date", "")
        thread_id = full.get("threadId")
        plain, html = extract_body(full.get("payload", {}))
        labels = full.get("labelIds", [])
        # Attachments
        attachments = []
        for part in (full.get("payload", {}).get("parts") or []):
            if part.get("filename"):
                attachments.append({
                    "filename": part["filename"],
                    "mime": part.get("mimeType"),
                    "size": part.get("body", {}).get("size", 0),
                    "attachmentId": part.get("body", {}).get("attachmentId"),
                })

        category, conf = classify_email(subject, plain, from_addr)
        case_file = correlate_case(f"{subject} {plain}", by_case)
        stats[category] = stats.get(category, 0) + 1

        # Bill metadata if applicable
        bill_meta = extract_bill_metadata(subject, plain) if category == "bill" else {}

        # Upsert
        if args.dry_run:
            print(f"  [DRY] {date_str[:25]:25s}  [{category:18s}]  {(subject or '')[:70]}  case={case_file or '—'}")
            inserted += 1
            continue

        try:
            received_at = datetime.strptime(date_str[:31].strip(), "%a, %d %b %Y %H:%M:%S %z") if date_str else None
        except: received_at = None

        # DEPLOY_297_INGEST_GATE — refuse archive-disposition senders.
        # bare_addr/bare_domain extraction mirrors email_briefer's SQL join logic.
        import re as _re
        _bare_addr = (_re.search(r"<([^>]+)>", from_addr or "") or [None, from_addr or ""])[1].lower()
        _bare_domain = _bare_addr.split("@", 1)[-1] if "@" in _bare_addr else ""
        cur.execute(
            """
            SELECT disposition FROM email_sender_disposition
             WHERE (sender_address = %s OR sender_domain = %s)
               AND disposition = 'archive'
             LIMIT 1
            """,
            (_bare_addr, _bare_domain),
        )
        _disp = cur.fetchone()
        if _disp:
            # Archived sender — write a stub to gmail_messages_archived for audit
            # and skip gmail_messages entirely. The autolink trigger never fires
            # for noise; the digest never sees it.
            cur.execute(
                """
                INSERT INTO gmail_messages_archived
                  (message_id, thread_id, from_addr, to_addrs, cc_addrs, subject,
                   body_plain, body_html, sent_at, received_at, labels,
                   has_attachments, attachment_refs, raw_payload,
                   archived_reason, archived_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
                ON CONFLICT (message_id) DO NOTHING
                """,
                (m["id"], thread_id, from_addr, to_addrs, cc_addrs, subject,
                 plain[:50000], html[:50000] if html else None, received_at, received_at,
                 labels, bool(attachments), json.dumps(attachments) if attachments else None,
                 json.dumps({"category": category, "auto_archived": True}),
                 "ingestion_gate", "gmail_watcher"),
            )
            archived_at_gate = (archived_at_gate if 'archived_at_gate' in dir() else 0) + 1  # noqa
            continue

        cur.execute("""
            INSERT INTO gmail_messages
              (message_id, thread_id, from_addr, to_addrs, cc_addrs, subject,
               body_plain, body_html, sent_at, received_at, labels,
               has_attachments, attachment_refs, case_file,
               relevance_score, relevance_reasons, raw_payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)
            ON CONFLICT (message_id) DO UPDATE SET
              case_file = COALESCE(EXCLUDED.case_file, gmail_messages.case_file),
              labels = EXCLUDED.labels,
              attachment_refs = EXCLUDED.attachment_refs
            RETURNING (xmax = 0) AS is_new
        """, (m["id"], thread_id, from_addr, to_addrs, cc_addrs, subject,
              plain[:50000], html[:50000] if html else None, received_at, received_at,
              labels, bool(attachments), json.dumps(attachments) if attachments else None,
              case_file, conf, [category],
              json.dumps({"category": category, "bill_metadata": bill_meta})))
        is_new = cur.fetchone()["is_new"]
        if is_new: inserted += 1
        else: updated += 1

        # Surface actionable items
        if category in ("bill", "legal_correspondence") and conf >= 0.5:
            actionable.append({
                "category": category, "subject": subject[:120], "from": from_addr[:60],
                "case": case_file, "has_attach": bool(attachments),
                "bill_meta": bill_meta if bill_meta else None,
            })

        if (i+1) % 20 == 0:
            print(f"  ... {i+1}/{len(msgs[:args.max])} processed")
        time.sleep(0.05)  # gentle on API

    # Emit heartbeat
    try:
        cur.execute("""INSERT INTO system_heartbeat (source, status, metadata)
                       VALUES ('gmail-watcher', 'ok', %s::jsonb)""",
                    (json.dumps({"inserted": inserted, "updated": updated,
                                  "by_category": stats, "query": q}),))
    except Exception: pass

    print(f"\n  inserted: {inserted}  updated: {updated}  skipped: {skipped}")
    print(f"  by category:")
    for c, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"    {c:25s}  {n}")

    if args.send_tg and actionable:
        import requests
        env = load_env_credentials()
        lines = [f"📬 <b>Gmail pull: {inserted} new + {updated} updated</b>",
                 f"<i>Query: {q}</i>", "",
                 f"<b>Actionable: {len(actionable)}</b>"]
        for a in actionable[:12]:
            tag = "💰" if a["category"] == "bill" else "⚖️"
            casetag = f" · {a['case']}" if a["case"] else ""
            attach = " 📎" if a["has_attach"] else ""
            lines.append(f"{tag} {a['subject']}")
            lines.append(f"   <i>from {a['from']}{casetag}{attach}</i>")
            bm = a.get("bill_meta") or {}
            if bm.get("amount"):
                lines.append(f"   amount: ₱{bm['amount']:,.2f}"
                             + (f" · due {bm.get('due_date_raw')}" if bm.get('due_date_raw') else ""))
            lines.append("")
        text = "\n".join(lines)
        # chunk
        chunks = []; buf = ""
        for ln in text.split("\n"):
            if len(buf) + len(ln) + 1 > 3800:
                chunks.append(buf); buf = ln
            else:
                buf = buf + ("\n" if buf else "") + ln
        if buf: chunks.append(buf)
        # OPS-ONLY: gmail digest is an operator-facing summary (bill categorization,
        # email triage). It must never reach the client/administrator. Per the
        # 2026-05-19 ops-leak incident — see [[feedback_client_comms_hardcoded]].
        from comms_recipients import OPS_RECIPIENTS
        per_recipient_results = []
        for _name, _cid in OPS_RECIPIENTS:
            ok_count, fail_count = 0, 0
            for c in chunks:
                try:
                    r = requests.post(
                        f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage",
                        json={"chat_id": _cid, "text": c, "parse_mode": "HTML",
                              "disable_web_page_preview": True},
                        timeout=15)
                    j = r.json() if r.content else {}
                    if r.status_code == 200 and j.get("ok"):
                        ok_count += 1
                    else:
                        fail_count += 1
                        print(f"  ✗ TG digest FAIL to {_name}({_cid}): "
                              f"HTTP {r.status_code} — {j.get('description','no-desc')[:120]}")
                except Exception as e:
                    fail_count += 1
                    print(f"  ✗ TG digest EXCEPTION to {_name}({_cid}): {str(e)[:120]}")
            per_recipient_results.append((_name, _cid, ok_count, fail_count))
        for _name, _cid, ok_c, fail_c in per_recipient_results:
            tag = "✓" if fail_c == 0 else ("⚠" if ok_c > 0 else "✗")
            print(f"  {tag} TG digest → {_name} ({_cid}): {ok_c} ok / {fail_c} fail")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
