#!/usr/bin/env python3
"""sim_monitor.py — adaptive-cadence simulator health monitor (deploy_313).

Cron fires this every 5 min unconditionally. Script self-throttles via
sim_monitor_state.next_check_at — if we're not due yet, exits cheaply.
When due, it:

  1. Computes a 'signature' of the last hour: pass rate, mandate invariant
     pass rate, no-reply count, leak count.
  2. Compares to the previously stored signature.
  3. Classifies the transition:
       - REGRESSION  — pass rate dropped ≥15pp, OR mandate pass rate dropped
                       from ≥0.75 to <0.5, OR ≥1 leak incident in the window.
                       → tighten interval to 5 min + push alert.
       - CHANGE      — pass rate moved ≥10pp in either direction, or mandate
                       status changed by ≥1 probe. → push update; keep
                       current interval.
       - STABLE      — within thresholds. Increment a stable-counter; after
                       3 consecutive stable reads, double interval (cap 60).

  4. Updates sim_monitor_state with the new interval, stable count, and
     signature.
  5. Pushes to Jonathan via tg_send (watchdog, rate-limit exempt) only when
     classification is REGRESSION or CHANGE — silent on STABLE so the
     phone doesn't buzz every 5 min when nothing's moving.

The result: tight visibility when things are unstable; quiet when steady.
"""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

DSN      = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"

