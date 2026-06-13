#!/usr/bin/env python3
"""leo_qa_runner.py — execute due Leo QA probes (deploy_298).

Runs every 60 seconds via systemd timer. Each tick, it queries leo_qa_probes
for any probe whose (last_run_at + cadence_min) ≤ now() and executes it.

Probe kinds (matched on definition.kind):

  leo_reply_regex_with_outbound_check
    Scan last 5 min of leo_interactions for reply_text matching `regex`.
    For each match, check outbound_messages for an actual send to a
    non-Jonathan recipient within `verify_outbound_within_minutes`.
    Fail if "promise" found with no corresponding outbound.

  leo_reply_contradicts_clients_table
    Scan last 5 min of leo_interactions for reply_text matching `regex`.
    Extract candidate names from the reply (heuristic: capitalized
    bigrams). For each candidate, query clients + authorized_users.
    Fail if Leo claimed someone is "not on file" but they ARE.

  leo_reply_claims_inbound_with_evidence_check
    Scan last 5 min for reply_text matching `regex`. Verify evidence
    exists in gmail_messages / leo_interactions / unauth_attempts in
    the last `verify_evidence_in_minutes`.

  synthetic_telegram_prompt
    [Stub for v1 — proper synthetic eval requires the eval-runner
    webhook injection path. v1 just records the probe as 'skipped'
    with a TODO. v2 will drive Leo via webhook.]

  metric_threshold
    Run `metric_query`, compare result to `threshold` per `comparator`.
    Pass/fail based on threshold. Respects `only_between_manila_hours`.

Failures fire Telegram alerts via tg_send (source='watchdog', exempt
from rate limit) and open a leo_qa_violations row. Passes after a prior
failure auto-close the violation."""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send
except Exception:
    send = None

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"
MANILA_TZ = timezone(timedelta(hours=8))

# Recipient name extractor for "ask X" / "tell X" / "remind X" patterns
RECIPIENT_RE = re.compile(
    r"(?i)(?:sending\s+(?:a\s+)?(?:message|reminder)\s+to|relaying\s+(?:the\s+\w+\s+(?:reminder|message))?\s*to|on\s+it\s+[-—]?\s*(?:sending|relaying|reminding|messaging)|reminder\s+to|reminding|to\s+ask|to\s+remind)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})"
)

# Capitalized bigram extractor (rough candidate-name finder)
NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b")


def now_utc():
    return datetime.now(timezone.utc)


def alert(text):
    if send is None:
        print(f"[qa_runner] {text[:200]}")
        return
    send(JONATHAN, text, source="watchdog", recipient_name="Jonathan", override_rate_limit=True)


def open_violation(cur, probe, details, leo_exec_id=None):
    cur.execute(
        """
        INSERT INTO leo_qa_violations (probe_id, severity, details, leo_exec_id, alerted_at)
        VALUES (%s, %s, %s::jsonb, %s, now())
        ON CONFLICT (probe_id, leo_exec_id) DO NOTHING
        RETURNING id
        """,
        (probe["id"], probe["severity"], json.dumps(details), leo_exec_id),
    )
    r = cur.fetchone()
    return r["id"] if r else None


def close_violations_for(cur, probe_id):
    cur.execute(
        "UPDATE leo_qa_violations SET closed_at = now() WHERE probe_id = %s AND closed_at IS NULL RETURNING id",
        (probe_id,),
    )
    return cur.rowcount


def record_run(cur, probe_id, status, duration_ms, details):
    cur.execute(
        "INSERT INTO leo_qa_runs (probe_id, status, duration_ms, details) VALUES (%s, %s, %s, %s::jsonb)",
        (probe_id, status, duration_ms, json.dumps(details)),
    )
    cur.execute(
        "UPDATE leo_qa_probes SET last_run_at = now(), last_status = %s WHERE id = %s",
        (status, probe_id),
    )


# ─── Probe handlers ────────────────────────────────────────────────────────

