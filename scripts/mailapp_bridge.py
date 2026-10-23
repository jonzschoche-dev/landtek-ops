#!/usr/bin/env python3
"""mailapp_bridge.py — feed office correspondence from Mail.app into gmail_messages. Runs on the MAC. Never sends.

Why (found 23 Oct 2026): the Gmail API token for jonzschoche@gmail.com died ~22 Sep (invalid_grant), so the
VPS stopped ingesting the inbox every MWK drip goes out from. For a month no reply, acknowledgment or sent
letter reached the database, and every board, clock and brief was blind. Mail.app on the Mac still syncs
both mailboxes over IMAP, so this bridge reads them there.

What it does:
  1. for each account (jonzschoche@gmail.com, jonathan@hayuma.org), lists "All Mail" since a watermark;
  2. keeps only office / case correspondence (government domains, the drip's known office addresses,
     case keywords) — promotions and personal mail never leave the Mac;
  3. inserts each kept message into gmail_messages (message_id 'mailapp:<Message-ID>', idempotent),
     tagged raw_payload.source='mailapp_bridge' so the Gmail-API ingest can dedupe once it is re-minted.

  python3 scripts/mailapp_bridge.py [--since 2026-09-20] [--dry-run]
MANUAL FALLBACK ONLY (Jonathan, 23 Oct: Mail.app can't be the backbone — the Mac is not always on or
reachable). The scheduled path is the VPS: landtek-drip-nightly.timer pulls jonzschoche via the Gmail API.
Use this only while that token is dead. Needs PG_DSN (default: the Mac tunnel 127.0.0.1:15432).
"""
import argparse
import email.utils
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@127.0.0.1:15432/n8n")
ACCOUNTS = ["jonzschoche@gmail.com", "jonathan@hayuma.org"]
DEFAULT_SINCE = "2026-09-20"
RS, US = "\x1e", "\x1f"

OFFICE_DOMAIN_RE = re.compile(r"@([a-z0-9.-]+\.)?(gov\.ph|judiciary\.gov\.ph|landbank\.com|op\.gov\.ph)\b", re.I)
KEYWORD_RE = re.compile(r"keesey|worrick|balane|t-?4497|t-?32917|t-?52540|t-?32911|mercedes|camarines norte|"
                        r"barangay|sanggunian|\bctn\b|arta|ombudsman|dilg|denr|penro|cenro|assessor|treasurer|"
                        r"registry of deeds|clerk of court|notarial|inocalla|paracale|lis pendens|26-360|6839|2680",
                        re.I)

LIST_SCRIPT = r'''
on run argv
  set acctAddr to item 1 of argv
  set i0 to (item 2 of argv) as integer
  set i1 to (item 3 of argv) as integer
  set RS to (character id 30)
  set US to (character id 31)
  set out to ""
  with timeout of 1200 seconds
    tell application "Mail"
      set acct to missing value
      repeat with a in accounts
        if (email addresses of a) contains acctAddr then set acct to contents of a
      end repeat
      if acct is missing value then return ""
      set mb to missing value
      repeat with x in (mailboxes of acct)
        if name of x is "All Mail" then set mb to contents of x
      end repeat
      if mb is missing value then
        repeat with x in (mailboxes of acct)
          repeat with z in (mailboxes of x)
            if name of z is "All Mail" then set mb to contents of z
          end repeat
        end repeat
      end if
      if mb is missing value then return ""
      set n to count of messages of mb
      if i0 > n then return ""
      if i1 > n then set i1 to n
      set ms to (a reference to (messages i0 thru i1 of mb))
      set mids to message id of ms
      set snds to sender of ms
      set subs to subject of ms
      set dts to date received of ms
      set tos to address of to recipients of ms
      set ccs to address of cc recipients of ms
    end tell
  end timeout
  repeat with i from 1 to (count of mids)
    set dr to item i of dts
    set ds to ((year of dr) as string) & "-" & ((month of dr as integer) as string) & "-" & ((day of dr) as string) & " " & ((time of dr) as string)
    set AppleScript's text item delimiters to ","
    set toL to (item i of tos) as string
    set ccL to (item i of ccs) as string
    set AppleScript's text item delimiters to ""
    set out to out & (item i of mids) & US & (item i of snds) & US & toL & US & ccL & US & (item i of subs) & US & ds & US & "0" & RS
  end repeat
  return out
end run
'''

BODY_SCRIPT = r'''
on run argv
  set acctAddr to item 1 of argv
  set mid to item 2 of argv
  with timeout of 600 seconds
  tell application "Mail"
    repeat with a in accounts
      if (email addresses of a) contains acctAddr then
        repeat with x in (mailboxes of a)
          if name of x is "All Mail" then
            set ms to (messages of x whose message id is mid)
            if (count of ms) > 0 then return ((count of mail attachments of item 1 of ms) as string) & (character id 31) & (content of item 1 of ms)
          end if
        end repeat
      end if
    end repeat
  end tell
  end timeout
  return ""
end run
'''


