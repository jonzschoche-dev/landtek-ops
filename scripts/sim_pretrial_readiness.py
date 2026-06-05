#!/usr/bin/env python3
"""sim_pretrial_readiness.py — phone-friendly trial-readiness scorecard.

Per-category health from 24h sim runs + pretrial timeline + filing gaps
+ improvement loop state. One screen, ~20 second read.

Replaces parts of sim_daily_digest for the morning push (the existing
daily digest stays for backward-compatible monitoring).

Run on-demand:
    python3 /root/landtek/scripts/sim_pretrial_readiness.py
"""
from __future__ import annotations
import os, sys
from datetime import datetime, timezone, timedelta
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

PRETRIAL_TARGET = datetime(2026, 8, 1, tzinfo=timezone.utc)  # approximate — adjust as confirmed

CATEGORY_DISPLAY = [
    ("mandate",          "Mandate invariants"),
    ("security",         "Impersonation defense"),
    ("evidence_trail",   "Title chain literacy"),
    ("filing_discipline","Evidence trail navigation"),
    ("phrasing",         "Refusal phrasing"),
    ("capability",       "Capability honesty"),
    ("onboarding",       "Onboarding flow"),
    ("infrastructure",   "System health"),
    ("business",         "Business health"),
]


def bar(pct, width=12):
    fill = int(round(width * pct / 100))
    return "█" * fill + "░" * (width - fill)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    title = f"📋 Pretrial Readiness — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
    print(f"\n┌{'─'*76}┐\n│ {title:<74} │\n└{'─'*76}┘")

    print("\n┌─── HEALTH BY DIMENSION (last 24h) ───────────────────────────────────────────────┐")
    cur.execute("""
        SELECT COALESCE(p.category, 'other') AS category,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE s.passed) AS passes
          FROM leo_qa_probes p
          LEFT JOIN leo_qa_sim_payloads s
            ON s.probe_id = p.id AND s.posted_at > now() - interval '24 hours'
         WHERE p.active = true
         GROUP BY p.category
    """)
    rows = {r["category"]: r for r in cur.fetchall()}
    for cat, label in CATEGORY_DISPLAY:
        r = rows.get(cat) or {"total": 0, "passes": 0}
        total, passes = r["total"] or 0, r["passes"] or 0
        if total == 0:
            print(f"  {label:30s}  not measured                            —")
            continue
        pct = round(100.0 * passes / total, 1)
        glyph = "✓" if pct >= 90 else ("⚠️" if pct >= 50 else "✗")
        print(f"  {label:30s}  {bar(pct)}  {pct:5.1f}% ({passes:3d}/{total:3d})  {glyph}")

    print("└──────────────────────────────────────────────────────────────────────────────────┘")

    print("\n┌─── PRETRIAL TIMELINE ─────────────────────────────────────────────────────────────┐")
    days_to_pretrial = (PRETRIAL_TARGET - datetime.now(timezone.utc)).days
    cur.execute("SELECT COUNT(*) FROM claims WHERE status = 'open'")
    open_claims = cur.fetchone()["count"]
    cur.execute("""
        SELECT COUNT(*) AS n FROM (
            SELECT c.id FROM claims c
              LEFT JOIN evidence_trail et ON et.claim_id = c.id AND et.weight='primary'
             WHERE c.status='open'
             GROUP BY c.id
            HAVING COUNT(et.id) >= 2
        ) t
    """)
    well_supported = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) FROM v_filing_gaps")
    gaps = cur.fetchone()["count"]
    print(f"  Days to pretrial (target):                {days_to_pretrial}")
    print(f"  Active claims (open):                     {open_claims}")
    print(f"  Claims with ≥2 primary exhibits:          {well_supported}")
    print(f"  Claims with filing gaps:                  {gaps}")
    print(f"    └─ see: scripts/list_filing_gaps.py")
    print("└──────────────────────────────────────────────────────────────────────────────────┘")

    print("\n┌─── SECURITY POSTURE ─────────────────────────────────────────────────────────────┐")
    cur.execute("""
        SELECT COUNT(*) FROM sim_leak_incidents
         WHERE detected_at > now() - interval '24 hours'
    """)
    leaks = cur.fetchone()["count"]
    print(f"  Sim leaks (24h):                          {leaks}    {'✓' if leaks == 0 else '🚨'}")
    cur.execute("""
        SELECT COUNT(*) AS n
          FROM leo_qa_sim_payloads s JOIN leo_qa_probes p ON p.id=s.probe_id
         WHERE p.category IN ('security','mandate')
           AND s.posted_at > now() - interval '24 hours'
           AND NOT s.passed
    """)
    security_fails = cur.fetchone()["n"]
    print(f"  Security/mandate fails (24h):             {security_fails}    "
          f"{'✓' if security_fails < 5 else ('⚠️' if security_fails < 20 else '✗')}")
    print("└──────────────────────────────────────────────────────────────────────────────────┘")

    print("\n┌─── IMPROVEMENT LOOP STATE ───────────────────────────────────────────────────────┐")
    cur.execute("SELECT COUNT(*) AS n FROM leo_improvement_proposals WHERE status='pending'")
    pending = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM leo_improvement_proposals WHERE status='applied'")
    applied = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM leo_improvement_proposals WHERE status='verified' AND verified_at > now() - interval '24 hours'")
    verified_today = cur.fetchone()["n"]
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE active) AS active
          FROM leo_qa_probes WHERE rail='sim'
    """)
    library = cur.fetchone()["active"]
    print(f"  Pending proposals:                        {pending}")
    print(f"  Applied (awaiting verify):                {applied}")
    print(f"  Verified in last 24h:                     {verified_today}")
    print(f"  Sim probe library (active):               {library}")
    print("└──────────────────────────────────────────────────────────────────────────────────┘")
    print()
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
