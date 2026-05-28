#!/usr/bin/env python3
"""Deploy 288 — outbound message pacing + bombardment monitor.

Symptom (May 28 01:06–01:40 UTC): the system (agent acting on Jonathan's
behalf, plus Leo) sent Kristyle 4 long messages in 35 minutes. Jonathan
flagged this as bombardment: "this is something we need to monitor."

This deploy:

  A. SCHEMA: new table outbound_messages logging every Telegram send by
     the system, regardless of source (Leo, scripts/, briefers, manual ops).
     Columns: id, sent_at, chat_id, recipient_name, source, content_hash,
     content_preview, success, error.

  B. INSTRUMENTATION: a small Python helper scripts/tg_send.py that all
     future system messages MUST go through. It (1) writes the
     outbound_messages row, (2) enforces a soft rate limit per recipient,
     (3) returns the Telegram response.

  C. MONITOR: scripts/bombardment_sentinel.py — runs every 5 min via
     systemd timer. Alerts Jonathan if any single non-Jonathan chat_id
     received >3 messages in the previous 15 min, OR if Jonathan himself
     received >8 messages in 30 min (could be Leo-loop runaway).

  D. RULE J: append a pacing discipline rule to Leo's system prompt:
       - Default cadence: 1 message per recipient per 10 min unless event-
         driven
       - Consolidate multiple talking points into a single message
       - If multiple things to convey, use a one-line header + bulleted body
       - Never split a logical update into multiple message blobs

Idempotent. Audit via outbound_messages.source column."""
import json
import os
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
REPO_ROOT = "/root/landtek"
WORKFLOW_ID = "vSDQv1vfn6627bnA"