# Thresholds for the classifier.
REGRESSION_PASS_DROP_PP   = 15.0   # pass rate fell by ≥15 percentage points
CHANGE_PASS_DELTA_PP      = 10.0   # any movement ≥10pp counts as a CHANGE
REGRESSION_MANDATE_FROM   = 0.75   # mandate pass rate previously ≥ this …
REGRESSION_MANDATE_TO     = 0.50   # … now < this
STABLE_RUNS_TO_BACK_OFF   = 3
INTERVAL_MAX_MIN          = 60
INTERVAL_MIN_MIN          = 5


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sim_monitor_state (
            id                   integer PRIMARY KEY DEFAULT 1,
            last_check_at        timestamptz NOT NULL DEFAULT now(),
            next_check_at        timestamptz NOT NULL DEFAULT now(),
            current_interval_min integer NOT NULL DEFAULT 5,
            consecutive_stable   integer NOT NULL DEFAULT 0,
            last_signature       jsonb,
            last_pushed_at       timestamptz,
            CONSTRAINT sim_monitor_singleton CHECK (id = 1)
        )
    """)
    cur.execute("INSERT INTO sim_monitor_state (id) VALUES (1) ON CONFLICT DO NOTHING")


def compute_signature(cur) -> dict:
    cur.execute("""
        SELECT COUNT(*) AS runs,
               COUNT(*) FILTER (WHERE passed) AS pass,
               COUNT(*) FILTER (WHERE leo_reply_text IS NULL OR leo_reply_text = '') AS no_reply
          FROM leo_qa_sim_payloads
         WHERE posted_at > now() - interval '1 hour'
    """)
    r = cur.fetchone()
    runs, passes, no_reply = r["runs"] or 0, r["pass"] or 0, r["no_reply"] or 0

    cur.execute("""
        SELECT COUNT(*) AS m_total,
               COUNT(*) FILTER (WHERE s.passed) AS m_pass
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE p.name LIKE 'mandate.%'
           AND s.posted_at > now() - interval '1 hour'
    """)
    m = cur.fetchone()
    m_total, m_pass = m["m_total"] or 0, m["m_pass"] or 0

    cur.execute("""
        SELECT COUNT(*) AS leaks
          FROM sim_leak_incidents
         WHERE detected_at > now() - interval '1 hour'
    """)
    leaks = cur.fetchone()["leaks"] or 0

    return {
        "runs": runs,
        "pass": passes,
        "pass_pct": round(100.0 * passes / max(runs, 1), 1),
        "no_reply": no_reply,
        "no_reply_pct": round(100.0 * no_reply / max(runs, 1), 1),
        "mandate_total": m_total,
        "mandate_pass": m_pass,
        "mandate_pass_rate": round(m_pass / max(m_total, 1), 3),
        "leaks": leaks,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def classify(prev: dict | None, cur: dict) -> tuple[str, str]:
    """Return ('regression'|'change'|'stable', reason)."""
    if prev is None:
        return ("change", "first run — baseline established")

    p_old = float(prev.get("pass_pct", 0))
    p_new = float(cur["pass_pct"])

    # Regression checks first.
    if cur["leaks"] > 0:
        return ("regression", f"leak incidents in last hour: {cur['leaks']}")
    if p_old - p_new >= REGRESSION_PASS_DROP_PP:
        return ("regression", f"pass rate dropped {p_old:.1f}% → {p_new:.1f}% (-{p_old-p_new:.1f}pp)")
    m_old = float(prev.get("mandate_pass_rate", 0))
    m_new = float(cur["mandate_pass_rate"])
    if m_old >= REGRESSION_MANDATE_FROM and m_new < REGRESSION_MANDATE_TO and cur["mandate_total"] >= 3:
        return ("regression",
                f"mandate pass rate fell from {m_old:.2f} to {m_new:.2f} "
                f"({cur['mandate_pass']}/{cur['mandate_total']} in last hour)")

    # Change checks.
    delta = p_new - p_old
    if abs(delta) >= CHANGE_PASS_DELTA_PP:
        return ("change", f"pass rate moved {p_old:.1f}% → {p_new:.1f}% ({delta:+.1f}pp)")
    if (prev.get("mandate_pass", -1) != cur["mandate_pass"]
            and cur["mandate_total"] >= 3 and prev.get("mandate_total", -1) >= 3):
        return ("change",
                f"mandate pass count: {prev.get('mandate_pass', '?')} → {cur['mandate_pass']}")

    return ("stable", f"within thresholds ({p_old:.1f}% → {p_new:.1f}%)")


def next_interval(classification: str, current: int, consecutive_stable: int) -> tuple[int, int]:
    """Return (new_interval_min, new_consecutive_stable)."""
    if classification == "regression":
        return (INTERVAL_MIN_MIN, 0)
    if classification == "change":
        return (current, 0)
    # stable
    new_stable = consecutive_stable + 1
    if new_stable >= STABLE_RUNS_TO_BACK_OFF:
        return (min(current * 2, INTERVAL_MAX_MIN), 0)
    return (current, new_stable)


def format_alert(classification: str, reason: str, sig: dict, prev: dict | None,
                 new_interval: int, old_interval: int) -> str:
    glyph = {"regression": "🚨", "change": "📡", "stable": "📊"}[classification]
    head = {"regression": "REGRESSION", "change": "Change detected", "stable": "Stable"}[classification]
    lines = [
        f"{glyph} <b>{head} — sim monitor</b>",
        f"<i>{reason}</i>",
        "",
        f"<b>Last hour:</b> {sig['runs']} runs · {sig['pass']} pass ({sig['pass_pct']}%) · {sig['no_reply']} no-reply",
        f"<b>Mandate invariants:</b> {sig['mandate_pass']}/{sig['mandate_total']} "
        f"(rate {sig['mandate_pass_rate']})",
        f"<b>Leaks (1h):</b> {sig['leaks']}",
    ]
    if prev is not None and classification != "stable":
        lines.append("")
        lines.append("<b>Δ from previous read:</b>")
        for k in ("pass_pct", "no_reply_pct", "mandate_pass_rate"):
            old = prev.get(k)
            new = sig.get(k)
            if old is not None and new is not None and old != new:
                lines.append(f"  {k}: {old} → {new}")
    if old_interval != new_interval:
        lines.append("")
        lines.append(f"<b>Cadence:</b> interval {old_interval}m → {new_interval}m")
    return "\n".join(lines)


def alert(text: str):
    if tg_send is None:
        print(text); return
    try:
        tg_send(JONATHAN, text, source="watchdog",
                recipient_name="Jonathan", override_rate_limit=True)
    except Exception as e:
        print(f"[monitor] tg_send failed: {e}", file=sys.stderr)
        print(text)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_schema(cur)
        cur.execute("SELECT * FROM sim_monitor_state WHERE id=1 FOR UPDATE")
        state = cur.fetchone()
        if datetime.now(timezone.utc) < state["next_check_at"]:
            print(f"[monitor] not due until {state['next_check_at']}; skipping")
            conn.rollback(); return

        sig = compute_signature(cur)
        prev_sig = state.get("last_signature") or None
        classification, reason = classify(prev_sig, sig)
        new_interval, new_stable = next_interval(
            classification, state["current_interval_min"], state["consecutive_stable"]
        )
        push = classification in ("regression", "change")

        cur.execute("""
            UPDATE sim_monitor_state
               SET last_check_at        = now(),
                   next_check_at        = now() + (%s || ' minutes')::interval,
                   current_interval_min = %s,
                   consecutive_stable   = %s,
                   last_signature       = %s::jsonb,
                   last_pushed_at       = CASE WHEN %s THEN now() ELSE last_pushed_at END
             WHERE id = 1
        """, (new_interval, new_interval, new_stable, json.dumps(sig), push))
        conn.commit()

        print(f"[monitor] {classification}: {reason} | interval {state['current_interval_min']}m → {new_interval}m | stable_run {new_stable}")
        if push:
            alert(format_alert(classification, reason, sig, prev_sig,
                               new_interval, state["current_interval_min"]))
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
