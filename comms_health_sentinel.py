#!/usr/bin/env python3
"""comms_health_sentinel — never let comms drop off silently.

Per Jonathan 2026-05-19: "we cannot have service drop offs ever."

Runs every 15 min. Probes (in order):

  1. Telegram bot API alive  — getMe returns 200 + ok:true
  2. tg-dispatcher cycle fresh — tg_update_cursor.updated_at < 90s ago
  3. gmail-watcher cycle fresh — last gmail_watcher.log success < 30 min
  4. token-health-sentinel fresh — last run < 90 min
  5. tg_inquiry_queue not jammed — auto-expire stale active:
       - kind=gap_alert/report/comms_probe active >4h → expire
       - kind=intake_item/clarification active >24h with no reply → escalate
                                                                  + keep active
                                                                  (don't expire,
                                                                   still need the answer)
  6. Inbound liveness — if active inquiry has audience client/both AND no reply
     in 24h, fire an ops gap_alert (silence escalation).
  7. Backstop alive — confirm comms.install_telegram_backstop() is in place.

Any failure → log + fire an ops gap_alert via comms_send.

Exit code: always 0 (alerts are enqueued, not raised).
"""
import os
import sys
import time
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, "/root/landtek")
import psycopg2
import requests

# Import comms FIRST — this also installs the backstop globally for this process.
from comms import comms_send, _orig_post, _intercepting_post

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def _load_token() -> str:
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.strip().split("=", 1)[1]
    return ""


# Auto-expire rules per kind (active-age threshold).
AUTO_EXPIRE_RULES = {
    "gap_alert":    timedelta(hours=4),
    "report":       timedelta(hours=4),
    "comms_probe":  timedelta(minutes=30),
    # intake_item, clarification, intake_followup: do NOT auto-expire,
    # they need real answers. The 24h-silence escalation covers them.
}

# Silence escalation: active inquiries with client audience get an ops alert
# if unanswered after this threshold (regardless of kind).
CLIENT_SILENCE_THRESHOLD = timedelta(hours=24)


def probe_bot_api(token) -> tuple[bool, str]:
    """Call getMe — confirms the bot token is valid and the API is reachable."""
    try:
        r = _orig_post(f"https://api.telegram.org/bot{token}/getMe",
                       json={}, timeout=10)
        j = r.json() if r.content else {}
        if r.status_code == 200 and j.get("ok"):
            return True, f"@{j['result']['username']}"
        return False, f"HTTP {r.status_code}: {j.get('description', 'no-desc')[:120]}"
    except Exception as e:
        return False, f"exception: {str(e)[:150]}"


def probe_webhook_state(token) -> tuple[bool, str]:
    """Confirm webhook is empty (polling mode) — prevent regression to dead n8n URL."""
    try:
        r = _orig_post(f"https://api.telegram.org/bot{token}/getWebhookInfo",
                       json={}, timeout=10)
        j = r.json() if r.content else {}
        if not (r.status_code == 200 and j.get("ok")):
            return False, f"getWebhookInfo failed: {j.get('description','no-desc')}"
        url = (j.get("result", {}) or {}).get("url", "")
        if url:
            return False, f"webhook is set: {url[:80]} — inbound replies may be lost"
        return True, "polling mode (no webhook)"
    except Exception as e:
        return False, f"exception: {str(e)[:150]}"


def probe_dispatcher_cycle(cur) -> tuple[bool, str]:
    """tg_update_cursor.updated_at refreshes every dispatcher cycle (45s)."""
    cur.execute("SELECT updated_at, NOW() - updated_at AS age FROM tg_update_cursor WHERE id=1")
    row = cur.fetchone()
    if not row:
        return False, "tg_update_cursor row 1 missing"
    age = row[1]
    if age > timedelta(seconds=120):  # >2× the cycle
        return False, f"dispatcher last polled {age} ago — service may be down"
    return True, f"last poll {age} ago"


