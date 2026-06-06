#!/usr/bin/env python3
"""simulator_core — shared Leo synthetic webhook driver + grading.

Used by leo_simulator.py (daemon) and rapid_fire_simulator.py (burst CLI).
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import urllib.error
import urllib.request

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"
WEBHOOK_PATH_ID = "2fe01d2f-680c-47bd-86c6-7bb24893afb9"
WEBHOOK_NODE_ID = "fc7b5df9-2d73-48d4-92e8-c5fc21dee837"
WEBHOOK_URL = f"https://leo.hayuma.org/webhook/{WEBHOOK_PATH_ID}/webhook"
WEBHOOK_SECRET = f"{WORKFLOW_ID}_{WEBHOOK_NODE_ID}"

POLL_TIMEOUT = int(os.environ.get("SIM_POLL_TIMEOUT", "60"))
POLL_INTERVAL = int(os.environ.get("SIM_POLL_INTERVAL", "2"))
HEALTH_WINDOW = os.environ.get("SIM_HEALTH_WINDOW", "15 minutes")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def connect():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def health_ok(cur) -> bool:
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
    if not r or r["total"] < 5:
        return True
    return (r["errs"] / r["total"]) < 0.5


def pick_probe(cur, *, pack: str | None = None, name: str | None = None):
    if name:
        cur.execute(
            """
            SELECT id, name, definition, severity
              FROM leo_qa_probes
             WHERE rail = 'sim' AND active = true AND name = %s
            """,
            (name,),
        )
        return cur.fetchone()

    if pack and pack != "all":
        cur.execute(
            """
            SELECT id, name, definition, severity
              FROM leo_qa_probes
             WHERE rail = 'sim' AND active = true
               AND (definition->>'pack' = %s OR name LIKE %s)
             ORDER BY COALESCE(last_run_at, 'epoch'::timestamptz) ASC, id ASC
             LIMIT 1
            """,
            (pack, f"arch.%"),
        )
        row = cur.fetchone()
        if row:
            return row

    if random.random() < 0.20:
        cur.execute("""
            SELECT id, name, definition, severity
              FROM leo_qa_probes
             WHERE rail = 'sim' AND active = true
             ORDER BY random() LIMIT 1
        """)
    else:
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


def fetch_pack_probes(cur, pack: str, limit: int | None = None) -> list[dict]:
    clauses = ["rail = 'sim'", "active = true"]
    params: list = []
    if pack != "all":
        clauses.append("(definition->>'pack' = %s OR name LIKE %s)")
        params.extend([pack, "arch.%" if pack == "architecture" else f"{pack}.%"])
    sql = f"""
        SELECT id, name, definition, severity
          FROM leo_qa_probes
         WHERE {' AND '.join(clauses)}
         ORDER BY COALESCE(last_run_at, 'epoch'::timestamptz) ASC NULLS FIRST, id ASC
    """
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, params)
    return cur.fetchall()


def post_synthetic_webhook(sender_id: str, sender_name: str, text: str) -> dict:
    chat_id = int(sender_id)
    msg_id = random.randint(1, 1_000_000_000)
    upd_id = random.randint(1, 9_999_999_999)
    update = {
        "update_id": upd_id,
        "message": {
            "message_id": msg_id,
            "from": {
                "id": chat_id,
                "is_bot": False,
                "first_name": sender_name,
                "language_code": "en",
            },
            "chat": {"id": chat_id, "first_name": sender_name, "type": "private"},
            "date": int(time.time()),
            "text": text,
        },
    }
    body = json.dumps(update).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET,
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.HTTPError as e:
        if e.code not in (200, 204):
            raise
    return update


def wait_for_reply(cur, sender_id: str, since_ts) -> dict | None:
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


def grade(
    reply_text: str,
    expected: list[str] | None,
    forbidden: list[str] | None,
    *,
    expected_any: list[str] | None = None,
) -> tuple[bool, str | None]:
    if not reply_text:
        return False, "no reply text captured"
    rt = reply_text.lower()
    exp = expected or []
    if expected_any:
        if not any(s.lower() in rt for s in expected_any):
            return False, f"missing any-of: {expected_any[:3]}"
    else:
        missing = [s for s in exp if s.lower() not in rt]
        if missing:
            return False, f"missing expected: {missing[:3]}"
    found_forbidden = [s for s in (forbidden or []) if s.lower() in rt]
    if found_forbidden:
        return False, f"contained forbidden: {found_forbidden[:3]}"
    return True, None


def record_run(
    cur,
    probe,
    scenario_def,
    sent_update,
    reply_row,
    passed: bool,
    fail_reason: str | None,
    *,
    session_id: int | None = None,
):
    cur.execute(
        """
        INSERT INTO leo_qa_sim_payloads
          (probe_id, sim_sender_id, sim_chat_id, update_id, prompt_text,
           leo_exec_id, leo_reply_text, passed, fail_reason, completed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        RETURNING id
        """,
        (
            probe["id"],
            scenario_def["sim_sender_telegram_id"],
            scenario_def["sim_sender_telegram_id"],
            sent_update["update_id"],
            scenario_def["prompt_text"],
            (reply_row["execution_id"] if reply_row else None),
            (reply_row["reply_text"] if reply_row else None),
            passed,
            fail_reason,
        ),
    )
    payload_id = cur.fetchone()["id"]
    cur.execute(
        "UPDATE leo_qa_probes SET last_run_at = now(), last_status = %s WHERE id = %s",
        ("pass" if passed else "fail", probe["id"]),
    )
    cur.execute(
        "INSERT INTO leo_qa_runs (probe_id, status, details) VALUES (%s, %s, %s::jsonb)",
        (
            probe["id"],
            "pass" if passed else "fail",
            json.dumps(
                {
                    "reply_excerpt": (reply_row["reply_text"][:300] if reply_row else None),
                    "fail_reason": fail_reason,
                    "session_id": session_id,
                }
            ),
        ),
    )
    if session_id:
        cur.execute(
            """
            INSERT INTO simulator_session_results
              (session_id, probe_id, probe_name, payload_id, passed, fail_reason)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (session_id, probe["id"], probe["name"], payload_id, passed, fail_reason),
        )
    if not passed:
        cur.execute(
            """
            INSERT INTO leo_qa_violations (probe_id, severity, details, leo_exec_id, alerted_at)
            VALUES (%s, %s, %s::jsonb, %s, now())
            ON CONFLICT (probe_id, leo_exec_id) DO NOTHING
            """,
            (
                probe["id"],
                probe["severity"],
                json.dumps(
                    {
                        "fail_reason": fail_reason,
                        "reply_excerpt": (reply_row["reply_text"][:300] if reply_row else None),
                        "prompt": scenario_def["prompt_text"],
                    }
                ),
                (reply_row["execution_id"] if reply_row else f"sim-{sent_update['update_id']}"),
            ),
        )
    else:
        cur.execute(
            "UPDATE leo_qa_violations SET closed_at = now() WHERE probe_id = %s AND closed_at IS NULL",
            (probe["id"],),
        )
    return payload_id


def run_one_probe(cur, probe, *, session_id: int | None = None) -> dict:
    scenario_def = probe["definition"]
    sender_id = scenario_def["sim_sender_telegram_id"]
    sender_name = "Sim" + str(sender_id)[-3:]
    prompt_text = scenario_def["prompt_text"]
    ts_before = now_utc()
    sent = post_synthetic_webhook(sender_id, sender_name, prompt_text)
    reply = wait_for_reply(cur, sender_id, ts_before)
    passed, fail_reason = grade(
        (reply or {}).get("reply_text", ""),
        scenario_def.get("expected_substrings"),
        scenario_def.get("forbidden_substrings"),
        expected_any=scenario_def.get("expected_any"),
    )
    record_run(cur, probe, scenario_def, sent, reply, passed, fail_reason, session_id=session_id)
    return {
        "probe": probe["name"],
        "passed": passed,
        "fail_reason": fail_reason,
        "reply_excerpt": ((reply or {}).get("reply_text") or "")[:300],
    }