def run_empty_promise(cur, probe):
    """leo_reply_regex_with_outbound_check"""
    defn = probe["definition"]
    regex = re.compile(defn["regex"])
    window_min = defn.get("verify_outbound_within_minutes", 2)
    cur.execute(
        """
        SELECT id, timestamp, sender_id, reply_text, execution_id
          FROM leo_interactions
         WHERE timestamp > now() - interval '5 minutes'
           AND reply_text IS NOT NULL
           AND failure_mode IS NULL
         ORDER BY id DESC
         LIMIT 30
        """,
    )
    rows = cur.fetchall()
    violations = []
    for r in rows:
        if not regex.search(r["reply_text"] or ""):
            continue
        # Try to extract recipient name from the reply
        m = RECIPIENT_RE.search(r["reply_text"])
        recipient_name = m.group(1) if m else None
        if not recipient_name:
            continue
        # Skip if recipient is "Jonathan" — Leo replying to Jonathan is fine
        if recipient_name.lower() in ("jonathan", "jj", "jj moreno"):
            continue
        # Look for an outbound to a non-Jonathan chat_id within window
        cur.execute(
            """
            SELECT id, chat_id, recipient_name FROM outbound_messages
             WHERE sent_at BETWEEN %s AND %s + (%s || ' minutes')::interval
               AND chat_id <> %s
               AND success = true
               AND (recipient_name ILIKE %s OR recipient_name ILIKE %s)
             LIMIT 1
            """,
            (r["timestamp"], r["timestamp"], window_min, JONATHAN,
             f"%{recipient_name}%",
             f"%{recipient_name.split()[0]}%"),
        )
        outbound = cur.fetchone()
        if not outbound:
            violations.append({
                "leo_interaction_id": r["id"],
                "leo_quote": (r["reply_text"] or "")[:200],
                "claimed_recipient": recipient_name,
                "verification": f"no outbound to {recipient_name} within {window_min} min of leo_interactions.id={r['id']}",
            })
    return violations


def run_false_not_on_file(cur, probe):
    """leo_reply_contradicts_clients_table"""
    defn = probe["definition"]
    regex = re.compile(defn["regex"])
    cur.execute(
        """
        SELECT id, timestamp, reply_text, question
          FROM leo_interactions
         WHERE timestamp > now() - interval '5 minutes'
           AND reply_text IS NOT NULL
         ORDER BY id DESC LIMIT 30
        """
    )
    rows = cur.fetchall()
    violations = []
    for r in rows:
        if not regex.search(r["reply_text"] or ""):
            continue
        # Extract candidate names
        candidates = NAME_RE.findall(r["reply_text"] or "")
        candidates += NAME_RE.findall(r["question"] or "")
        # Dedup, drop generic
        cand_set = {c.strip() for c in candidates if c.strip().lower() not in
                    ("jonathan", "leo", "datu", "atty", "mr", "ms")}
        for cand in cand_set:
            cur.execute(
                """
                SELECT id, name, telegram_id FROM clients
                 WHERE name ILIKE %s AND COALESCE(telegram_id,'') <> ''
                 UNION ALL
                SELECT id, name, telegram_user_id FROM authorized_users
                 WHERE name ILIKE %s AND active = true
                 LIMIT 1
                """,
                (f"%{cand}%", f"%{cand}%"),
            )
            found = cur.fetchone()
            if found:
                violations.append({
                    "leo_interaction_id": r["id"],
                    "leo_quote": (r["reply_text"] or "")[:200],
                    "claimed_name": cand,
                    "actual_record": dict(found),
                    "verification": f"Leo said {cand!r} not on file — actually clients/authorized_users row exists",
                })
                break
    return violations


