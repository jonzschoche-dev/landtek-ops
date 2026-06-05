#!/usr/bin/env python3
"""leo_simulator.py — constantly-running Leo simulator (deploy_298c).

A long-running daemon that drives synthesized Telegram webhooks into Leo's
bot endpoint every CYCLE_SECONDS, then evaluates the resulting reply against
each scenario's expected/forbidden substrings.

Target volume: ~3 prompts/min × 60 × 24 = 4,320 Leo invocations/day.

Architecture:
  1. Pick the oldest-last-run sim scenario (definition.kind='simulator_prompt')
  2. POST a fake Telegram update to the bot's n8n webhook
  3. Wait POLL_TIMEOUT seconds for the exec to log a reply in leo_interactions
  4. Grade the reply against expected_substrings (must contain ALL) and
     forbidden_substrings (must contain NONE), case-insensitive
  5. Record pass/fail to leo_qa_sim_payloads, update leo_qa_probes.last_run_at,
     open/close leo_qa_violations on regression
  6. Alert Jonathan on critical-severity regression (rate-limit exempt)

Operational notes:
  - Sim chat_ids in range 999000001-999000005 are bogus; Telegram returns 400
    on Reply node sends, so no real user ever sees a sim reply.
  - The reply *text* is captured in leo_interactions by 'Log Leo Interaction'
    which runs BEFORE Reply nodes, so grading is intact.
  - Long-running service (systemd Type=simple, Restart=always); sleeps inside
    the main loop between cycles.
  - SAFETY: if execution_error_rate over the last hour spikes >50%, sleep
    longer to avoid amplifying problems."""
from __future__ import annotations
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"
# Two different IDs on the Telegram Trigger node:
#   webhookId is in the URL  → 2fe01d2f-680c-47bd-86c6-7bb24893afb9
#   node.id is in the secret → fc7b5df9-2d73-48d4-92e8-c5fc21dee837
# Per n8n's getSecretToken: secret = workflow_id + "_" + node.id (alphanumeric/_/-).
WEBHOOK_PATH_ID = "2fe01d2f-680c-47bd-86c6-7bb24893afb9"
WEBHOOK_NODE_ID = "fc7b5df9-2d73-48d4-92e8-c5fc21dee837"
WEBHOOK_URL = f"https://leo.hayuma.org/webhook/{WEBHOOK_PATH_ID}/webhook"
WEBHOOK_SECRET = f"{WORKFLOW_ID}_{WEBHOOK_NODE_ID}"
JONATHAN = "6513067717"

CYCLE_SECONDS    = 20      # sleep between cycles
POLL_TIMEOUT     = 60      # how long to wait for Leo's reply per scenario
POLL_INTERVAL    = 2       # how often to check leo_interactions
HEALTH_PAUSE_SEC = 90      # back off this many seconds when health is bad
HEALTH_WINDOW    = '15 minutes'  # how far back to count errors for health gauge


def now_utc():
    return datetime.now(timezone.utc)


def health_ok(cur) -> bool:
    """If the last hour's Leo error rate is >50%, back off."""
    cur.execute(
        f"""
        SELECT
          COUNT(*) FILTER (WHERE status='error') AS errs,
          COUNT(*) AS total
          FROM execution_entity
         WHERE "workflowId" = %s
           AND "startedAt" > now() - interval '{HEALTH_WINDOW}'
        """,
        (WORKFLOW_ID,),
    )
    r = cur.fetchone()
    if not r or r["total"] == 0:
        return True
    # Require at least 5 runs in window before the rate is statistically meaningful;
    # otherwise a single bootstrap error pegs the rate at 100% and we never wake.
    if r["total"] < 5:
        return True
    rate = r["errs"] / r["total"]
    return rate < 0.5


