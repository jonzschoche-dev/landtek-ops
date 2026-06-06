#!/usr/bin/env python3
"""weekly_client_status — Sunday 09:00 Manila digest for MWK-001 client+ops.

Per Jonathan 2026-05-19: a polished, client-facing weekly status for the
MWK-001 estate sent to both Don Qi (Administrator) and Jonathan (Owner).
Audited by Opus before delivery so no un-citable claims ship.

Sections:
  1. Where the case stands (current stage of each active matter)
  2. Recent activity (past 7 days — verified events only)
  3. Upcoming events (next 14 days, confirmed dates only)
  4. Pending action items where Don Qi is the owner
  5. What Leo is watching for next

Routes via comms_send(audience='both', kind='memo'). Strict output_audit.
Pre-delivery Opus audit per [[feedback_opus_pre_delivery_audit]].
"""
import sys
import argparse
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

sys.path.insert(0, "/root/landtek")
import psycopg2, psycopg2.extras

from comms import comms_send  # installs backstop on import

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
CASE_FILE = "MWK-001"


def fetch_case_stages(cur):
    """Current stage of each active matter under MWK-001 (CV-26360 first, then estate, then ARTA dockets)."""
    cur.execute("""
        SELECT matter_code, title, current_stage, next_event, next_deadline, next_event_owner
          FROM matters
         WHERE status = 'active'
           AND (case_file = %s OR matter_code LIKE 'MWK%%')
         ORDER BY
            CASE
              WHEN matter_code LIKE 'MWK-CV%%' THEN 1
              WHEN matter_code = 'MWK-ESTATE' THEN 2
              WHEN matter_code LIKE 'MWK-TCT%%' THEN 3
              ELSE 4 END,
            matter_code
    """, (CASE_FILE,))
    return cur.fetchall()


def fetch_recent_activity(cur, days_back=7):
    """Verified events from the past N days (only doc_date_norm + verified provenance)."""
    cur.execute("""
        SELECT d.id, d.smart_filename, d.classification, d.execution_status,
               d.doc_date_norm, d.case_file
          FROM documents d
         WHERE d.case_file = %s
           AND d.doc_date_norm IS NOT NULL
           AND d.doc_date_norm >= CURRENT_DATE - %s::int
           AND d.execution_status IN ('executed_filed', 'executed_notarized',
                                       'government_issued')
         ORDER BY d.doc_date_norm DESC
         LIMIT 20
    """, (CASE_FILE, days_back))
    return cur.fetchall()


def fetch_upcoming_events(cur, days_forward=14):
    """Confirmed calendar events in the next N days."""
    cur.execute("""
        SELECT id, title, start_at, location, related_case
          FROM calendar_events
         WHERE start_at >= NOW()
           AND start_at <= NOW() + (%s::int * INTERVAL '1 day')
           AND COALESCE(related_case, '') ILIKE %s
         ORDER BY start_at
         LIMIT 8
    """, (days_forward, f"%{CASE_FILE}%"))
    return cur.fetchall()


def fetch_pending_deadlines_for_admin(cur, days_forward=14):
    """Deadlines in the next N days assigned to administrator OR unassigned (caution)."""
    cur.execute("""
        SELECT id, title, due_date, assigned_to,
               (due_date - CURRENT_DATE) AS days_until
          FROM case_deadlines
         WHERE case_file = %s
           AND status = 'pending'
           AND due_date <= CURRENT_DATE + (%s::int)
         ORDER BY due_date
         LIMIT 8
    """, (CASE_FILE, days_forward))
    return cur.fetchall()


