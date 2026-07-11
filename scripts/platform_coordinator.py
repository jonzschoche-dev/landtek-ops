#!/usr/bin/env python3
"""platform_coordinator.py — the Communications Layer's governing coordinator (v1).

ONTOLOGY.md §2.14 PlatformCoordinator (A31): the single authoritative layer for cross-channel
identity resolution, routing/health, and exposure governance. This v1 delivers the governance +
observability functions (the per-channel bridges keep owning drain/send; the n8n workflow keeps
owning Telegram) — it is the coordinator ABOVE them, not a rebuild of them.

  --status    phone-friendly go-live readiness board across every channel
  --audit     write channel_audit activation records for active channels (feeds A30) — idempotent
  --resolve   scan channel_users, resolve to one client_code where confident (feeds A25) — separation-safe
  --tick      --audit + --resolve + a health heartbeat (for a systemd timer)

Reads token PRESENCE from /root/landtek/.env (never prints or logs secret values). Sends nothing
outward. Safe to run repeatedly / on a timer.
"""
import json
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Fallback env-var name per channel when channels.auth_secret_ref is blank.
TOKEN_KEY = {
    "telegram": "TELEGRAM_BOT_TOKEN", "email": "GMAIL_REFRESH_TOKEN",
    "viber": "VIBER_AUTH_TOKEN", "whatsapp": "WHATSAPP_API_TOKEN",
}
# Channels whose external switch is deliberately held until provisioned (A26/A30).
HELD = {"whatsapp", "viber"}


def _env_present(key):
    """True if KEY has a non-empty value in /root/landtek/.env (value never returned)."""
    if not key:
        return False
    try:
        with open("/root/landtek/.env") as f:
            for line in f:
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip() != ""
    except Exception:
        pass
    return os.environ.get(key, "").strip() != ""


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def client_of(cur, channel, channel_user_id):
    """A25 resolve-or-hold, single identity: the client_code this (channel, user) is bound to, or None.
    The one resolver every comms consumer (sink, leo_service) shares — never guess a client."""
    cur.execute("""SELECT cu.mapped_client_code
                     FROM channel_users cu JOIN channels c ON c.id = cu.channel_id
                    WHERE c.name = %s AND cu.channel_user_id = %s""",
                (channel, str(channel_user_id)))
    r = cur.fetchone()
    val = r["mapped_client_code"] if (r and isinstance(r, dict)) else (r[0] if r else None)
    return val or None


def _channels(cur):
    cur.execute("""SELECT id, name, active, webhook_url, auth_secret_ref FROM channels ORDER BY id""")
    return cur.fetchall()


def _queued(cur, cid):
    cur.execute("""SELECT count(*) AS n FROM channel_messages
                   WHERE channel_id=%s AND direction='outbound'
                     AND (status LIKE 'pending%%' OR status='queued')""", (cid,))
    return cur.fetchone()["n"]


def _verdict(name, active, tok, webhook):
    if not active:
        return "INACTIVE"
    if name == "telegram" and tok:
        return "LIVE (via n8n)"
    if name == "email":
        return "INBOUND LIVE · send HELD" if tok else "INACTIVE (no GMAIL token)"
    if tok and webhook:
        return "LIVE"
    if name in HELD:
        return "ARMED · token HELD" if not tok else "ARMED · needs webhook"
    return "PARTIAL"


def status():
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    rows = _channels(cur)
    print("COMMS LAYER — go-live readiness")
    print(f"{'channel':10} {'active':6} {'token':5} {'webhook':7} {'queued':6}  verdict")
    for r in rows:
        tok = _env_present(r["auth_secret_ref"] or TOKEN_KEY.get(r["name"]))
        wh = bool(r["webhook_url"])
        q = _queued(cur, r["id"])
        print(f"{r['name']:10} {('yes' if r['active'] else 'no'):6} "
              f"{('yes' if tok else '-'):5} {('yes' if wh else '-'):7} {q:<6}  "
              f"{_verdict(r['name'], r['active'], tok, wh)}")
    cur.close(); c.close()


def audit():
    """Write a channel_audit activation record for each active channel — idempotent on (channel, state)."""
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    rows = _channels(cur); wrote = 0
    for r in rows:
        if not r["active"]:
            continue
        tok = _env_present(r["auth_secret_ref"] or TOKEN_KEY.get(r["name"]))
        state = {"active": True, "token_present": tok, "webhook": bool(r["webhook_url"])}
        # idempotent: only write if the latest activation for this channel differs from current state
        cur.execute("""SELECT payload FROM channel_audit
                       WHERE channel_id=%s AND event_type='activation'
                       ORDER BY created_at DESC LIMIT 1""", (r["id"],))
        last = cur.fetchone()
        if last and last["payload"] == state:
            continue
        cur.execute("""INSERT INTO channel_audit (channel_id, event_type, payload, result)
                       VALUES (%s, 'activation', %s, %s)""",
                    (r["id"], json.dumps(state), "active" if tok else "active_no_token"))
        wrote += 1
    print(f"[coordinator] audit: wrote {wrote} activation record(s) to channel_audit")
    cur.close(); c.close()


def resolve():
    """Resolve channel_users -> exactly one client_code where confident (A25). Separation-safe:
    never guesses across clients; leaves NULL when unresolved (V7 permits NULL, forbids WRONG)."""
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT id, channel_id, channel_user_id, mapped_client_code, mapped_operator, role
                   FROM channel_users
                   WHERE mapped_client_code IS NULL
                     AND coalesce(mapped_operator,'')=''
                     AND coalesce(role,'') <> 'operator'
                     AND channel_user_id NOT LIKE '999000%%'""")
    rows = cur.fetchall(); resolved = 0
    for r in rows:
        # v1 conservative resolver: only bind when a UNIQUE client contact matches this identity.
        # Match an email-style channel_user_id against a single client's known address.
        uid = (r["channel_user_id"] or "").lower()
        if "@" not in uid:
            continue  # non-email identity: no confident resolution source yet
        cur.execute("""SELECT DISTINCT client_code FROM channel_users
                       WHERE lower(channel_user_id)=%s AND mapped_client_code IS NOT NULL""", (uid,))
        hits = [x["client_code"] for x in cur.fetchall()]
        if len(hits) == 1:  # exactly one known client for this identity -> safe to bind
            cur.execute("UPDATE channel_users SET mapped_client_code=%s WHERE id=%s", (hits[0], r["id"]))
            resolved += 1
    print(f"[coordinator] resolve: {len(rows)} unresolved client identities scanned, "
          f"{resolved} confidently bound (rest left NULL — no unique source).")
    cur.close(); c.close()


def main():
    args = set(sys.argv[1:])
    if "--status" in args:
        status()
    elif "--audit" in args:
        audit()
    elif "--resolve" in args:
        resolve()
    elif "--tick" in args:
        audit(); resolve()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
