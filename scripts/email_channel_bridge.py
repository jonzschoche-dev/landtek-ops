#!/usr/bin/env python3
"""email_channel_bridge.py — wire Gmail into the omnichannel pipeline (Pillar 7).

The `/api/channel/email` adapter (leo_tools/channel_adapters.py) already normalizes inbound
email → routes through onboarding/agent → queues the reply as `pending_gmail_send`. What was
missing is the FEED (Gmail is polled, not webhooked to us) and the SEND drain. This bridges
both, reusing the already-ingested `gmail_messages` rows and the existing adapter.

  --inbound : new client inbound emails (gmail_messages) → POST /api/channel/email
              Creditless plumbing: routing/onboarding/audit run here; the reply CONTENT is
              produced by the agent (Leo) and is credit-gated, so it simply queues until fuel.
  --send    : drain channel_messages 'pending_gmail_send' → Gmail API send
              Needs gmail.send scope on GMAIL_REFRESH_TOKEN; best-effort (gated on reply content).

Idempotent via an email_bridge_state cursor (first run anchors at current max — no history replay).
"""
import base64
import json
import os
import re
import sys
import urllib.request
from email.mime.text import MIMEText

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:  # outward-action chokepoint (deploy_717)
    import outward_guard
except Exception:
    outward_guard = None

from _pgdsn import dsn as _pgdsn  # noqa: E402
DSN = _pgdsn("172.18.0.3:5432")
ADAPTER = os.environ.get("CHANNEL_EMAIL_URL", "http://localhost:8765/api/channel/email")
JONATHAN_ADDRS = ("jonzschoche@gmail.com", "jonathan@hayuma.org", "jonpeezee@hotmail.com")

# Who may reach Leo's client channel (Jonathan, 24 Oct 2026, after 203 bot replies were found queued to offices, a law
# firm and his own mail): only real client / prospect senders. from_addr is stored with the display name
# ("Jonathan Zschoche <jonzschoche@gmail.com>"), so the address is parsed out before any comparison — the old exact-string
# NOT IN never matched, and 94 of the 203 replies were addressed to Jonathan himself.
ADDR_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
GOV_RX = re.compile(r"(?i)(\.gov(\.[a-z]{2})?$|\.gov\.ph$|judiciary|\.mil(\.ph)?$)")
OFFICE_LOCAL_RX = re.compile(r"(?i)dilg|mlgoo|lgu|municipal|munisipyo|province|provincial|pgo|brgy|barangay|sanggunian|"
                             r"treasur|assessor|denr|penro|cenro|mgb|emb|coa|region\d|records|mayor|governor|registry|"
                             r"deeds|landbank|lbp|ombudsman|arta|csc|blgf")
LAW_RX = re.compile(r"(?i)\blaw\b|law ?office|law ?firm|lawyers?|& ?associates|\batty\b|attorneys?|legal")
AUTO_RX = re.compile(r"(?i)^(no-?reply|do-?not-?reply|donotreply|mailer-daemon|postmaster|notifications?|newsletter|"
                     r"alerts?|info|hello|news|marketing|support|billing|vms-no-reply)@")


def sender_address(from_addr):
    """The bare e-mail address inside a From header ("Name <addr>" or "addr"), lower-cased; None if there is none."""
    m = ADDR_RX.search(from_addr or "")
    return m.group(0).lower() if m else None


def office_addresses(cur):
    """Addresses that must never reach Leo: every address the drip has written to or heard from (ladder offices), and
    every person Jonathan has himself written to from his own accounts (family, heirs, partners, counsel, officials on
    private mailboxes): they are in a conversation with him, not cold prospects. Registered client contacts
    (channel_users with a mapped client) are let back in."""
    cur.execute("SELECT detail::text AS t FROM drip_event")
    found = {a.lower() for r in cur.fetchall() for a in ADDR_RX.findall(r["t"] or "")}
    cur.execute("""SELECT coalesce(to_addrs::text,'') || ' ' || coalesce(cc_addrs::text,'') AS t FROM gmail_messages
                    WHERE from_addr ~* 'jonzschoche|hayuma\\.org|jonpeezee'""")
    found |= {a.lower() for r in cur.fetchall() for a in ADDR_RX.findall(r["t"] or "")}
    cur.execute("""SELECT channel_user_id FROM channel_users WHERE mapped_client_code IS NOT NULL AND authorized""")
    clients = {sender_address(r["channel_user_id"]) for r in cur.fetchall()} - {None}
    return found - set(JONATHAN_ADDRS) - clients


