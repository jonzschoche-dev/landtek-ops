#!/usr/bin/env python3
"""sim_pretrial_readiness.py — trial-readiness scorecard split by intent.

Two top-level views:
  1. BONAFIDE ENGAGEMENT — how well Leo helps authorized users
     (intent = engage_helpfully OR verify_facts)
  2. REFUSAL POSTURE     — how well Leo blocks impersonators/strangers
     (intent = refuse_unauthorized OR gracefully_onboard)

This separates the two distinct quality dimensions so phrasing-driven
refusal noise can't mask whether Leo is getting smarter at helping
Jonathan.
"""
from __future__ import annotations
import os, sys
from datetime import datetime, timezone, timedelta
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
PRETRIAL_TARGET = datetime(2026, 8, 1, tzinfo=timezone.utc)


def bar(pct, width=12):
    fill = int(round(width * pct / 100))
    return "█" * fill + "░" * (width - fill)


def glyph_for(pct):
    return "✓" if pct >= 90 else ("⚠️" if pct >= 50 else "✗")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    title = f"📋 Pretrial Readiness — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
    print(f"\n┌{'─'*78}┐\n│ {title:<76} │\n└{'─'*78}┘")

    # ── BONAFIDE ENGAGEMENT ────────────────────────────────────────────
    print("\n┌─── BONAFIDE ENGAGEMENT (Leo helping authorized users) ─────────────────────────┐")
    cur.execute("""
        SELECT p.category,
               p.intent,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE s.passed) AS passes
          FROM leo_qa_probes p
          LEFT JOIN leo_qa_sim_payloads s
            ON s.probe_id = p.id AND s.posted_at > now() - interval '24 hours'
         WHERE p.active = true
           AND p.intent IN ('engage_helpfully','verify_facts','honest_disclosure')
         GROUP BY p.category, p.intent
         ORDER BY total DESC NULLS LAST
    """)
    bonafide = cur.fetchall()
    overall = {"total": 0, "passes": 0}
    for r in bonafide:
        total, passes = r["total"] or 0, r["passes"] or 0
        if total == 0: continue
        overall["total"] += total
        overall["passes"] += passes
        pct = round(100.0 * passes / total, 1)
        cat = (r["category"] or "—")
        intent = (r["intent"] or "—")
        label = f"{cat:14s} ({intent[:12]})"
        print(f"  {label:30s}  {bar(pct)}  {pct:5.1f}% ({passes:3d}/{total:3d})  {glyph_for(pct)}")
    if overall["total"]:
        opct = round(100.0 * overall["passes"] / overall["total"], 1)
        print(f"  {'─'*78}")
        print(f"  {'OVERALL BONAFIDE':30s}  {bar(opct)}  {opct:5.1f}% "
              f"({overall['passes']:3d}/{overall['total']:3d})  {glyph_for(opct)}")
    print("└──────────────────────────────────────────────────────────────────────────────────┘")

    # ── REFUSAL POSTURE ────────────────────────────────────────────────
    print("\n┌─── REFUSAL POSTURE (Leo blocking impersonators / strangers) ──────────────────┐")
    cur.execute("""
        SELECT p.category,
               p.intent,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE s.passed) AS passes
          FROM leo_qa_probes p
          LEFT JOIN leo_qa_sim_payloads s
            ON s.probe_id = p.id AND s.posted_at > now() - interval '24 hours'
         WHERE p.active = true
           AND p.intent IN ('refuse_unauthorized','gracefully_onboard')
         GROUP BY p.category, p.intent
         ORDER BY total DESC NULLS LAST
    """)
    refusal = cur.fetchall()
    overall_r = {"total": 0, "passes": 0}
    for r in refusal:
        total, passes = r["total"] or 0, r["passes"] or 0
        if total == 0: continue
        overall_r["total"] += total
        overall_r["passes"] += passes
        pct = round(100.0 * passes / total, 1)
        cat = (r["category"] or "—")
        intent = (r["intent"] or "—")
        label = f"{cat:14s} ({intent[:12]})"
        print(f"  {label:30s}  {bar(pct)}  {pct:5.1f}% ({passes:3d}/{total:3d})  {glyph_for(pct)}")
    if overall_r["total"]:
        opct = round(100.0 * overall_r["passes"] / overall_r["total"], 1)
        print(f"  {'─'*78}")
        print(f"  {'OVERALL REFUSAL':30s}  {bar(opct)}  {opct:5.1f}% "
              f"({overall_r['passes']:3d}/{overall_r['total']:3d})  {glyph_for(opct)}")
    print("└──────────────────────────────────────────────────────────────────────────────────┘")

    # ── PRETRIAL TIMELINE ──────────────────────────────────────────────
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
    cur.execute("SELECT COUNT(*) FROM evidence_trail_proposals WHERE status='pending'")
    proposals_pending = cur.fetchone()["count"]
    print(f"  Days to pretrial (target):                {days_to_pretrial}")
    print(f"  Active claims (open):                     {open_claims}")
    print(f"  Claims with ≥2 primary exhibits:          {well_supported}")
    print(f"  Claims with filing gaps:                  {gaps}")
    print(f"  Evidence proposals pending review:        {proposals_pending}")
    print("└──────────────────────────────────────────────────────────────────────────────────┘")

    # ── BONAFIDE TREND (last 3 days, engage_helpfully + verify_facts) ─
    print("\n┌─── BONAFIDE TREND — last 3 days ─────────────────────────────────────────────────┐")
    cur.execute("""
        SELECT date_trunc('day', s.posted_at)::date AS day,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE s.passed) AS passes
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE p.intent IN ('engage_helpfully','verify_facts','honest_disclosure')
           AND s.posted_at > now() - interval '3 days'
         GROUP BY 1 ORDER BY 1
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (no bonafide probe data yet)")
    else:
        for r in rows:
            pct = round(100.0 * r["passes"] / max(r["total"], 1), 1)
            print(f"  {str(r['day']):<12s}  {bar(pct)}  {pct:5.1f}% ({r['passes']:3d}/{r['total']:3d})")
        if len(rows) >= 2:
            first = round(100.0 * rows[0]["passes"] / max(rows[0]["total"], 1), 1)
            last  = round(100.0 * rows[-1]["passes"] / max(rows[-1]["total"], 1), 1)
            arrow = "↑" if last > first + 1 else ("↓" if last < first - 1 else "→")
            print(f"  slope: {first}% → {last}% {arrow}{last-first:+.1f}pp")
    print("└──────────────────────────────────────────────────────────────────────────────────┘")

    # ── LATEST BONAFIDE FAILS (most actionable) ───────────────────────
    print("\n┌─── LATEST BONAFIDE FAILS (Leo should have helped but didn't) ────────────────────┐")
    cur.execute("""
        SELECT p.name, s.posted_at::timestamp(0) AS at,
               LEFT(s.prompt_text, 55) AS prompt,
               LEFT(s.leo_reply_text, 180) AS reply,
               LEFT(s.fail_reason, 60) AS fail
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE p.intent IN ('engage_helpfully','verify_facts')
           AND NOT s.passed
           AND s.posted_at > now() - interval '24 hours'
           AND s.leo_reply_text IS NOT NULL
           AND s.leo_reply_text != ''
         ORDER BY s.id DESC LIMIT 5
    """)
    fails = cur.fetchall()
    if not fails:
        print("  (none in last 24h — bonafide replies all passing or no data)")
    for f in fails:
        print(f"  • {f['name']:60s}")
        print(f"      Q: {f['prompt']!r}")
        print(f"      A: {f['reply'][:140]!r}")
        print(f"      ✗ {f['fail']}")
    print("└──────────────────────────────────────────────────────────────────────────────────┘")
    print()
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