def pick_due_scenario(cur):
    """Pick a probe with variety bias (deploy_328).

    Strategy: 80% of the time, pick from the oldest-last-run quartile
    (round-robin). 20% of the time, pick randomly from the active library —
    so Jonathan sees varied probe content in the digest instead of the
    same 6 names cycling.

    Also weights NEVER-RUN probes (last_run_at IS NULL) heavily so new
    probes get exercised quickly.
    """
    import random
    if random.random() < 0.20:
        # Random selection across the entire library
        cur.execute("""
            SELECT id, name, definition, severity
              FROM leo_qa_probes
             WHERE rail = 'sim' AND active = true
             ORDER BY random() LIMIT 1
        """)
    else:
        # Oldest-last-run quartile (NULL ranks highest as "epoch")
        cur.execute("""
            WITH ranked AS (
              SELECT id, name, definition, severity,
                     ROW_NUMBER() OVER (ORDER BY
                       COALESCE(last_run_at, 'epoch'::timestamptz) ASC,
                       id ASC) AS rn,
                     COUNT(*) OVER () AS total
                FROM leo_qa_probes
               WHERE rail = 'sim' AND active = true
            )
            SELECT id, name, definition, severity
              FROM ranked
             WHERE rn <= GREATEST(total / 4, 5)
             ORDER BY random() LIMIT 1
        """)
    return cur.fetchone()