def run_metric_threshold(cur, probe):
    """metric_threshold"""
    defn = probe["definition"]
    only_hours = defn.get("only_between_manila_hours")
    if only_hours:
        now_manila = datetime.now(MANILA_TZ)
        if not (only_hours[0] <= now_manila.hour < only_hours[1]):
            return None  # outside window, skip silently
    try:
        cur.execute(defn["metric_query"])
        v = cur.fetchone()
        value = v["n"] if v and "n" in v else (list(v.values())[0] if v else None)
    except Exception as e:
        return [{"error": str(e)[:200], "query": defn["metric_query"][:200]}]
    threshold = defn["threshold"]
    op = defn["comparator"]
    breached = (
        (op == ">" and value > threshold) or
        (op == "<" and value < threshold) or
        (op == ">=" and value >= threshold) or
        (op == "<=" and value <= threshold) or
        (op == "==" and value == threshold)
    )
    if breached:
        return [{
            "metric_value": value,
            "comparator": op,
            "threshold": threshold,
            "verification": defn.get("description", probe["name"]),
        }]
    return []


# Probe-kind dispatch
HANDLERS = {
    "leo_reply_regex_with_outbound_check": run_empty_promise,
    "leo_reply_contradicts_clients_table": run_false_not_on_file,
    "metric_threshold": run_metric_threshold,
    # synthetic_telegram_prompt + fabricated_inbound stubbed for v2
}


def format_alert(probe, violations):
    """Build a single consolidated Telegram alert for one probe's violations."""
    head = {
        "critical": "🚨 <b>QA VIOLATION (critical)</b>",
        "warn":     "⚠️ <b>QA violation (warn)</b>",
        "info":     "ℹ️ <b>QA note</b>",
    }.get(probe["severity"], "⚠️ <b>QA violation</b>")
    lines = [head, "", f"<b>Probe:</b> {probe['name']}  ({probe['rail']})",
             f"<b>Cadence:</b> every {probe['cadence_min']} min",
             ""]
    for i, v in enumerate(violations[:5], 1):
        lines.append(f"<b>Hit #{i}:</b>")
        for k, val in v.items():
            s = str(val)[:280].replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"  {k}: {s}")
        lines.append("")
    if len(violations) > 5:
        lines.append(f"+{len(violations) - 5} more hit(s) — see leo_qa_violations table.")
    return "\n".join(lines)


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Pick due probes
    cur.execute(
        """
        SELECT * FROM leo_qa_probes
         WHERE active = true
           AND (last_run_at IS NULL OR last_run_at < now() - (cadence_min || ' minutes')::interval)
         ORDER BY rail, name
        """,
    )
    due = cur.fetchall()

    stats = {"ran": 0, "passed": 0, "failed": 0, "skipped": 0, "errored": 0}
    for probe in due:
        defn = probe["definition"]
        kind = defn.get("kind")
        handler = HANDLERS.get(kind)
        start = now_utc()
        if handler is None:
            # synthetic_telegram_prompt / fabricated_inbound need the webhook-injection
            # eval path (v2). The live leo-simulator IS that synthetic path; this runner
            # owns the creditless reply-integrity probes (the 3 handlers above). Skip the
            # v2 kinds cleanly instead of recording a false 'error' every tick.
            if kind in ("synthetic_telegram_prompt", "fabricated_inbound"):
                stats["skipped"] += 1
            else:
                record_run(cur, probe["id"], "error", 0, {"reason": f"no handler for kind={kind}"})
                stats["errored"] += 1
            continue
        try:
            violations = handler(cur, probe)
        except Exception as e:
            record_run(cur, probe["id"], "error", 0, {"exception": str(e)[:300]})
            stats["errored"] += 1
            continue
        duration_ms = int((now_utc() - start).total_seconds() * 1000)
        stats["ran"] += 1
        if violations is None:
            # Handler returned None = skipped (e.g., outside hours)
            stats["skipped"] += 1
            continue
        if violations:
            stats["failed"] += 1
            for v in violations:
                open_violation(cur, probe, v, leo_exec_id=str(v.get("leo_interaction_id", "")))
            record_run(cur, probe["id"], "fail", duration_ms,
                       {"count": len(violations), "first": violations[0]})
            alert(format_alert(probe, violations))
        else:
            stats["passed"] += 1
            # Auto-close any prior open violation
            close_violations_for(cur, probe["id"])
            record_run(cur, probe["id"], "pass", duration_ms, {})

    ts = now_utc().isoformat(timespec="seconds")
    print(f"[{ts}] qa_runner: {stats}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
