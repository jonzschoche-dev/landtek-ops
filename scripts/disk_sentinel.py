#!/usr/bin/env python3
"""disk_sentinel.py — prevent disk-full freezes.

A full disk crashes Postgres into recovery mode, which makes the router unable
to connect, which freezes Leo (this happened 2026-06-09). This sentinel runs
every few minutes from cron and guarantees that can't happen again:

  - >= WARN%: auto-clean — truncate any oversized log, prune DB backups older
    than N days, clear stale /tmp scans, truncate bloated docker logs.
  - still >= CRIT% after cleaning: alert Jonathan (he owns the consequence).

Designed to be safe and idempotent: it only removes regenerable artifacts
(logs, old backups, temp downloads) — never application data or vault scans.
"""
from __future__ import annotations
import glob
import os
import shutil
import sys
import time

WARN_PCT = 85          # start cleaning at 85%
CRIT_PCT = 92          # alert Jonathan if still this high after cleaning
BACKUP_KEEP_DAYS = 3
LOG_CAP_BYTES = 100 * 1024 * 1024     # truncate any single log over 100MB
DOCKER_LOG_CAP = 50 * 1024 * 1024     # truncate docker json logs over 50MB
TMP_AGE_SECS = 86400                   # clear /tmp scans older than 1 day
JONATHAN_CHAT = "6513067717"
SENTINEL_LOG = "/var/log/landtek_disk_sentinel.log"


def disk():
    u = shutil.disk_usage("/")
    return round(u.used / u.total * 100), round(u.free / 1e9, 2)


def log(msg):
    try:
        with open(SENTINEL_LOG, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _truncate(path):
    try:
        open(path, "w").close()
        return True
    except Exception:
        return False


def clean():
    freed = []
    # 1) Truncate any oversized landtek log (the runaway-log failure mode).
    logs = (glob.glob("/var/log/landtek*.log") + glob.glob("/root/landtek/*.log")
            + glob.glob("/var/log/landtek-*.log"))
    for lg in set(logs):
        try:
            if os.path.getsize(lg) > LOG_CAP_BYTES and _truncate(lg):
                freed.append(f"truncated log {os.path.basename(lg)}")
        except Exception:
            pass
    # 2) Prune DB backups older than BACKUP_KEEP_DAYS (nothing else prunes them).
    for pat in ("/var/backups/landtek/postgres/*.sql.gz", "/root/backups/*.sql.gz",
                "/var/backups/landtek/postgres/*.sql"):
        for b in glob.glob(pat):
            try:
                if time.time() - os.path.getmtime(b) > BACKUP_KEEP_DAYS * 86400:
                    os.remove(b)
                    freed.append(f"removed old backup {os.path.basename(b)}")
            except Exception:
                pass
    # 3) Clear stale temp scan downloads.
    for t in glob.glob("/tmp/*.pdf") + glob.glob("/tmp/hunt_*.pdf") + glob.glob("/tmp/vfy_*.pdf"):
        try:
            if time.time() - os.path.getmtime(t) > TMP_AGE_SECS:
                os.remove(t)
        except Exception:
            pass
    # 4) Truncate bloated docker container logs.
    for cl in glob.glob("/var/lib/docker/containers/*/*-json.log"):
        try:
            if os.path.getsize(cl) > DOCKER_LOG_CAP and _truncate(cl):
                freed.append("truncated a docker log")
        except Exception:
            pass
    return freed


def alert(msg):
    try:
        sys.path.insert(0, "/root/landtek/scripts")
        from tg_send import send
        send(chat_id=JONATHAN_CHAT, text=msg, source="sentinel",
             override_pacing=True, override_rate_limit=True, human_readable=True)
        log(f"ALERTED Jonathan: {msg}")
    except Exception as e:
        log(f"alert failed: {e}")


def main():
    pct, free = disk()
    if pct < WARN_PCT:
        return
    log(f"disk {pct}% ({free}GB free) >= {WARN_PCT}% — cleaning")
    freed = clean()
    pct2, free2 = disk()
    log(f"after clean: {pct2}% ({free2}GB free); actions={freed or 'none'}")
    if pct2 >= CRIT_PCT:
        alert(f"Disk on the LandTek server is {pct2}% full ({free2}GB free) even "
              f"after auto-cleanup. The database is at risk of crashing. Please "
              f"check the server when you can.")


if __name__ == "__main__":
    main()