def post_synthetic_webhook(sender_id: str, sender_name: str, text: str) -> dict:
    """POST a fake Telegram update to the n8n webhook. Returns the update we sent."""
    chat_id = int(sender_id)  # sim chat_id == sim sender_id
    msg_id  = random.randint(1, 1_000_000_000)
    upd_id  = random.randint(1, 9_999_999_999)
    update = {
        "update_id": upd_id,
        "message": {
            "message_id": msg_id,
            "from": {"id": chat_id, "is_bot": False, "first_name": sender_name, "language_code": "en"},
            "chat": {"id": chat_id, "first_name": sender_name, "type": "private"},
            "date": int(time.time()),
            "text": text,
        },
    }
    body = json.dumps(update).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL, data=body,
        headers={
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET,
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.HTTPError as e:
        # 200/204 expected; 5xx/4xx logged
        if e.code not in (200, 204):
            raise
    return update


def wait_for_reply(cur, sender_id: str, since_ts) -> dict | None:
    """Poll leo_interactions for a reply from this sim sender after timestamp."""
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        cur.execute(
            """
            SELECT id, timestamp, sender_id, reply_text, execution_id
              FROM leo_interactions
             WHERE sender_id = %s
               AND timestamp >= %s
             ORDER BY id DESC LIMIT 1
            """,
            (sender_id, since_ts),
        )
        r = cur.fetchone()
        if r and r["reply_text"]:
            return r
        time.sleep(POLL_INTERVAL)
    return None


def grade(reply_text: str, expected: list[str], forbidden: list[str]) -> tuple[bool, str | None]:
    """Pass = all `expected` substrings present AND no `forbidden` substring present."""
    if not reply_text:
        return False, "no reply text captured"
    rt = reply_text.lower()
    missing = [s for s in (expected or []) if s.lower() not in rt]
    found_forbidden = [s for s in (forbidden or []) if s.lower() in rt]
    if missing:
        return False, f"missing expected: {missing[:3]}"
    if found_forbidden:
        return False, f"contained forbidden: {found_forbidden[:3]}"
    return True, None


def record_run(cur, probe, scenario_def, sent_update, reply_row, passed: bool, fail_reason: str | None):
    cur.execute(
        """
        INSERT INTO leo_qa_sim_payloads
          (probe_id, sim_sender_id, sim_chat_id, update_id, prompt_text,
           leo_exec_id, leo_reply_text, passed, fail_reason, completed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        """,
        (probe["id"],
         scenario_def["sim_sender_telegram_id"],
         scenario_def["sim_sender_telegram_id"],
         sent_update["update_id"],
         scenario_def["prompt_text"],
         (reply_row["execution_id"] if reply_row else None),
         (reply_row["reply_text"] if reply_row else None),
         passed, fail_reason),
    )
    cur.execute(
        "UPDATE leo_qa_probes SET last_run_at = now(), last_status = %s WHERE id = %s",
        ("pass" if passed else "fail", probe["id"]),
    )
    cur.execute(
        "INSERT INTO leo_qa_runs (probe_id, status, details) VALUES (%s, %s, %s::jsonb)",
        (probe["id"], "pass" if passed else "fail",
         json.dumps({"reply_excerpt": (reply_row["reply_text"][:300] if reply_row else None),
                     "fail_reason": fail_reason})),
    )
    if not passed:
        cur.execute(
            """
            INSERT INTO leo_qa_violations (probe_id, severity, details, leo_exec_id, alerted_at)
            VALUES (%s, %s, %s::jsonb, %s, now())
            ON CONFLICT (probe_id, leo_exec_id) DO NOTHING
            """,
            (probe["id"], probe["severity"],
             json.dumps({"fail_reason": fail_reason,
                         "reply_excerpt": (reply_row["reply_text"][:300] if reply_row else None),
                         "prompt": scenario_def["prompt_text"]}),
             (reply_row["execution_id"] if reply_row else f"sim-{sent_update['update_id']}")),
        )
    else:
        # Auto-close any prior open violations for this probe
        cur.execute(
            "UPDATE leo_qa_violations SET closed_at = now() WHERE probe_id = %s AND closed_at IS NULL",
            (probe["id"],),
        )


def alert_critical(probe, scenario_def, fail_reason, reply_excerpt):
    if probe["severity"] != "critical":
        return
    if tg_send is None:
        return
    text = (
        f"🚨 <b>SIM CRITICAL FAIL</b>\n\n"
        f"Probe: <code>{probe['name']}</code>\n"
        f"Prompt: <i>{(scenario_def['prompt_text'] or '')[:200]}</i>\n\n"
        f"Reason: {fail_reason}\n\n"
        f"Reply excerpt:\n  {(reply_excerpt or '(empty)')[:400]}"
    )
    try:
        tg_send(JONATHAN, text, source="watchdog", recipient_name="Jonathan", override_rate_limit=True)
    except Exception:
        pass


def main():
    print(f"[leo_simulator] starting; cycle={CYCLE_SECONDS}s, poll_timeout={POLL_TIMEOUT}s", flush=True)
    while True:
        cycle_start = time.time()
        try:
            conn = psycopg2.connect(DSN)
            conn.autocommit = True
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            if not health_ok(cur):
                print(f"[leo_simulator] health_ok=False — backing off {HEALTH_PAUSE_SEC}s", flush=True)
                cur.close(); conn.close()
                time.sleep(HEALTH_PAUSE_SEC)
                continue

            probe = pick_due_scenario(cur)
            if not probe:
                cur.close(); conn.close()
                time.sleep(CYCLE_SECONDS)
                continue

            scenario_def = probe["definition"]
            sender_id    = scenario_def["sim_sender_telegram_id"]
            sender_name  = "Sim" + sender_id[-3:]
            prompt_text  = scenario_def["prompt_text"]

            ts_before = now_utc()
            try:
                sent = post_synthetic_webhook(sender_id, sender_name, prompt_text)
            except Exception as e:
                print(f"[leo_simulator] webhook POST failed: {e}", flush=True)
                cur.close(); conn.close()
                time.sleep(CYCLE_SECONDS)
                continue

            reply = wait_for_reply(cur, sender_id, ts_before)
            passed, fail_reason = grade(
                (reply or {}).get("reply_text", ""),
                scenario_def.get("expected_substrings", []),
                scenario_def.get("forbidden_substrings", []),
            )
            record_run(cur, probe, scenario_def, sent, reply, passed, fail_reason)
            if not passed:
                alert_critical(probe, scenario_def, fail_reason,
                               (reply or {}).get("reply_text", ""))

            print(
                f"[leo_simulator] {probe['name']}  pass={passed}  fail={fail_reason or '—'}",
                flush=True,
            )
            cur.close(); conn.close()
        except Exception as e:
            print(f"[leo_simulator] cycle error: {e}", flush=True)

        elapsed = time.time() - cycle_start
        sleep_for = max(CYCLE_SECONDS - elapsed, 1)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