def osa(script, *args, timeout=900):
    p = subprocess.run(["osascript", "-", *args], input=script, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[-300:])
    return p.stdout.rstrip("\n")


def known_office_addresses(cur):
    """Every address the drip has written to or heard from — the bridge keeps their mail even off-domain."""
    addrs = set()
    cur.execute("SELECT to_address, cc_addresses FROM step_plan")
    for r in cur.fetchall():
        for a in [r["to_address"], *(r["cc_addresses"] or [])]:
            if a:
                addrs.add(a.lower().strip())
    cur.execute("SELECT detail FROM drip_event WHERE kind IN ('sent','reply','receipt','drafted')")
    for r in cur.fetchall():
        for v in (r["detail"] or {}).values():
            for a in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", json.dumps(v)):
                addrs.add(a.lower())
    return addrs - set(ACCOUNTS)


def parse_local(ds):
    """Mail.app gives local wall-clock time; gmail_messages stores naive UTC."""
    date_part, _, secs = ds.partition(" ")
    y, mo, d = (int(x) for x in date_part.split("-"))
    local = datetime(y, mo, d) + timedelta(seconds=int(secs or 0))
    return local.astimezone().astimezone(timezone.utc).replace(tzinfo=None)


def addr_of(s):
    return (email.utils.parseaddr(s or "")[1] or "").lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    known = known_office_addresses(cur)
    total_new = 0
    for acct in ACCOUNTS:
        since = a.since
        if not since:
            cur.execute("""SELECT max(received_at) m FROM gmail_messages
                            WHERE account=%s AND raw_payload->>'source'='mailapp_bridge'""", (acct,))
            m = cur.fetchone()["m"]
            since = (m - timedelta(days=2)).strftime("%Y-%m-%d") if m else DEFAULT_SINCE
        cutoff = parse_local(since + " 0")
        rows, i0, CH = [], 1, 150
        while True:   # newest first: read chunks from the top until a chunk reaches past the cutoff
            raw = osa(LIST_SCRIPT, acct, str(i0), str(i0 + CH - 1), timeout=1300)
            chunk = [r.split(US) for r in raw.split(RS) if r.strip()]
            if not chunk:
                break
            rows += [r for r in chunk if len(r) >= 7 and parse_local(r[5]) >= cutoff]
            if any(len(r) >= 7 and parse_local(r[5]) < cutoff for r in chunk) or len(chunk) < CH:
                break
            i0 += CH
        kept = []
        for r in rows:
            if len(r) < 7:
                continue
            mid, sender, to_l, cc_l, subj, ds, natt = r[:7]
            to_a = [x.lower() for x in to_l.split(",") if x]
            cc_a = [x.lower() for x in cc_l.split(",") if x]
            parties = {addr_of(sender), *to_a, *cc_a} - set(ACCOUNTS)
            hit = (any(OFFICE_DOMAIN_RE.search(p) for p in parties) or (parties & known)
                   or KEYWORD_RE.search(subj or ""))
            if hit:
                kept.append((mid, sender, to_a, cc_a, subj, ds, int(natt or 0)))
        new = 0
        for mid, sender, to_a, cc_a, subj, ds, natt in kept:
            key = "mailapp:" + mid
            cur.execute("SELECT 1 FROM gmail_messages WHERE message_id=%s", (key,))
            if cur.fetchone():
                continue
            if a.dry_run:
                new += 1
                continue
            got = osa(BODY_SCRIPT, acct, mid, timeout=700)
            natt_s, _, body = got.partition(US)
            natt = int(natt_s) if natt_s.isdigit() else 0
            body = body[:100000]
            name, addr = email.utils.parseaddr(sender)
            when = parse_local(ds)
            cur.execute("""INSERT INTO gmail_messages (message_id, from_addr, from_name, to_addrs, cc_addrs, subject,
                               body_plain, sent_at, received_at, has_attachments, ingested_at, provenance_level,
                               raw_payload, relevance_status, account)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now() at time zone 'utc','inferred_strong',%s,'unlinked',%s)
                           ON CONFLICT (message_id) DO NOTHING""",
                        (key, addr.lower() or sender, name or None, to_a, cc_a, subj, body, when, when, natt > 0,
                         json.dumps({"source": "mailapp_bridge", "rfc_message_id": mid, "attachments": natt}), acct))
            new += cur.rowcount
        if not a.dry_run:
            c.commit()
        total_new += new
        print(f"{acct}: since {since}: {len(rows)} messages scanned, {len(kept)} office/case, {new} new")
    print(f"total new: {total_new}{' (dry run)' if a.dry_run else ''}")


if __name__ == "__main__":
    sys.exit(main())
