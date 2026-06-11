#!/usr/bin/env python3
"""fullstack_engineer.py — the always-on full-stack engineer loop. Continuously
watches the whole stack and FIXES it, the way the truth loop watches the data:

  DISK      — if >WARN%, run comprehensive cleanup (journald, prune snapshots>100,
              truncate fat logs, delete unreferenced uploads, /tmp, docker). The exact
              remediation that the disk-full incident needed. Alert if still >CRIT%.
  SERVICES  — every critical daemon must be active; restart any dead one + alert.
  DATABASE  — Postgres reachable; else alert P0.
  PIPELINE  — telegram_inbox not backlogged/stalled.
  ERRORS    — scan recent service logs for tracebacks; surface spikes.

When something is wrong that rules can't cleanly fix, an Opus "senior staff engineer"
diagnoses the gathered state and recommends a fix (logged + alerted, never blindly
applied to anything destructive). Runs as systemd service landtek-fullstack-loop.
"""
import json, os, re, subprocess, sys, time, urllib.request

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
for _l in open("/root/landtek/.env"):
    _l = _l.strip()
    if "=" in _l and not _l.startswith("#"):
        _k, _v = _l.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

PACE = 420          # 7 min between full sweeps
DISK_WARN, DISK_CRIT = 85, 92
CRITICAL = ["landtek-tg-router", "landtek-tg-inbox", "landtek-tg-media",
            "leo-tools", "landtek-corpus-backfill", "landtek-truth-loop",
            "leo-simulator.service"]
OPUS_EVERY = 8       # Opus review every ~1hr (8 * 7min)


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120).stdout.strip()


def alert(text):
    try:
        sys.path.insert(0, "/root/landtek/scripts")
        import tg_send
        tg_send.send("6513067717", text[:280], "watchdog", recipient_name="Jonathan")
    except Exception as e:
        log(f"alert failed: {e}")


def disk_pct():
    out = sh("df -P / | tail -1")
    m = re.search(r"(\d+)%", out)
    return int(m.group(1)) if m else 0


def cleanup_disk():
    actions = []
    sh("journalctl --vacuum-size=150M")
    actions.append("journald->150M")
    sh("docker exec n8n-postgres-1 psql -U n8n -d n8n -c \"DELETE FROM leo_workflow_snapshots WHERE id NOT IN (SELECT id FROM leo_workflow_snapshots ORDER BY id DESC LIMIT 100)\"")
    actions.append("snapshots->100")
    sh("for f in /root/landtek/logs/*.log; do [ $(stat -c%s \"$f\" 2>/dev/null || echo 0) -gt 83886080 ] && truncate -s 20M \"$f\"; done")
    sh("truncate -s 0 /var/log/btmp /var/log/btmp.1 2>/dev/null; find /tmp -type f -mtime +1 -delete 2>/dev/null; find /tmp -name 'bf_*' -delete 2>/dev/null")
    actions.append("logs+tmp")
    # delete unreferenced uploads (canonical refs are documents.file_path)
    try:
        import psycopg2
        c = psycopg2.connect(DSN); cu = c.cursor()
        cu.execute("SELECT file_path FROM documents WHERE file_path LIKE '%/uploads/%'")
        refd = {r[0] for r in cu.fetchall()}
        cu.close(); c.close()
        n = 0
        for root, _, files in os.walk("/root/landtek/uploads"):
            for f in files:
                p = os.path.join(root, f)
                if p not in refd:
                    try: os.remove(p); n += 1
                    except OSError: pass
        if n: actions.append(f"uploads-stale:{n}")
    except Exception as e:
        actions.append(f"uploads-skip:{type(e).__name__}")
    return actions


def check_services():
    dead, restarted, failed = [], [], []
    for s in CRITICAL:
        if sh(f"systemctl is-active {s}") != "active":
            dead.append(s)
            sh(f"systemctl restart {s}")
            time.sleep(2)
            (restarted if sh(f"systemctl is-active {s}") == "active" else failed).append(s)
    return restarted, failed


def db_ok():
    return sh("docker exec n8n-postgres-1 psql -U n8n -d n8n -tAc 'SELECT 1'") == "1"


def inbox_backlog():
    out = sh("docker exec n8n-postgres-1 psql -U n8n -d n8n -tAc \"SELECT count(*) FROM telegram_inbox WHERE processed_at IS NULL AND received_at < now()-interval '5 min'\"")
    try: return int(out)
    except ValueError: return 0


def recent_errors():
    out = sh("tail -n 200 /root/landtek/logs/*.log 2>/dev/null | grep -ciE 'traceback|error:|exception|FATAL' ")
    try: return int(out)
    except ValueError: return 0


def opus_review(state):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    sysmsg = ("You are a senior staff full-stack/SRE engineer for a small Postgres+Python+Docker "
              "VPS app (1 core, 33G disk, ~960MB RAM — fragile). Given the system state, say if "
              "anything needs attention the automatic remediation didn't handle, and the single most "
              "important fix. Be terse. JSON: {\"ok\":bool,\"concern\":\"...\",\"fix\":\"...\"}")
    body = json.dumps({"model": "claude-opus-4-5-20251101", "max_tokens": 400, "system": sysmsg,
                       "messages": [{"role": "user", "content": json.dumps(state)}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = "".join(c["text"] for c in json.loads(r.read())["content"] if c.get("type") == "text")
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception as e:
        log(f"opus_review failed: {type(e).__name__}")
        return None


def main():
    log("fullstack_engineer started")
    cyc = 0
    last_alert = {}
    while True:
        cyc += 1
        try:
            d = disk_pct()
            disk_actions = cleanup_disk() if d >= DISK_WARN else []
            d_after = disk_pct() if disk_actions else d
            restarted, failed = check_services()
            dbok = db_ok()
            backlog = inbox_backlog()
            errs = recent_errors()
            state = {"disk_pct": d, "disk_after_cleanup": d_after, "disk_actions": disk_actions,
                     "services_restarted": restarted, "services_failed": failed,
                     "db_ok": dbok, "inbox_backlog": backlog, "recent_errors": errs}
            log(json.dumps(state))

            # P0 alerts (deduped 1/hr per kind)
            now = time.time()
            def fire(kind, msg):
                if now - last_alert.get(kind, 0) > 3600:
                    alert(msg); last_alert[kind] = now
            if not dbok:
                fire("db", "P0: Postgres unreachable — Leo is down.")
            if failed:
                fire("svc", f"P0: services failed to restart: {', '.join(failed)}")
            if d_after >= DISK_CRIT:
                fire("disk", f"P0: disk {d_after}% after cleanup — needs manual reclaim.")
            elif disk_actions and d >= DISK_WARN:
                fire("disk_clean", f"Disk was {d}% — auto-cleaned to {d_after}% ({', '.join(disk_actions)}).")
            if restarted:
                fire("restart", f"Auto-restarted dead service(s): {', '.join(restarted)}.")
            if backlog > 20:
                fire("backlog", f"Telegram inbox backlog: {backlog} unprocessed >5min.")

            if cyc % OPUS_EVERY == 0:
                rv = opus_review(state)
                if rv and not rv.get("ok"):
                    log(f"OPUS concern: {rv.get('concern')} | fix: {rv.get('fix')}")
                    fire("opus", f"Engineer review: {rv.get('concern','')[:160]} Fix: {rv.get('fix','')[:90]}")
        except Exception as e:
            log(f"loop error: {type(e).__name__}: {str(e)[:140]}")
        time.sleep(PACE)


if __name__ == "__main__":
    main()
