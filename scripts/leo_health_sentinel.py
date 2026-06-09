#!/usr/bin/env python3
"""leo_health_sentinel.py — detect + auto-recover a frozen Leo, and alert.

Both 2026-06-09 freezes (a DB lock, then a disk-full DB crash) went UNDETECTED
because the old connection sentinel watches n8n executions, which Leo no longer
uses. This watches the REAL pipeline — Postgres + the Python Telegram router —
and acts within ~2 minutes:

  - DB unreachable        -> alert Jonathan (a DB outage can't be auto-fixed).
  - tg service not active -> restart it + alert.
  - inbox backlog stale   -> the router is stalled -> restart it + alert.

Alerts are de-duped (10-min window) so it never spams. Runs every 2 min via cron.
The goal is simple: Leo must never freeze silently again — it self-heals where it
can and tells Jonathan immediately where it can't.
"""
from __future__ import annotations
import subprocess
import sys
import time

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN = "6513067717"
STALE_MIN = 4
SVCS = ["landtek-tg-router", "landtek-tg-inbox"]
STATE = "/var/run/leo_health_sentinel.state"
DEDUP_SECS = 600


def alert(msg):
    try:
        sys.path.insert(0, "/root/landtek/scripts")
        from tg_send import send
        send(chat_id=JONATHAN, text=msg, source="sentinel",
             override_pacing=True, override_rate_limit=True, human_readable=True)
    except Exception:
        pass


def recently_alerted(key):
    try:
        with open(STATE) as f:
            for line in f:
                k, t = line.strip().split("|")
                if k == key and time.time() - float(t) < DEDUP_SECS:
                    return True
    except FileNotFoundError:
        pass
    return False


def mark(key):
    lines = []
    try:
        with open(STATE) as f:
            lines = [l for l in f
                     if l.strip() and time.time() - float(l.strip().split("|")[1]) < 3600]
    except FileNotFoundError:
        pass
    lines.append(f"{key}|{time.time()}\n")
    try:
        with open(STATE, "w") as f:
            f.writelines(lines)
    except Exception:
        pass


def svc_active(svc):
    return subprocess.run(["systemctl", "is-active", svc],
                          capture_output=True, text=True).stdout.strip() == "active"


def main():
    # 1) Database reachable?
    try:
        conn = psycopg2.connect(DSN, connect_timeout=8)
        conn.autocommit = True
        cur = conn.cursor()
    except Exception as e:
        if not recently_alerted("db_down"):
            alert("Leo health: the database is unreachable, so Leo is frozen. "
                  "This needs a look at the server (often disk-full or a DB crash) "
                  f"- I can't auto-fix a database outage. Detail: {str(e)[:70]}")
            mark("db_down")
        return

    # 2) Telegram services up?
    dead = [s for s in SVCS if not svc_active(s)]
    if dead:
        for s in dead:
            subprocess.run(["systemctl", "restart", s], capture_output=True)
        if not recently_alerted("svc_dead"):
            alert(f"Leo health: {', '.join(dead)} was down - I restarted it "
                  "automatically. Leo should be back. Flagging so you know.")
            mark("svc_dead")
        cur.close(); conn.close()
        return

    # 3) Inbox backlog stale -> router stalled -> restart it.
    cur.execute(
        "SELECT count(*) FROM telegram_inbox "
        "WHERE processed_at IS NULL AND received_at < now() - interval %s",
        (f"{STALE_MIN} minutes",))
    stale = cur.fetchone()[0]
    cur.close(); conn.close()
    if stale > 0:
        subprocess.run(["systemctl", "restart", "landtek-tg-router"], capture_output=True)
        if not recently_alerted("router_stuck"):
            alert(f"Leo health: {stale} message(s) sat unprocessed for over "
                  f"{STALE_MIN} minutes - the router was stalled. I restarted it "
                  "automatically; Leo should be catching up now.")
            mark("router_stuck")


if __name__ == "__main__":
    main()
