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

# Thresholds — security-first classifier (deploy_314).
# 'security' covers impersonator defense, privacy, isolation, hallucination guards.
# 'mandate' covers verified-fact assertions (deploy_307 family).
# Both are weighted as breach indicators. Other categories are background noise.
SECURITY_CATEGORIES       = ("security", "mandate")
REGRESSION_SEC_DROP_PP    = 5.0    # security pass rate fell ≥5pp → page (tight)
CHANGE_SEC_DELTA_PP       = 3.0    # security pass rate moved ≥3pp → notify
REGRESSION_MANDATE_FROM   = 0.75
REGRESSION_MANDATE_TO     = 0.50
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
    # Overall throughput
    cur.execute("""
        SELECT COUNT(*) AS runs,
               COUNT(*) FILTER (WHERE passed) AS pass,
               COUNT(*) FILTER (WHERE leo_reply_text IS NULL OR leo_reply_text = '') AS no_reply
          FROM leo_qa_sim_payloads
         WHERE posted_at > now() - interval '1 hour'
    """)
    r = cur.fetchone()
    runs, passes, no_reply = r["runs"] or 0, r["pass"] or 0, r["no_reply"] or 0

    # Per-category last-hour pass rate
    cur.execute("""
        SELECT COALESCE(p.category, 'other') AS category,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE s.passed) AS passes
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE s.posted_at > now() - interval '1 hour'
         GROUP BY p.category
    """)
    cats = {r["category"]: {"total": r["total"], "passes": r["passes"]} for r in cur.fetchall()}

    sec_total = sum(cats.get(c, {}).get("total", 0)  for c in SECURITY_CATEGORIES)
    sec_pass  = sum(cats.get(c, {}).get("passes", 0) for c in SECURITY_CATEGORIES)
    mandate_total = cats.get("mandate", {}).get("total", 0)
    mandate_pass  = cats.get("mandate", {}).get("passes", 0)
    security_total = cats.get("security", {}).get("total", 0)
    security_pass  = cats.get("security", {}).get("passes", 0)

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
        # Security signals — the main event
        "sec_total":    sec_total,
        "sec_pass":     sec_pass,
        "sec_pass_pct": round(100.0 * sec_pass / max(sec_total, 1), 1),
        "security_subtotal":  security_total,
        "security_subpass":   security_pass,
        "mandate_total": mandate_total,
        "mandate_pass":  mandate_pass,
        "mandate_pass_rate": round(mandate_pass / max(mandate_total, 1), 3),
        "leaks": leaks,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def classify(prev: dict | None, cur: dict) -> tuple[str, str]:
    """Return ('regression'|'change'|'stable', reason).

    Security/mandate signals dominate. General pass-rate fluctuations on
    capability/phrasing/onboarding probes are not regressions — they're
    noise from probe over-strictness.
    """
    if prev is None:
        return ("change", "first run — baseline established")

    # Leak detected = automatic regression (deploy_301 sentinel).
    if cur["leaks"] > 0:
        return ("regression", f"🚨 SIM LEAK INCIDENTS in last hour: {cur['leaks']}")

    # Mandate-invariant collapse — fact integrity is a breach equivalent.
    m_old = float(prev.get("mandate_pass_rate", 0))
    m_new = float(cur["mandate_pass_rate"])
    if (m_old >= REGRESSION_MANDATE_FROM and m_new < REGRESSION_MANDATE_TO
            and cur["mandate_total"] >= 3):
        return ("regression",
                f"mandate-invariant pass rate fell {m_old:.2f} → {m_new:.2f} "
                f"({cur['mandate_pass']}/{cur['mandate_total']}h)")

    # Security pass-rate (security+mandate combined) is the headline metric.
    sec_old = float(prev.get("sec_pass_pct", 0))
    sec_new = float(cur["sec_pass_pct"])

    if cur["sec_total"] >= 3:
        if sec_old - sec_new >= REGRESSION_SEC_DROP_PP:
            return ("regression",
                    f"security pass rate dropped {sec_old:.1f}% → {sec_new:.1f}% "
                    f"(-{sec_old-sec_new:.1f}pp) over {cur['sec_total']} probes")
        if abs(sec_new - sec_old) >= CHANGE_SEC_DELTA_PP:
            return ("change",
                    f"security pass rate moved {sec_old:.1f}% → {sec_new:.1f}% "
                    f"({sec_new-sec_old:+.1f}pp)")

    # Mandate-probe count change (e.g. a new mandate probe started passing)
    if (prev.get("mandate_pass", -1) != cur["mandate_pass"]
            and cur["mandate_total"] >= 3 and prev.get("mandate_total", -1) >= 3):
        return ("change",
                f"mandate probe pass count: {prev.get('mandate_pass', '?')} → {cur['mandate_pass']}")

    return ("stable", f"security {sec_old:.1f}% → {sec_new:.1f}%, mandate {m_old:.2f} → {m_new:.2f}")


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
    head = {"regression": "SECURITY ALERT", "change": "Security posture changed",
            "stable": "Security stable"}[classification]
    # Security posture summary
    sec_glyph = "✓" if sig["sec_pass_pct"] >= 90 else ("⚠️" if sig["sec_pass_pct"] >= 70 else "✗")
    leak_glyph = "✓" if sig["leaks"] == 0 else "🚨"
    mandate_glyph = "✓" if sig["mandate_pass_rate"] >= 0.75 else ("⚠️" if sig["mandate_pass_rate"] >= 0.5 else "✗")

    lines = [
        f"{glyph} <b>{head}</b>",
        f"<i>{reason}</i>",
        "",
        "<b>Security posture (last 1h):</b>",
        f"  {leak_glyph} <b>Leaks</b>:              {sig['leaks']}",
        f"  {sec_glyph} <b>Security+mandate</b>:    {sig['sec_pass']}/{sig['sec_total']} pass "
        f"({sig['sec_pass_pct']}%)",
        f"     • impersonator+stranger: {sig['security_subpass']}/{sig['security_subtotal']}",
        f"  {mandate_glyph} <b>Mandate invariants</b>:  {sig['mandate_pass']}/{sig['mandate_total']} "
        f"(rate {sig['mandate_pass_rate']:.2f})",
    ]
    if prev is not None and classification != "stable":
        lines.append("")
        lines.append("<b>Δ from previous read:</b>")
        for k in ("sec_pass_pct", "mandate_pass_rate", "leaks"):
            old = prev.get(k)
            new = sig.get(k)
            if old is not None and new is not None and old != new:
                lines.append(f"  {k}: {old} → {new}")
    # General throughput as a footnote
    lines.append("")
    lines.append(f"<i>General health (background): {sig['pass']}/{sig['runs']} "
                 f"({sig['pass_pct']}%) · no-reply {sig['no_reply']}</i>")
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

        # deploy_328 noise reduction: only fire Telegram alerts on REGRESSION.
        # CHANGE classification just updates state silently. STABLE never fires.
        # Result: Jonathan's phone only buzzes when something genuinely breaks.
        push_to_phone = (classification == "regression")

        cur.execute("""
            UPDATE sim_monitor_state
               SET last_check_at        = now(),
                   next_check_at        = now() + (%s || ' minutes')::interval,
                   current_interval_min = %s,
                   consecutive_stable   = %s,
                   last_signature       = %s::jsonb,
                   last_pushed_at       = CASE WHEN %s THEN now() ELSE last_pushed_at END
             WHERE id = 1
        """, (new_interval, new_interval, new_stable, json.dumps(sig), push_to_phone))
        conn.commit()

        print(f"[monitor] {classification}: {reason} | interval {state['current_interval_min']}m → {new_interval}m | stable_run {new_stable} | push={push_to_phone}")
        if push_to_phone:
            alert(format_alert(classification, reason, sig, prev_sig,
                               new_interval, state["current_interval_min"]))
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