def compose_digest(stages, recent, upcoming, deadlines):
    """Build the client-facing HTML. Cites doc-IDs inline. No ops jargon."""
    today = date.today()
    lines = [
        f"📋 <b>Weekly Status — Heirs of Mary Worrick Keesey (MWK-001)</b>",
        f"<i>Week of {today.isoformat()}</i>",
        "",
    ]

    # Section 1 — Current stage of active matters
    lines.append("<b>Where the case stands</b>")
    if stages:
        for s in stages[:8]:
            stage = (s.get("current_stage") or "stage not yet set").replace("_", " ")
            next_e = s.get("next_event") or ""
            next_d = s.get("next_deadline")
            title = (s.get("title") or "")[:100]
            lines.append(f"  • <b>{s['matter_code']}</b> — {title}")
            lines.append(f"     <i>Stage: {stage}</i>")
            if next_e or next_d:
                next_line = "     Next: "
                if next_e: next_line += next_e
                if next_d: next_line += f" (due {next_d})"
                lines.append(next_line)
    else:
        lines.append("  No active matters listed.")
    lines.append("")

    # Section 2 — Recent activity (verified only)
    lines.append("<b>Recent activity (past 7 days, verified)</b>")
    if recent:
        for r in recent[:6]:
            fname = (r.get("smart_filename") or "(unnamed)").replace("&", "&amp;")[:60]
            clf = (r.get("classification") or "document").replace("&", "&amp;")[:40]
            lines.append(f"  • {r['doc_date_norm']} — {clf}: {fname} [doc#{r['id']}]")
    else:
        lines.append("  No new verified filings recorded in the past 7 days.")
    lines.append("")

    # Section 3 — Upcoming confirmed events
    lines.append("<b>Upcoming events (next 14 days)</b>")
    if upcoming:
        for u in upcoming[:6]:
            when = u["start_at"].strftime("%Y-%m-%d %H:%M %Z")
            loc = u.get("location") or "TBC"
            lines.append(f"  • {when} — {u['title']} ({loc})")
    else:
        lines.append("  No confirmed events scheduled in the next 14 days.")
    lines.append("")

    # Section 4 — Pending deadlines (especially admin-owned)
    lines.append("<b>Pending action items (next 14 days)</b>")
    if deadlines:
        for d in deadlines[:6]:
            owner = d.get("assigned_to") or "(owner not set)"
            days = d["days_until"]
            lines.append(f"  • Due {d['due_date']} (T+{days}d): {d['title'][:90]}")
            lines.append(f"     <i>Owner: {owner}</i>")
    else:
        lines.append("  No deadlines fall within the next 14 days.")
    lines.append("")

    # Section 5 — What Leo is watching for next
    lines.append("<b>What Leo is watching for</b>")
    lines.append("  • Replies from agencies and counterparty counsel")
    lines.append("  • New filings on file with the courts")
    lines.append("  • Follow-up actions on the items above as deadlines approach")
    lines.append("")
    lines.append("<i>Reply with any update or question. "
                  "Leo will route it to the right place.</i>")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Compose and print the digest but don't send")
    ap.add_argument("--audience", default="both",
                    choices=("ops", "client", "both"))
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    stages = fetch_case_stages(cur)
    recent = fetch_recent_activity(cur)
    upcoming = fetch_upcoming_events(cur)
    deadlines = fetch_pending_deadlines_for_admin(cur)

    digest = compose_digest(stages, recent, upcoming, deadlines)

    if args.dry_run:
        print(digest)
        print()
        print(f"━━━ length: {len(digest)} chars ━━━")
        return 0

    # Strict audit: kind='memo' is in STRICT_AUDIT_KINDS so comms_send enforces it.
    ok, results = comms_send(digest, audience=args.audience, kind="memo",
                              case_file=CASE_FILE)
    if ok:
        for r in results:
            tag = "✓" if r.get("ok") else "✗"
            print(f"  {tag} {r.get('name','?')} ({r.get('chat_id','?')}): "
                  f"{r.get('tg_description','?')[:80]}")
    else:
        first = results[0] if results else {}
        print(f"  ✗ digest BLOCKED or failed: "
              f"{first.get('reason') or first.get('tg_description', '?')[:200]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
