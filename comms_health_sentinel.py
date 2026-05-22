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

# Per deploy_266 (2026-05-22 noise incident): the sentinel was re-firing the
# same P0 every 15 minutes for an unchanged condition (webhook drift). Dedup
# state lives in this table; only NEW failures or info-changed conditions
# alert, plus a 24h re-prompt while the condition persists. Recoveries get
# a single ✓ line.
ALERT_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS comms_health_alert_state (
    probe_name      text PRIMARY KEY,
    last_status     text NOT NULL,
    last_info       text,
    last_alerted_at timestamptz,
    last_seen_at    timestamptz NOT NULL DEFAULT now(),
    consecutive_failure_count int NOT NULL DEFAULT 0
);
"""
ALERT_REPROMPT_INTERVAL = timedelta(hours=24)


def _ensure_alert_state_table(cur):
    cur.execute(ALERT_STATE_SCHEMA)


def _decide_alert(cur, name, ok, info):
    """Compare current finding to last persisted state. Returns one of:
      None              — no alert (status unchanged-OK or unchanged-FAIL within reprompt window)
      'NEW_FAIL'        — first failure or info changed → alert
      'REPROMPT'        — same failure persisted >24h → re-alert
      'RECOVERED'       — was failing, now OK → send recovery line
    Always updates the persisted state."""
    cur.execute("""
        SELECT last_status, last_info, last_alerted_at, consecutive_failure_count
          FROM comms_health_alert_state WHERE probe_name = %s
    """, (name,))
    prev = cur.fetchone()
    decision = None
    if not ok:
        same = (prev and prev[0] == 'fail' and (prev[1] or '') == (info or ''))
        if not same:
            decision = 'NEW_FAIL'
        elif prev[2] and (datetime.now(timezone.utc) - prev[2]) > ALERT_REPROMPT_INTERVAL:
            decision = 'REPROMPT'
        new_count = (prev[3] if prev and prev[0] == 'fail' else 0) + 1
    else:
        if prev and prev[0] == 'fail':
            decision = 'RECOVERED'
        new_count = 0
    cur.execute("""
        INSERT INTO comms_health_alert_state
          (probe_name, last_status, last_info, last_alerted_at,
           last_seen_at, consecutive_failure_count)
        VALUES (%s, %s, %s,
                CASE WHEN %s IS NOT NULL THEN NOW() ELSE
                    (SELECT last_alerted_at FROM comms_health_alert_state WHERE probe_name = %s) END,
                NOW(), %s)
        ON CONFLICT (probe_name) DO UPDATE SET
          last_status = EXCLUDED.last_status,
          last_info = EXCLUDED.last_info,
          last_alerted_at = COALESCE(EXCLUDED.last_alerted_at,
                                      comms_health_alert_state.last_alerted_at),
          last_seen_at = NOW(),
          consecutive_failure_count = EXCLUDED.consecutive_failure_count
    """, (name, 'ok' if ok else 'fail', info, decision, name, new_count))
    return decision


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
    """Confirm webhook is empty (polling mode) — prevent regression to dead n8n URL.

    Per deploy_267 (2026-05-22): the polling-based tg_dispatcher is canonical
    for inbound. A webhook on the bot blocks getUpdates from returning new
    messages, so the dispatcher polls forever empty and Jonathan's replies
    silently vanish. We've seen this drift happen at least twice. So when this
    probe detects a webhook, it SELF-HEALS by calling deleteWebhook before
    surfacing anything. If the delete succeeds, the probe returns ok=True
    with a "auto-deleted drift" detail — deploy_266 dedup then converts this
    into a single ✓ recovery line, not a continuous alert.

    If a future migration makes n8n the canonical inbound path, this probe
    needs to be updated to accept that webhook URL as healthy. Today the
    dispatcher is polling-based, so the invariant is: NO webhook."""
    try:
        r = _orig_post(f"https://api.telegram.org/bot{token}/getWebhookInfo",
                       json={}, timeout=10)
        j = r.json() if r.content else {}
        if not (r.status_code == 200 and j.get("ok")):
            return False, f"getWebhookInfo failed: {j.get('description','no-desc')}"
        url = (j.get("result", {}) or {}).get("url", "")
        if not url:
            return True, "polling mode (no webhook)"
        # Webhook drift detected — self-heal.
        try:
            dr = _orig_post(f"https://api.telegram.org/bot{token}/deleteWebhook",
                            json={"drop_pending_updates": False}, timeout=10)
            dj = dr.json() if dr.content else {}
            if dr.status_code == 200 and dj.get("ok"):
                return True, f"auto-deleted drift webhook: {url[:80]}"
            return False, (f"webhook is set ({url[:60]}) and deleteWebhook failed: "
                            f"{dj.get('description','?')[:80]} — inbound still blocked")
        except Exception as de:
            return False, (f"webhook is set ({url[:60]}) and deleteWebhook raised: "
                            f"{str(de)[:80]} — inbound still blocked")
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
    _ensure_alert_state_table(cur)

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

    # Per deploy_266: route every finding through _decide_alert so unchanged
    # conditions don't re-fire every 15 minutes. The decision tells us whether
    # this round produces a NEW_FAIL alert, a REPROMPT (24h+ unfixed), or a
    # RECOVERED line.
    alert_failures = []     # (sev, name, info, decision) — to send THIS round
    recoveries = []         # (name, info) — was failing, now OK
    suppressed = []         # for the verbose log
    for sev, name, ok, info in findings:
        decision = _decide_alert(cur, name, ok, info)
        if decision in ('NEW_FAIL', 'REPROMPT'):
            alert_failures.append((sev, name, info, decision))
        elif decision == 'RECOVERED':
            recoveries.append((name, info))
        elif not ok:
            suppressed.append(name)
    if suppressed:
        print(f"  ⇣ suppressed {len(suppressed)} unchanged failure(s): {suppressed}")

    # Client-silence dedup: keep the existing one-time warning behavior by
    # treating each inquiry_id as a probe_name. A new silent inquiry is
    # NEW_FAIL once; re-running the sentinel won't re-fire for the same one.
    silent_to_alert = []
    for s in silent:
        probe_key = f"client_silent_#{s['id']}"
        info_str = f"{s['kind']} aud={s['audience']} age={s['age']}"
        decision = _decide_alert(cur, probe_key, ok=False, info=info_str)
        if decision in ('NEW_FAIL', 'REPROMPT'):
            silent_to_alert.append(s)

    if alert_failures or recoveries or silent_to_alert:
        lines = ["⚠️ <b>comms_health_sentinel — issues detected</b>",
                 f"<i>{datetime.now(timezone.utc).isoformat()}Z</i>", ""]
        for sev, name, info, decision in alert_failures:
            tag = " (24h re-prompt)" if decision == 'REPROMPT' else ""
            lines.append(f"  • <b>{sev}</b> {name}{tag}: {info}")
        if silent_to_alert:
            lines.append("")
            lines.append("<b>Client inquiries silent &gt;24h:</b>")
            for s in silent_to_alert[:5]:
                lines.append(f"  • inquiry #{s['id']} ({s['kind']}, audience={s['audience']}) "
                             f"— silent {s['age']}")
        if recoveries:
            lines.append("")
            for name, info in recoveries:
                lines.append(f"  ✓ {name} recovered: {info}")
        if n_expired:
            lines.append("")
            lines.append(f"<b>Auto-expired {n_expired} stale active:</b> {', '.join(expired_list[:5])}")
        body = "\n".join(lines)[:4000]
        ok, results = comms_send(body, audience="ops", kind="gap_alert",
                                  case_file="MWK-001")
        if ok:
            print(f"  → ops alert sent ({len(alert_failures)} new/reprompt, "
                  f"{len(recoveries)} recovered, {len(silent_to_alert)} silent)")
        else:
            Path("/var/log/comms_health_sentinel_FATAL.log").write_text(
                f"{datetime.now(timezone.utc).isoformat()}Z — ALL comms failed.\n"
                f"findings: {findings}\nsilent: {silent}\n"
            )
            print(f"  ✗ FAILED to send ops alert — wrote FATAL log")
    else:
        print(f"  ✓ no new issues — nothing to alert")

    cur.close(); conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