# ---------------------------------------------------------------------------
# A. Schema
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS outbound_messages (
  id              serial PRIMARY KEY,
  sent_at         timestamptz NOT NULL DEFAULT now(),
  chat_id         text NOT NULL,
  recipient_name  text,
  source          text NOT NULL,
  content_hash    text NOT NULL,
  content_preview text NOT NULL,
  success         boolean NOT NULL DEFAULT true,
  error           text,
  CONSTRAINT outbound_messages_source_check
    CHECK (source IN ('leo_agent','script','briefer','manual_ops','recovery','watchdog'))
);
CREATE INDEX IF NOT EXISTS idx_outbound_chat_time ON outbound_messages(chat_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbound_source ON outbound_messages(source);
CREATE INDEX IF NOT EXISTS idx_outbound_time ON outbound_messages(sent_at DESC);

-- Audit-rejected outbound sends (when rate limit blocks)
CREATE TABLE IF NOT EXISTS outbound_blocks (
  id          serial PRIMARY KEY,
  blocked_at  timestamptz NOT NULL DEFAULT now(),
  chat_id     text NOT NULL,
  source      text NOT NULL,
  reason      text NOT NULL,
  content_preview text
);
CREATE INDEX IF NOT EXISTS idx_outbound_blocks_chat ON outbound_blocks(chat_id, blocked_at DESC);
"""


# ---------------------------------------------------------------------------
# B. Helper script that wraps Telegram send with logging + rate limit
# ---------------------------------------------------------------------------
TG_SEND_PY = '''#!/usr/bin/env python3
"""tg_send.py — single chokepoint for system-originated Telegram sends.

Every script/briefer/recovery/manual_ops send MUST use this helper. It:
  1. Checks rate limits (N messages per recipient per window)
  2. Logs to outbound_messages
  3. Sends via Telegram API
  4. Returns (ok, response_or_error)

Usage:
  from tg_send import send
  ok, info = send(chat_id="5992075757", text="Hi", source="manual_ops",
                  recipient_name="Joy Kristyle")
"""
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Rate limits: max N messages per chat_id per window_seconds
# Jonathan gets a higher cap because he's actively interacting
RATE_LIMITS = {
    "default": (3, 15 * 60),       # non-Jonathan: 3 messages per 15 min
    "6513067717": (12, 30 * 60),    # Jonathan: 12 per 30 min
}

JONATHAN_CHAT = "6513067717"


def _bot_token():
    for k in ("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
        v = os.environ.get(k)
        if v:
            return v
    p = Path("/root/landtek/.env")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() in ("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
                return v.strip().strip(\'"\').strip("\'")
    return None


def _check_rate(cur, chat_id, source):
    cap, window = RATE_LIMITS.get(chat_id, RATE_LIMITS["default"])
    cur.execute(
        """
        SELECT COUNT(*) AS n
          FROM outbound_messages
         WHERE chat_id = %s
           AND sent_at > now() - (%s || \' seconds\')::interval
           AND success = true
        """,
        (chat_id, window),
    )
    n = cur.fetchone()["n"]
    if n >= cap:
        return False, f"rate_limit: {n}/{cap} in last {window}s for chat {chat_id}"
    return True, None


def send(chat_id, text, source, recipient_name=None, parse_mode="HTML",
         disable_web_page_preview=True, override_rate_limit=False):
    chat_id = str(chat_id)
    token = _bot_token()
    if not token:
        return False, "no_bot_token"
    chash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    preview = text.replace("\\n", " | ")[:200]

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Rate limit check
    if not override_rate_limit:
        ok, reason = _check_rate(cur, chat_id, source)
        if not ok:
            cur.execute(
                "INSERT INTO outbound_blocks (chat_id, source, reason, content_preview) VALUES (%s, %s, %s, %s)",
                (chat_id, source, reason, preview),
            )
            cur.close()
            conn.close()
            return False, reason

    # Send via Telegram
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read().decode("utf-8")
        ok = resp.status == 200
        err = None
    except Exception as e:
        ok = False
        body = ""
        err = str(e)[:300]

    cur.execute(
        """
        INSERT INTO outbound_messages
            (chat_id, recipient_name, source, content_hash, content_preview, success, error)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (chat_id, recipient_name, source, chash, preview, ok, err),
    )
    cur.close()
    conn.close()
    return ok, body if ok else err


if __name__ == "__main__":
    # CLI: tg_send.py <chat_id> <source> <text>
    if len(sys.argv) < 4:
        print("usage: tg_send.py <chat_id> <source> <text>")
        sys.exit(1)
    ok, info = send(chat_id=sys.argv[1], source=sys.argv[2], text=sys.argv[3])
    print("ok=", ok)
    print(info[:500])
'''


# ---------------------------------------------------------------------------
# C. Sentinel — alerts Jonathan when bombardment detected
# ---------------------------------------------------------------------------
SENTINEL_PY = '''#!/usr/bin/env python3
"""bombardment_sentinel.py — runs every 5 min, alarms on outbound bursts.

Alarm conditions:
  - >3 messages to any single non-Jonathan chat_id in last 15 min
  - >8 messages to Jonathan in last 30 min (Leo loop risk)

Sends alert via tg_send.py with source=\'watchdog\' (which gets a higher
rate limit ceiling so the alert itself doesn\'t get throttled)."""
import os
import sys

sys.path.insert(0, "/root/landtek/scripts")
from tg_send import send  # noqa: E402

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN = "6513067717"


def main():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Burst to non-Jonathan in last 15 min
    cur.execute(
        """
        SELECT chat_id, recipient_name, COUNT(*) AS n,
               STRING_AGG(LEFT(content_preview,80), \' | \' ORDER BY sent_at) AS recent_previews,
               MIN(sent_at)::timestamp(0) AS first_at,
               MAX(sent_at)::timestamp(0) AS last_at
          FROM outbound_messages
         WHERE chat_id <> %s
           AND sent_at > now() - INTERVAL \'15 minutes\'
           AND success = true
         GROUP BY chat_id, recipient_name
        HAVING COUNT(*) > 3
        """,
        (JONATHAN,),
    )
    alerts = cur.fetchall()

    # Jonathan-burst in last 30 min
    cur.execute(
        """
        SELECT COUNT(*) AS n
          FROM outbound_messages
         WHERE chat_id = %s
           AND sent_at > now() - INTERVAL \'30 minutes\'
           AND success = true
        """,
        (JONATHAN,),
    )
    jon_count = cur.fetchone()["n"]

    for a in alerts:
        text = (
            f"\\u26a0\\ufe0f <b>Bombardment detected</b>\\n\\n"
            f"  Recipient: {a[\'recipient_name\'] or a[\'chat_id\']} ({a[\'chat_id\']})\\n"
            f"  Count: {a[\'n\']} messages in 15 min\\n"
            f"  Window: {a[\'first_at\']} \\u2192 {a[\'last_at\']}\\n\\n"
            f"  Recent previews: {a[\'recent_previews\'][:600]}"
        )
        # Dedupe — only alert once per recipient per hour
        cur.execute(
            """
            SELECT 1 FROM outbound_messages
             WHERE source = \'watchdog\'
               AND content_preview LIKE %s
               AND sent_at > now() - INTERVAL \'1 hour\'
             LIMIT 1
            """,
            (f"%Bombardment%{a[\'chat_id\']}%",),
        )
        if not cur.fetchone():
            send(JONATHAN, text, source="watchdog",
                 recipient_name="Jonathan",
                 override_rate_limit=True)

    if jon_count > 8:
        text = (
            f"\\u26a0\\ufe0f <b>Self-bombardment risk</b>\\n\\n"
            f"You received {jon_count} system messages in the last 30 min. "
            f"That\'s above the soft cap of 8. Likely a Leo or script loop. "
            f"Check outbound_messages table for the source pattern."
        )
        cur.execute(
            """
            SELECT 1 FROM outbound_messages
             WHERE source = \'watchdog\'
               AND content_preview LIKE \'%Self-bombardment%\'
               AND sent_at > now() - INTERVAL \'30 minutes\'
             LIMIT 1
            """
        )
        if not cur.fetchone():
            send(JONATHAN, text, source="watchdog",
                 recipient_name="Jonathan",
                 override_rate_limit=True)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# D. Rule J text — appended to Leo's system prompt
# ---------------------------------------------------------------------------
RULE_J = """

## PACING DISCIPLINE (Rule J — added 2026-05-28 — deploy_288)

Symptom that triggered this rule: 4 long messages sent to Kristyle in 35 minutes after her registration. Jonathan flagged it as bombardment.

### Default cadence

- Default: **1 message per recipient per 10 minutes** unless event-driven (i.e., the recipient just sent something or a deadline just hit).
- **Consolidate** multiple talking points into a single message. If you have a welcome + a directive + a status update + a correction, those become ONE message with a one-line header + a bulleted body, not four separate sends.

### Anti-patterns to avoid

- ❌ Sending a "welcome" message followed 2 minutes later by an "additional info" message
- ❌ Sending a "fix is live" message followed by an "and here's what changed" message
- ❌ Apologizing as a separate message — fold the apology into the next substantive message
- ❌ Sending a sender_id 5992075757 (Kristyle) more than 3 messages in any 15-minute window

### When event-driven sends ARE okay

- The recipient just messaged and is waiting for a reply (always reply once)
- A deadline crosses (e.g., calendar alarm fires)
- A user action requires a notification (e.g., onboarding handshake)

### Hard cap

If you would emit a 4th message to a single non-Jonathan recipient within 15 min, **do not send it**. Instead, populate `telegram_summary_for_jonathan` with the suppressed content and a note `⚠️ suppressed redundant message to <recipient>: <gist>`.
"""


# ---------------------------------------------------------------------------
# systemd timer
# ---------------------------------------------------------------------------
SERVICE = """[Unit]
Description=LandTek outbound bombardment sentinel
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/bombardment_sentinel.py
StandardOutput=append:/var/log/landtek-bombardment-sentinel.log
StandardError=append:/var/log/landtek-bombardment-sentinel.log
"""

TIMER = """[Unit]
Description=Run bombardment sentinel every 5 min

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s
Unit=landtek-bombardment-sentinel.service

[Install]
WantedBy=timers.target
"""


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main():
    print("Deploy 288 — outbound pacing + bombardment monitor")
    print("=" * 56)

    # A. Schema
    print("\n  A) Schema")
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_288'")
    cur.execute(SCHEMA_SQL)
    conn.commit()
    print("    ✓ outbound_messages + outbound_blocks tables")

    # B. tg_send.py helper
    print("\n  B) tg_send.py helper")
    helper_path = f"{REPO_ROOT}/scripts/tg_send.py"
    open(helper_path, "w").write(TG_SEND_PY)
    os.chmod(helper_path, 0o755)
    print(f"    ✓ wrote {helper_path}")

    # C. bombardment_sentinel.py
    print("\n  C) bombardment_sentinel.py")
    sentinel_path = f"{REPO_ROOT}/scripts/bombardment_sentinel.py"
    open(sentinel_path, "w").write(SENTINEL_PY)
    os.chmod(sentinel_path, 0o755)
    print(f"    ✓ wrote {sentinel_path}")

    # systemd timer
    print("\n  D) systemd timer")
    open("/etc/systemd/system/landtek-bombardment-sentinel.service", "w").write(SERVICE)
    open("/etc/systemd/system/landtek-bombardment-sentinel.timer", "w").write(TIMER)
    run(["systemctl", "daemon-reload"])
    rc, _ = run(["systemctl", "enable", "--now", "landtek-bombardment-sentinel.timer"])
    print(f"    ✓ timer enabled rc={rc}")

    # E. Rule J in system prompt
    print("\n  E) Rule J appended to Leo system prompt")
    cur2 = psycopg2.connect(DSN).cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur2.execute("SELECT nodes FROM workflow_entity WHERE id=%s FOR UPDATE", (WORKFLOW_ID,))
    nodes = cur2.fetchone()["nodes"]
    patched = False
    for n in nodes:
        if n.get("name") == "AI Agent":
            opts = n.setdefault("parameters", {}).setdefault("options", {})
            sm = opts.get("systemMessage", "")
            if "Rule J" in sm:
                print("    · Rule J already present")
                break
            opts["systemMessage"] = sm.rstrip() + RULE_J
            patched = True
            print(f"    ✓ appended ({len(sm)} → {len(opts['systemMessage'])} chars)")
            break
    if patched:
        cur2.connection.autocommit = False
        cur2.execute(
            'UPDATE workflow_entity SET nodes=%s, "updatedAt"=now() WHERE id=%s',
            (json.dumps(nodes), WORKFLOW_ID),
        )
        cur2.connection.commit()

    print("\n  ✓ deploy_288 complete")


if __name__ == "__main__":
    main()
