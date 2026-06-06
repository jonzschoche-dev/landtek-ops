#!/usr/bin/env python3
"""email_briefer.py - proactive critical-email push to Jonathan.

Runs every 15 min via systemd timer. Three jobs:

  1. RECONCILE — re-run matter-code linkage on any gmail_messages row that
     came in since last successful run and is still unlinked. Idempotent:
     leverages the same regex / sender allowlist that deploy_261 used.

  2. CRITICAL PUSH — for any UNREAD high-priority email in the last 30 min,
     push a Telegram message to Jonathan with subject + sender + link to the
     leo.hayuma.org dashboard. "Critical" means EITHER:
       - sender in CRITICAL_SENDERS allowlist (ARTA, court, DILG, CSC,
         Barandon, opposing counsel)
       - subject matches CRITICAL_SUBJECT_REGEX (CTN SL-, [Order, Resolution-,
         Civil Case, hearing, notice, deadline)

  3. DAILY EMAIL DIGEST — once per day at 7am Manila (paired with the
     calendar_briefer's morning brief), include a "Inbox last 24h" section
     in a separate Telegram message: count by sender, top subjects, anything
     still unlinked.

Deduplication via email_briefs_sent table.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
ENV_PATH = "/root/landtek/.env"
JONATHAN_CHAT_ID = "6513067717"
LOG_PATH = "/var/log/landtek/email_briefer.log"
MANILA_TZ = timezone(timedelta(hours=8))

CRITICAL_SENDERS_RE = re.compile(
    r"(arta\.gov\.ph|judiciary\.gov\.ph|csc\.gov\.ph|dilg.*gmail|penro|denr|mgb|"
    r"barandon|botor|yuzon|pajarillo|mercedes\.gov|camnortepao|@sb\.judiciary|"
    r"@sc\.judiciary|@ca\.judiciary)",
    re.IGNORECASE,
)
CRITICAL_SUBJECT_RE = re.compile(
    r"(\[order|\[osca\]|\[urgent|resolution[-\s]|"
    r"ctn\s*sl[-\s]|civil\s+case|crim\.?\s+case|"
    r"notice\s+of|hearing|deadline|subpoena|"
    r"motion\s+for|order\s+dated|writ\s+of|"
    r"complaint|petition|affidavit)",
    re.IGNORECASE,
)

# Inline matter-code linkage rules (mirrors deploy_226/261)
CTN_RE = re.compile(
    r"\bCTN\s*s?\s*[-:]?\s*SL\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{3,4})\b",
    re.IGNORECASE,
)
CV_KNOWN = {
    "26-360": "MWK-CV26360",
    "26360":  "MWK-CV26360",
    "6839":   "MWK-CV6839",
    "6922":   "MWK-PARALLEL-CV6922",
    "13-131220": "PAR-CV13-131220",
    "8563":   "MWK-CV26360",  # Juntilla et al. v Donata King (predecessor of CA-181607)
}
# Senders that almost-always belong to a specific matter:
SENDER_DEFAULT_MATTER = {
    "barandon_lawoffice@yahoo.com": "MWK-CV26360",
    "colenacious@yahoo.com":        "MWK-CV26360",
    "dilgcamarinesnorte2020@gmail.com": "MWK-ARTA-DILG",
    "lourdestotanes@yahoo.com":     "MWK-CV26360",
}


def log(msg):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(LOG_PATH, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")


def load_bot_token():
    with open(ENV_PATH) as f:
        for line in f:
            for k in ("TELEGRAM_BOT_TOKEN", "TG_BOT_TOKEN", "BOT_TOKEN"):
                if line.startswith(k + "="):
                    return line.split("=", 1)[1].strip().strip('"\'')
    return None


def send_telegram(token, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": JONATHAN_CHAT_ID,
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return bool(json.loads(resp.read()).get("ok")), ""
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.read().decode('utf-8','ignore')[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS email_briefs_sent (
            id              SERIAL PRIMARY KEY,
            email_id        INTEGER REFERENCES gmail_messages(id) ON DELETE CASCADE,
            brief_type      TEXT NOT NULL CHECK (brief_type IN
                              ('critical_push','daily_digest')),
            brief_date      DATE,
            sent_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            telegram_ok     BOOLEAN,
            UNIQUE (email_id, brief_type),
            UNIQUE (brief_type, brief_date)
        );
        CREATE INDEX IF NOT EXISTS idx_email_briefs_email ON email_briefs_sent(email_id);
    """)