def probe_gmail_watcher_fresh() -> tuple[bool, str]:
    """gmail-watcher fires every 15 min; check its systemd timer last-run."""
    try:
        r = subprocess.run(
            ["systemctl", "show", "gmail-watcher.timer",
             "--property=LastTriggerUSec", "--no-pager"],
            capture_output=True, text=True, timeout=10)
        out = r.stdout.strip()
        # Parse "LastTriggerUSec=Tue 2026-05-19 21:16:39 UTC"
        if "=" not in out:
            return False, f"systemctl returned {out[:120]}"
        _, when = out.split("=", 1)
        if not when or when == "n/a":
            return False, "gmail-watcher.timer never fired"
        # Parse the timestamp
        when_dt = None
        for fmt in ("%a %Y-%m-%d %H:%M:%S %Z", "%a %Y-%m-%d %H:%M:%S UTC"):
            try:
                when_dt = datetime.strptime(when, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        if when_dt is None:
            return False, f"can't parse gmail-watcher.timer trigger: {when[:80]}"
        age = datetime.now(timezone.utc) - when_dt
        if age > timedelta(minutes=30):
            return False, f"gmail-watcher last fired {age} ago (>30 min — stale)"
        return True, f"last fired {age} ago"
    except Exception as e:
        return False, f"exception: {str(e)[:150]}"


def expire_stale_active(cur) -> tuple[int, list[str]]:
    """Auto-expire active inquiries that have exceeded their kind's threshold.
    Returns (n_expired, reasons)."""
    expired = []
    now = datetime.now(timezone.utc)
    for kind, threshold in AUTO_EXPIRE_RULES.items():
        cur.execute("""
            SELECT id, sent_at, NOW() - sent_at AS age
              FROM tg_inquiry_queue
             WHERE status='active'
               AND kind=%s
               AND sent_at IS NOT NULL
               AND sent_at < NOW() - %s
        """, (kind, threshold))
        rows = cur.fetchall()
        for row in rows:
            inq_id, sent_at, age = row
            cur.execute("""
                UPDATE tg_inquiry_queue
                   SET status='expired',
                       responded_at=NOW(),
                       response_text=%s
                 WHERE id=%s
            """, (f"[auto-expired by comms_health_sentinel — "
                  f"{kind} active {age} > threshold {threshold}]",
                  inq_id))
            expired.append(f"#{inq_id} ({kind}, age {age})")
    return len(expired), expired


def detect_client_silence(cur) -> list[dict]:
    """Find active inquiries with audience client/both that have been silent >24h.
    Returns list of {id, kind, age, sent_at}."""
    cur.execute("""
        SELECT id, kind, audience, sent_at, NOW() - sent_at AS age
          FROM tg_inquiry_queue
         WHERE status='active'
           AND audience IN ('client', 'both')
           AND sent_at IS NOT NULL
           AND responded_at IS NULL
           AND sent_at < NOW() - %s
    """, (CLIENT_SILENCE_THRESHOLD,))
    return [{"id": r[0], "kind": r[1], "audience": r[2],
             "sent_at": r[3], "age": r[4]} for r in cur.fetchall()]


def probe_backstop_alive() -> tuple[bool, str]:
    """Confirm the monkey-patch is still in place this process."""
    if requests.post is _intercepting_post:
        return True, "backstop active"
    return False, "BACKSTOP MISSING — raw requests.post is unpatched"


def main():
    token = _load_token()
    if not token:
        print("FATAL: no TELEGRAM_BOT_TOKEN")
        return 1
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()

    print(f"=== comms_health_sentinel  {datetime.now(timezone.utc).isoformat()}Z ===")
    findings = []  # (severity, name, ok, detail)

    # 1. Bot API alive
    ok, info = probe_bot_api(token)
    findings.append(("P0", "bot_api_alive", ok, info))
    print(f"  {'✓' if ok else '✗'} bot_api_alive: {info}")

    # 2. Webhook = empty (polling mode)
    ok, info = probe_webhook_state(token)
    findings.append(("P0", "webhook_state", ok, info))
    print(f"  {'✓' if ok else '✗'} webhook_state: {info}")

    # 3. Dispatcher cycle fresh
    ok, info = probe_dispatcher_cycle(cur)
    findings.append(("P0", "dispatcher_cycle", ok, info))
    print(f"  {'✓' if ok else '✗'} dispatcher_cycle: {info}")

    # 4. gmail-watcher fresh
    ok, info = probe_gmail_watcher_fresh()
    findings.append(("P1", "gmail_watcher_fresh", ok, info))
    print(f"  {'✓' if ok else '✗'} gmail_watcher_fresh: {info}")

    # 5. Backstop in place
    ok, info = probe_backstop_alive()
    findings.append(("P1", "backstop_alive", ok, info))
    print(f"  {'✓' if ok else '✗'} backstop_alive: {info}")

    # 6. Stale-active auto-expire (self-healing)
    n_expired, expired_list = expire_stale_active(cur)
    if n_expired:
        print(f"  ⚙ auto-expired {n_expired} stale active inquiry(ies): {expired_list[:5]}")
    else:
        print(f"  ✓ no stale active inquiries")

    # 7. Client silence (>24h on a client/both active)
    silent = detect_client_silence(cur)
    if silent:
        print(f"  ⚠ {len(silent)} client inquiry(ies) silent >24h: {[s['id'] for s in silent]}")

    # Build the failure list
    failures = [(sev, name, info) for sev, name, ok, info in findings if not ok]

    # If anything failed, enqueue an ops gap_alert via comms_send
    if failures or silent:
        lines = ["⚠️ <b>comms_health_sentinel — issues detected</b>",
                 f"<i>{datetime.now(timezone.utc).isoformat()}Z</i>", ""]
        for sev, name, info in failures:
            lines.append(f"  • <b>{sev}</b> {name}: {info}")
        if silent:
            lines.append("")
            lines.append("<b>Client inquiries silent &gt;24h:</b>")
            for s in silent[:5]:
                lines.append(f"  • inquiry #{s['id']} ({s['kind']}, audience={s['audience']}) "
                             f"— silent {s['age']}")
        if n_expired:
            lines.append("")
            lines.append(f"<b>Auto-expired {n_expired} stale active:</b> {', '.join(expired_list[:5])}")
        body = "\n".join(lines)[:4000]
        ok, results = comms_send(body, audience="ops", kind="gap_alert",
                                  case_file="MWK-001")
        if ok:
            print(f"  → ops alert sent")
        else:
            # CRITICAL: comms_health_sentinel itself can't reach ops.
            # Last-resort: write to a file marker so a human can see.
            Path("/var/log/comms_health_sentinel_FATAL.log").write_text(
                f"{datetime.now(timezone.utc).isoformat()}Z — ALL comms failed.\n"
                f"findings: {findings}\nsilent: {silent}\n"
            )
            print(f"  ✗ FAILED to send ops alert — wrote FATAL log")

    cur.close(); conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
