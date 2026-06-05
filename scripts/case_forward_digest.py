#!/usr/bin/env python3
"""case_forward_digest.py — replaces sim_daily_digest, leads with ACTION.

Sent once daily at 23:00 UTC (7am Manila). Structure:

  THE ONE THING — single highest-leverage action for today
  CASE ADVANCED YESTERDAY — what concretely moved (claims linked, obligations
                            marked done, evidence_trail rows added, etc.)
                            Silent if nothing moved (no false celebration).
  STALLED ITEMS — obligations / claims / events not moving for ≥3 days
                  (this is where leverage hides)
  PENDING QUEUE — counts only, no breakdown (you can drill in if needed)
  HEALTH FOOTER — one line. Only if something is wrong.

Suppresses entirely if everything is stale AND no actionable items.
"""
from __future__ import annotations
import os, sys
from datetime import datetime, timezone, timedelta
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
from report_publisher import push_strict

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"


def compute_next_action(cur) -> tuple[str, str] | None:
    """Return (label, action_command) for highest-leverage next move."""
    # Priority 1: any overdue obligation
    cur.execute("""
        SELECT id, short_label, client_code FROM v_obligations_at_risk
         WHERE risk_window = 'overdue' LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        return (f"⚠️ OBLIGATION OVERDUE: [{r['client_code']}] {r['short_label']}",
                f"Address obligation #{r['id']} immediately. "
                f"View: SELECT * FROM landtek_obligations WHERE id={r['id']}")

    # Priority 2: any priority-5 claim with zero exhibits
    cur.execute("""
        SELECT c.id, c.short_label
          FROM claims c
          LEFT JOIN evidence_trail et ON et.claim_id = c.id
         WHERE c.status='open' AND c.priority=5
         GROUP BY c.id
        HAVING COUNT(et.id) = 0
         LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        # See if there's a high-confidence proposal for this claim
        cur.execute("""
            SELECT COUNT(*) FROM evidence_trail_proposals
             WHERE claim_id=%s AND status='pending' AND confidence >= 0.85
        """, (r["id"],))
        hi = cur.fetchone()["count"]
        if hi > 0:
            return (f"📎 LINK EXHIBITS: priority-5 claim [{r['short_label']}] has 0 exhibits but {hi} high-confidence proposals waiting",
                    f"psql -c \"UPDATE evidence_trail_proposals SET status='approved' "
                    f"WHERE claim_id={r['id']} AND status='pending' AND confidence >= 0.85\"")
        return (f"📎 LINK EXHIBITS: priority-5 claim [{r['short_label']}] has 0 exhibits and no high-conf proposals",
                f"Manually identify which LT-NNNNs support this claim and INSERT into evidence_trail")

    # Priority 3: pretrial readiness if pretrial < 60 days
    cur.execute("""
        SELECT id, short_label, scheduled_for,
               (scheduled_for - now()) AS time_until,
               req_total, req_done, readiness_pct
          FROM v_upcoming_events_30d
         WHERE event_kind = 'court_hearing'
        UNION ALL
        SELECT id, short_label, scheduled_for,
               (scheduled_for - now()) AS time_until,
               (SELECT COUNT(*) FROM prep_requirements WHERE event_id=case_events.id) AS req_total,
               (SELECT COUNT(*) FROM prep_requirements WHERE event_id=case_events.id AND status='done') AS req_done,
               0.0 AS readiness_pct
          FROM case_events WHERE event_kind='court_hearing' AND status='upcoming'
            AND scheduled_for < now() + interval '90 days'
            AND id NOT IN (SELECT id FROM v_upcoming_events_30d)
         LIMIT 1
    """)
    rows = cur.fetchall()
    for r in rows:
        days = r["time_until"].days if hasattr(r["time_until"], "days") else 0
        if days <= 60 and (r["req_done"] or 0) < (r["req_total"] or 1) * 0.8:
            return (f"🏛 PRETRIAL PREP: {r['short_label']} in {days}d at {r['readiness_pct']}%",
                    f"Mark prep_requirements done OR add new ones via psql; cite LT-NNNNs as you go")

    # Priority 4: high-confidence evidence proposals waiting
    cur.execute("SELECT COUNT(*) FROM evidence_trail_proposals WHERE status='pending' AND confidence >= 0.85")
    hi = cur.fetchone()["count"]
    if hi >= 3:
        return (f"📋 APPROVE PROPOSALS: {hi} high-confidence evidence proposals ready",
                f"psql -c \"UPDATE evidence_trail_proposals SET status='approved' "
                f"WHERE status='pending' AND confidence >= 0.85\"")

    # Priority 5: any pending leo improvement proposal
    cur.execute("""SELECT id, failure_pattern FROM leo_improvement_proposals
                    WHERE status='pending' ORDER BY id LIMIT 1""")
    r = cur.fetchone()
    if r:
        return (f"🧠 REVIEW LEO PROPOSAL #{r['id']}: {r['failure_pattern'][:80]}",
                f"python3 scripts/leo_proposal_apply.py {r['id']} --dry  (preview)\n"
                f"python3 scripts/leo_proposal_apply.py {r['id']}        (apply)")

    return None


def compute_yesterday_advances(cur) -> list[str]:
    """What concretely moved in last 24h? Empty list = nothing to celebrate."""
    advances = []
    cur.execute("SELECT COUNT(*) FROM evidence_trail WHERE added_at > now() - interval '24 hours'")
    n = cur.fetchone()["count"]
    if n:
        advances.append(f"+{n} new exhibit→claim links in evidence_trail")
    cur.execute("""SELECT COUNT(*) FROM landtek_obligations
                    WHERE updated_at > now() - interval '24 hours' AND status='done'""")
    n = cur.fetchone()["count"]
    if n:
        advances.append(f"+{n} obligations marked done")
    cur.execute("""SELECT COUNT(*) FROM prep_requirements
                    WHERE completed_at > now() - interval '24 hours'""")
    n = cur.fetchone()["count"]
    if n:
        advances.append(f"+{n} prep_requirements completed")
    cur.execute("""SELECT COUNT(*) FROM leo_improvement_proposals
                    WHERE verified_at > now() - interval '24 hours' AND status='verified'""")
    n = cur.fetchone()["count"]
    if n:
        advances.append(f"+{n} Leo improvement proposals verified with positive delta")
    cur.execute("""SELECT COUNT(*) FROM documents
                    WHERE doc_role IS NOT NULL AND doc_role != 'not_yet_assessed'
                      AND updated_at > now() - interval '24 hours'""")
    n = cur.fetchone()["count"]
    if n:
        advances.append(f"+{n} documents got doc_role assigned")
    cur.execute("""SELECT COUNT(*) FROM case_events
                    WHERE status='done' AND updated_at > now() - interval '24 hours'""")
    n = cur.fetchone()["count"]
    if n:
        advances.append(f"+{n} case_events completed")
    return advances


def compute_stalled_items(cur) -> list[str]:
    """What hasn't moved in ≥3 days that should have?"""
    stalled = []
    cur.execute("""
        SELECT id, short_label, client_code, EXTRACT(DAY FROM now() - updated_at)::int AS days_stale
          FROM landtek_obligations
         WHERE status='open' AND priority >= 4
           AND updated_at < now() - interval '3 days'
         ORDER BY priority DESC, updated_at LIMIT 3
    """)
    for r in cur.fetchall():
        stalled.append(f"  • Obligation [{r['client_code']}] {r['short_label'][:60]} (stale {r['days_stale']}d)")

    cur.execute("""
        SELECT c.id, c.short_label, EXTRACT(DAY FROM now() - c.updated_at)::int AS days_stale
          FROM claims c
          LEFT JOIN evidence_trail et ON et.claim_id = c.id
         WHERE c.status='open' AND c.priority >= 4
           AND c.updated_at < now() - interval '3 days'
         GROUP BY c.id
        HAVING COUNT(et.id) = 0
         LIMIT 3
    """)
    for r in cur.fetchall():
        stalled.append(f"  • Claim {r['short_label'][:60]}: 0 exhibits, stale {r['days_stale']}d")
    return stalled


def compute_health_issue(cur) -> str | None:
    """One-line health flag, only if something is wrong."""
    cur.execute("SELECT COUNT(*) FROM sim_leak_incidents WHERE detected_at > now() - interval '24 hours'")
    leaks = cur.fetchone()["count"]
    if leaks:
        return f"🚨 {leaks} sim leak(s) in 24h — investigate sim_leak_incidents"
    cur.execute("""SELECT COUNT(*) FROM execution_entity
                    WHERE "workflowId"='vSDQv1vfn6627bnA'
                      AND status='error' AND "startedAt" > now() - interval '1 hour'""")
    errs = cur.fetchone()["count"]
    if errs > 10:
        return f"⚠️ {errs} Leo execs errored in last hour"
    return None


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    next_action = compute_next_action(cur)
    advances = compute_yesterday_advances(cur)
    stalled = compute_stalled_items(cur)
    health = compute_health_issue(cur)

    # Suppress entirely if nothing changed AND nothing stalled AND no action
    if not next_action and not advances and not stalled and not health:
        print("[case_forward] nothing actionable — suppressing")
        return

    # STRICT RAILS (deploy_329): one-line headline → Telegram; full detail → report file.
    # Headline = the ONE THING. Everything else goes in the report.
    headline = f"📋 Case Forward — {datetime.now(timezone.utc):%m-%d}"
    if next_action:
        label, _ = next_action
        # Strip emoji + brackets for the headline
        headline = f"📋 {label[:200]}"
    elif health:
        headline = f"📋 Case Forward — {health[:200]}"
    elif advances:
        headline = f"📋 Case Forward — {advances[0][:200]}"
    elif stalled:
        headline = f"📋 Case Forward — {len(stalled)} item(s) stalled ≥3d"
    else:
        # Nothing actionable AND nothing moving AND no health issue → suppress
        print("[case_forward] truly nothing to report — suppressing")
        return

    # Build the full report (markdown) — everything goes here
    report = [f"## Case Forward — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", ""]
    if next_action:
        label, action = next_action
        report.append(f"### The One Thing Today")
        report.append(f"**{label}**")
        report.append("")
        report.append(f"```")
        report.append(action)
        report.append(f"```")
        report.append("")
    if advances:
        report.append(f"### What Moved Yesterday")
        for a in advances:
            report.append(f"- ✓ {a}")
        report.append("")
    if stalled:
        report.append(f"### Stalled ≥3 Days")
        for s in stalled:
            report.append(s)
        report.append("")
    if health:
        report.append(f"### Health")
        report.append(health)
        report.append("")
    # Queue counts as footer
    cur.execute("""
        SELECT
          (SELECT COUNT(*) FROM evidence_trail_proposals WHERE status='pending') AS evid,
          (SELECT COUNT(*) FROM leo_improvement_proposals WHERE status='pending') AS leo,
          (SELECT COUNT(*) FROM doc_role_proposals WHERE status='pending' AND confidence >= 0.75) AS doc_role
    """)
    q = cur.fetchone()
    report.append(f"### Pending Review")
    report.append(f"- {q['evid']} evidence_trail proposals")
    report.append(f"- {q['leo']} leo_improvement proposals")
    report.append(f"- {q['doc_role']} doc_role proposals (≥0.75 confidence)")

    push_strict(
        headline=headline,
        body_md="\n".join(report),
        source="watchdog",
        slug=f"case-forward-{datetime.now(timezone.utc):%Y%m%d}",
    )
    print(f"[case_forward] pushed headline + report link")


if __name__ == "__main__":
    main()