def derive_matters(from_addr, subject, body):
    """Shared sanitize rules (correspondence_spine.sanitize_gmail_matter_codes)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from correspondence_spine import sanitize_gmail_matter_codes

    return set(
        sanitize_gmail_matter_codes(
            from_addr=from_addr,
            subject=subject,
            body_plain=body,
            matter_codes=[],
        )
    )


def fetch_valid_matter_codes(cur):
    cur.execute("SELECT matter_code FROM matters")
    return {r["matter_code"] for r in cur.fetchall()}


# ─── Job 1: reconcile unlinked emails ────────────────────────────────────
def job_reconcile(cur):
    valid = fetch_valid_matter_codes(cur)
    cur.execute("""
        SELECT id, from_addr, subject, COALESCE(body_plain, '') AS body
          FROM gmail_messages
         WHERE cardinality(COALESCE(matter_codes, '{}'::text[])) = 0
         ORDER BY ingested_at DESC
         LIMIT 500
    """)
    rows = cur.fetchall()
    updated = 0
    for r in rows:
        mcs = derive_matters(r["from_addr"], r["subject"], r["body"])
        mcs = sorted(m for m in mcs if m in valid)
        if mcs:
            cur.execute("UPDATE gmail_messages SET matter_codes = %s WHERE id = %s",
                        (mcs, r["id"]))
            updated += 1
    log(f"  reconcile: {updated}/{len(rows)} now linked")
    return updated


# ─── Job 2: critical push ────────────────────────────────────────────────
def job_critical_push(cur, token, dry_run=False, window_min=30):
    """Push high-priority inbound from the last window."""
    cur.execute("""
        SELECT g.id, g.ingested_at, g.from_addr, g.from_name, g.subject, g.matter_codes
          FROM gmail_messages g
         WHERE g.ingested_at >= now() - (%s || ' minutes')::interval
           AND NOT EXISTS (
                 SELECT 1 FROM email_briefs_sent b
                  WHERE b.email_id = g.id AND b.brief_type = 'critical_push'
               )
         ORDER BY g.ingested_at DESC
    """, (window_min,))
    rows = cur.fetchall()
    sent = 0
    for r in rows:
        subject = r["subject"] or ""
        from_addr = r["from_addr"] or ""
        is_crit_sender = bool(CRITICAL_SENDERS_RE.search(from_addr))
        is_crit_subject = bool(CRITICAL_SUBJECT_RE.search(subject))
        if not (is_crit_sender or is_crit_subject):
            continue

        def esc(s):
            if not s:
                return ""
            return (str(s).replace("&", "&amp;")
                          .replace("<", "&lt;")
                          .replace(">", "&gt;"))

        mc_str = ", ".join(r["matter_codes"] or []) or "(unlinked — check)"
        manila_ts = r["ingested_at"].astimezone(MANILA_TZ).strftime("%H:%M")
        reason = []
        if is_crit_sender:
            reason.append("critical sender")
        if is_crit_subject:
            reason.append("critical subject")
        msg = (
            f"📧 <b>Inbound — {manila_ts}</b>\n\n"
            f"<b>From:</b> {esc((r['from_name'] or from_addr))[:80]}\n"
            f"<b>Subject:</b> {esc(subject)[:120]}\n"
            f"<b>Matter:</b> {esc(mc_str)}\n"
            f"<b>Why pushed:</b> {esc(' + '.join(reason))}"
        )
        if dry_run:
            log(f"  [DRY] critical push email#{r['id']} subject={subject[:60]!r}")
            continue
        ok, err = send_telegram(token, msg)
        cur.execute("""
            INSERT INTO email_briefs_sent (email_id, brief_type, telegram_ok)
            VALUES (%s, 'critical_push', %s)
            ON CONFLICT DO NOTHING
        """, (r["id"], ok))
        log(f"  critical push email#{r['id']} ok={ok} err={(err or '')[:60]}")
        sent += 1
    return sent


# ─── Job 3: daily digest ─────────────────────────────────────────────────
def job_daily_digest(cur, token, dry_run=False, force=False):
    now_utc = datetime.now(timezone.utc)
    now_manila = now_utc.astimezone(MANILA_TZ)
    if not force and not (6 <= now_manila.hour <= 8):
        return 0
    brief_date = now_manila.date()
    cur.execute("SELECT 1 FROM email_briefs_sent WHERE brief_type='daily_digest' AND brief_date=%s",
                (brief_date,))
    if not force and cur.fetchone():
        return 0

    # Last 24h
    cur.execute("""
        SELECT id, ingested_at, from_addr, from_name, subject, matter_codes
          FROM gmail_messages
         WHERE ingested_at >= now() - INTERVAL '24 hours'
         ORDER BY ingested_at DESC
    """)
    rows = cur.fetchall()
    if not rows:
        return 0

    linked = [r for r in rows if (r["matter_codes"] or [])]
    unlinked = [r for r in rows if not (r["matter_codes"] or [])]

    lines = [f"📬 <b>Inbox digest — {brief_date.strftime('%a %b %-d')}</b>"]
    lines.append(f"Last 24h: {len(rows)} ingested ({len(linked)} linked, {len(unlinked)} unlinked)")

    def esc(s):
        if not s:
            return ""
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    if linked:
        lines.append("")
        lines.append(f"<b>Matter-linked ({len(linked)})</b>")
        for r in linked[:8]:
            mc = ", ".join(r["matter_codes"] or [])
            lines.append(f"  • [{esc(mc)}] {esc(r['subject'] or '(no subject)')[:80]}")
            lines.append(f"      from {esc(r['from_name'] or r['from_addr'] or '?')[:50]}")
    if unlinked:
        lines.append("")
        lines.append(f"<b>Unlinked ({len(unlinked)})</b> — may need manual review")
        for r in unlinked[:6]:
            lines.append(f"  • {esc(r['subject'] or '(no subject)')[:100]}")
            lines.append(f"      from {esc(r['from_name'] or r['from_addr'] or '?')[:50]}")

    msg = "\n".join(lines)
    if dry_run:
        log(f"  [DRY] daily digest:\n{msg}")
        return 1
    ok, err = send_telegram(token, msg)
    cur.execute("""
        INSERT INTO email_briefs_sent (email_id, brief_type, brief_date, telegram_ok)
        VALUES (NULL, 'daily_digest', %s, %s)
        ON CONFLICT DO NOTHING
    """, (brief_date, ok))
    log(f"  daily digest {brief_date} ok={ok}")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-daily", action="store_true")
    ap.add_argument("--window-min", type=int, default=30,
                    help="Critical-push lookback window in minutes")
    ap.add_argument("--only", choices=["reconcile", "critical", "digest"])
    args = ap.parse_args()

    token = load_bot_token()
    if not token and not args.dry_run:
        log("FATAL: no bot token")
        sys.exit(1)

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)

    summary = {}
    if args.only in (None, "reconcile"):
        summary["reconciled"] = job_reconcile(cur)
    if args.only in (None, "critical"):
        summary["critical_pushes"] = job_critical_push(cur, token, args.dry_run, args.window_min)
    if args.only in (None, "digest"):
        summary["daily_digest"] = job_daily_digest(cur, token, args.dry_run, args.force_daily)

    cur.close()
    conn.close()
    log(f"summary: {summary}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