def route_decision(from_addr, office_addrs=frozenset()):
    """(route?, reason). Only real client/prospect senders route; never us, offices, law firms or automated mail."""
    addr = sender_address(from_addr)
    if not addr:
        return False, "no address"
    local, _, domain = addr.partition("@")
    if addr in JONATHAN_ADDRS:
        return False, "our own mail"
    if GOV_RX.search(domain):
        return False, "government domain"
    if addr in office_addrs:
        return False, "drip-ladder office or existing correspondent"
    if OFFICE_LOCAL_RX.search(local) or OFFICE_LOCAL_RX.search(domain.split(".")[0]):
        return False, "office mailbox"
    if LAW_RX.search(from_addr or "") or "law" in domain:
        return False, "law firm"
    if AUTO_RX.search(addr):
        return False, "automated sender"
    return True, "client/prospect"


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS email_bridge_state (
        id int PRIMARY KEY DEFAULT 1, last_gmail_id bigint DEFAULT 0, updated_at timestamptz DEFAULT now())""")
    cur.execute("SELECT coalesce(max(id),0) FROM gmail_messages")
    cur.execute("INSERT INTO email_bridge_state (id,last_gmail_id) VALUES (1,(SELECT coalesce(max(id),0) FROM gmail_messages)) ON CONFLICT (id) DO NOTHING")


def inbound():
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor); ensure(cur)
    cur.execute("SELECT last_gmail_id FROM email_bridge_state WHERE id=1")
    cursor = cur.fetchone()["last_gmail_id"]
    cur.execute("""SELECT id, message_id, from_addr, subject, left(coalesce(body_plain,''),4000) AS body
                     FROM gmail_messages
                    WHERE id > %s AND coalesce(body_plain,'') <> ''
                    ORDER BY id ASC LIMIT 100""", (cursor,))
    rows = cur.fetchall()
    offices = office_addresses(cur)
    sent = maxid = 0
    skipped = {}
    for r in rows:
        maxid = max(maxid, r["id"])
        ok, why = route_decision(r["from_addr"], offices)
        if not ok:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        payload = {"from": r["from_addr"], "subject": r["subject"] or "",
                   "body": r["body"], "message_id": r["message_id"] or ""}
        try:
            req = urllib.request.Request(ADAPTER, data=json.dumps(payload).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=30).read()
            sent += 1
        except Exception as e:
            print(f"  ! {r['from_addr']}: {str(e)[:80]}")
    if maxid:
        cur.execute("UPDATE email_bridge_state SET last_gmail_id=%s, updated_at=now() WHERE id=1", (maxid,))
    print(f"[email_bridge] inbound: routed {sent}/{len(rows)} new client emails to the channel adapter; skipped {skipped}; "
          f"cursor->{maxid or cursor}")
    cur.close(); c.close()


def send():
    """Drain queued replies via Gmail. Best-effort; needs gmail.send scope."""
    try:
        sys.path.insert(0, "/root/landtek/scripts")
        from gmail_watcher import gmail_client
        svc = gmail_client()
    except Exception as e:
        print(f"[email_bridge] send: gmail client unavailable ({str(e)[:80]}) — replies stay queued")
        return
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT id, channel_user_id, text_content, metadata
                     FROM channel_messages
                    WHERE direction='outbound' AND status='pending_gmail_send'
                    ORDER BY id ASC LIMIT 50""")
    rows = cur.fetchall(); done = 0
    offices = office_addresses(cur)
    for r in rows:
        ok, why = route_decision(r["channel_user_id"], offices)
        if not ok:   # same rule as inbound: never a reply to us, an office, a law firm or an automated sender
            cur.execute("UPDATE channel_messages SET status='held_not_client', metadata=coalesce(metadata,'{}'::jsonb)"
                        " || jsonb_build_object('held_reason', %s) WHERE id=%s", (why, r["id"]))
            continue
        try:
            meta = r["metadata"] or {}
            mime = MIMEText(r["text_content"] or "")
            mime["To"] = r["channel_user_id"]
            mime["Subject"] = (meta.get("subject") if isinstance(meta, dict) else None) or "Re:"
            # Outward chokepoint (deploy_717) — shadow logs; block holds an un-approved outward email.
            if outward_guard is not None:
                try:
                    _d, _gi = outward_guard.guard("email", r["channel_user_id"],
                                                  source="email_channel_bridge",
                                                  preview=(r["text_content"] or "")[:200])
                except Exception:
                    _d = "allow"
                if _d == "hold":
                    cur.execute("UPDATE channel_messages SET status='held_outward' WHERE id=%s", (r["id"],))
                    continue
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
            svc.users().messages().send(userId="me", body={"raw": raw}).execute()
            cur.execute("UPDATE channel_messages SET status='sent' WHERE id=%s", (r["id"],))
            done += 1
        except Exception as e:
            print(f"  ! send {r['id']}: {str(e)[:100]}")
    print(f"[email_bridge] send: delivered {done}/{len(rows)} queued replies")
    cur.close(); c.close()


if __name__ == "__main__":
    if "--send" in sys.argv:
        send()
    elif "--inbound" in sys.argv:
        inbound()
    else:
        print(__doc__)
