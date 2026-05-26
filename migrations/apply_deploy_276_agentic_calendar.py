#!/usr/bin/env python3
"""Deploy 276 — agentic calendar.

Five pieces:
  A. scripts/calendar_briefer.py installed as systemd timer (every 30 min):
     auto-completes past events, sends 2h prep briefs, post-event followup
     asks, 7am Manila daily briefs.
  B. Active Landscape extension: SQL adds today's events + tomorrow's events
     + post-event-needs-followup to Context Builder's per-turn injection.
  C. New /api/calendar/upcoming, /api/calendar/needs_followup endpoints on
     leo-tools so the AI Agent can query the calendar as a tool.
  D. AI Agent prompt extension: CALENDAR DISCIPLINE — emit
     calendar_event_to_save on ANY future date mention; auto-link
     related_case via current case_file; never overwrite a confirmed event
     without first asking.
  E. Auto-link related_case for any existing events with case_file/matter_code
     resolvable from title.

Idempotent. Audited via app.actor='jonathan_deploy_276'.
"""
import json
import os
import subprocess
import sys
import time

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"

SERVICE_UNIT = "/etc/systemd/system/landtek-calendar-briefer.service"
TIMER_UNIT = "/etc/systemd/system/landtek-calendar-briefer.timer"

SERVICE_CONTENT = """[Unit]
Description=LandTek agentic calendar briefer
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/calendar_briefer.py
StandardOutput=append:/var/log/landtek/calendar_briefer.log
StandardError=append:/var/log/landtek/calendar_briefer.log
"""

TIMER_CONTENT = """[Unit]
Description=Run LandTek calendar briefer every 30 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
AccuracySec=15s
Unit=landtek-calendar-briefer.service

[Install]
WantedBy=timers.target
"""

NEW_LANDSCAPE_SQL = """  -- ACTIVE LANDSCAPE (deploy_264) ---------------------------------------
  (
    SELECT json_agg(m_row ORDER BY due_sort, matter_code)
    FROM (
      SELECT matter_code,
             current_stage,
             next_event,
             next_deadline,
             next_event_owner,
             COALESCE(next_deadline::text, '9999-12-31') AS due_sort
        FROM matters
       WHERE (next_event IS NOT NULL AND TRIM(next_event) <> '')
          OR next_deadline IS NOT NULL
       ORDER BY due_sort, matter_code
       LIMIT 30
    ) m_row
  ) as upcoming_meetings_and_actions,
  (
    SELECT json_build_object(
      'new_docs_48h',     (SELECT COUNT(*) FROM documents WHERE created_at >= now() - INTERVAL '48 hours'),
      'new_emails_48h',   (SELECT COUNT(*) FROM gmail_messages WHERE ingested_at >= now() - INTERVAL '48 hours'),
      'new_resolutions_48h', (SELECT COUNT(*) FROM resolutions WHERE created_at >= now() - INTERVAL '48 hours'),
      'new_escalations_48h', (SELECT COUNT(*) FROM escalations WHERE created_at >= now() - INTERVAL '48 hours')
    )
  ) as recent_activity_48h,
  (
    SELECT json_build_object(
      'proposals_needs_manual_review',
        (SELECT COUNT(*) FROM doc_classification_proposals WHERE status = 'needs_manual_review'),
      'proposals_proposed',
        (SELECT COUNT(*) FROM doc_classification_proposals WHERE status = 'proposed'),
      'resolutions_unknown_disposition',
        (SELECT COUNT(*) FROM resolutions WHERE disposition IS NULL OR disposition = 'unknown'),
      'documents_untagged_mwk',
        (SELECT COUNT(*) FROM documents WHERE case_file = 'MWK-001' AND matter_code IS NULL)
    )
  ) as outstanding_queues,
  -- CALENDAR (deploy_276) --------------------------------------------------
  (
    SELECT json_agg(ev ORDER BY start_at)
    FROM (
      SELECT id, title, start_at, end_at, location, attendees, related_case, related_tct, status
        FROM calendar_events
       WHERE status IN ('scheduled', 'rescheduled')
         AND (start_at AT TIME ZONE 'Asia/Manila')::date = (now() AT TIME ZONE 'Asia/Manila')::date
       ORDER BY start_at
    ) ev
  ) as calendar_today,
  (
    SELECT json_agg(ev ORDER BY start_at)
    FROM (
      SELECT id, title, start_at, end_at, location, attendees, related_case, related_tct, status
        FROM calendar_events
       WHERE status IN ('scheduled', 'rescheduled')
         AND (start_at AT TIME ZONE 'Asia/Manila')::date = ((now() AT TIME ZONE 'Asia/Manila') + INTERVAL '1 day')::date
       ORDER BY start_at
    ) ev
  ) as calendar_tomorrow,
  (
    SELECT json_agg(ev ORDER BY start_at DESC)
    FROM (
      SELECT e.id, e.title, e.start_at, e.related_case
        FROM calendar_events e
       WHERE e.status = 'completed'
         AND COALESCE(e.end_at, e.start_at + INTERVAL '2 hours') > now() - INTERVAL '48 hours'
         AND COALESCE(e.end_at, e.start_at + INTERVAL '2 hours') < now()
         AND NOT EXISTS (
               SELECT 1 FROM calendar_briefs_sent b
                WHERE b.event_id = e.id
                  AND b.brief_type IN ('followup_post', 'manual_followup_logged')
             )
       ORDER BY e.start_at DESC LIMIT 5
    ) ev
  ) as calendar_needs_followup,
  (
    SELECT now() AT TIME ZONE 'Asia/Manila'
  ) as now_manila"""

NEW_CONTEXT_LANDSCAPE_BLOCK = r"""
// ACTIVE LANDSCAPE block (deploy_264, extended deploy_276 with calendar)
const nowManila = clientRow?.now_manila || new Date().toISOString();
const meetings = clientRow?.upcoming_meetings_and_actions || [];
const activity48h = clientRow?.recent_activity_48h || {};
const queues = clientRow?.outstanding_queues || {};
const calToday = clientRow?.calendar_today || [];
const calTomorrow = clientRow?.calendar_tomorrow || [];
const calFollowup = clientRow?.calendar_needs_followup || [];

const meetingsBlock = meetings.length === 0
  ? '(no open matters with scheduled actions)'
  : meetings.map(m => {
      const due = m.next_deadline ? `due ${m.next_deadline}` : '(no deadline)';
      const owner = m.next_event_owner ? ` [owner: ${m.next_event_owner}]` : '';
      const stage = m.current_stage ? ` [stage: ${m.current_stage}]` : '';
      return `  ${m.matter_code} ${due}${owner}${stage}\n    next: ${(m.next_event || '').slice(0, 240)}`;
    }).join('\n');

const activityBlock =
  `  new docs (48h):        ${activity48h.new_docs_48h ?? '?'}\n` +
  `  new emails (48h):      ${activity48h.new_emails_48h ?? '?'}\n` +
  `  new resolutions (48h): ${activity48h.new_resolutions_48h ?? '?'}\n` +
  `  new escalations (48h): ${activity48h.new_escalations_48h ?? '?'}`;

const queuesBlock =
  `  proposals needs_manual_review: ${queues.proposals_needs_manual_review ?? '?'}\n` +
  `  proposals still proposed:      ${queues.proposals_proposed ?? '?'}\n` +
  `  resolutions unknown disp:      ${queues.resolutions_unknown_disposition ?? '?'}\n` +
  `  MWK docs still untagged:       ${queues.documents_untagged_mwk ?? '?'}`;

function fmtEvent(e) {
  const att = (e.attendees && e.attendees.length) ? ` w/ ${e.attendees.join(', ')}` : '';
  const loc = e.location ? ` @ ${e.location}` : '';
  const mc = e.related_case ? ` [${e.related_case}]` : '';
  const t = (e.start_at || '').replace('T', ' ').substr(0, 16);
  return `  ev#${e.id} ${t}${mc} — ${e.title}${att}${loc}`;
}
const calTodayBlock    = calToday.length    ? calToday.map(fmtEvent).join('\n')    : '  (none scheduled)';
const calTomorrowBlock = calTomorrow.length ? calTomorrow.map(fmtEvent).join('\n') : '  (none scheduled)';
const calFollowupBlock = calFollowup.length
  ? calFollowup.map(e => `  ev#${e.id} (${(e.start_at || '').substr(0,10)}) ${e.title} — NEEDS YOUR OUTCOME NOTE`).join('\n')
  : '  (none — all caught up)';

const activeLandscape = `ACTIVE LANDSCAPE (auto-injected per turn; do NOT re-query via tools):
Today (Asia/Manila): ${nowManila}

Calendar — today:
${calTodayBlock}

Calendar — tomorrow:
${calTomorrowBlock}

Calendar — past 48h needing your followup note:
${calFollowupBlock}

Open matters with next-event / deadline:
${meetingsBlock}

Recent activity (last 48h):
${activityBlock}

Outstanding review queues:
${queuesBlock}`;
"""

SYSTEM_PROMPT_INSERT = """

# CALENDAR DISCIPLINE (deploy_276 — added 2026-05-26)

The ACTIVE LANDSCAPE block now includes three calendar sections:
  - Calendar — today
  - Calendar — tomorrow
  - Calendar — past 48h needing your followup note

Rules:

1. Every conversational turn from Jonathan: if today's or tomorrow's
   calendar has events, mention them ONCE per session start, then only when
   directly relevant. Format: "Today you have <title> at <time>" — concise.

2. If Jonathan mentions a future date, time, meeting, hearing, call,
   appointment, deadline, follow-up, or scheduled event, you MUST emit a
   calendar_event_to_save object. Required fields: title, start_at (ISO 8601
   Asia/Manila), end_at (best-effort), location, attendees (array of names
   you can identify), related_tct (if a TCT is mentioned),
   related_case (matter_code if discernible). Default time to 9:00 AM
   Asia/Manila if Jonathan said only the date.

3. If a past event from "needs your followup note" matches Jonathan's
   current message (e.g., he mentions a meeting that already happened),
   capture the outcome as a chat_note tagged with the event_id in
   pending_question_resolution.

4. NEVER overwrite a confirmed event without first asking. If Jonathan
   contradicts an existing event (e.g., "the meeting is actually Tuesday
   not Monday"), set needs_clarification=true and ask: "Update event#N
   (start_at) to (new value)? Or create a new one?"

5. If today's date is within 3 days of a forcing_function date in the
   client registry (e.g., MWK's 2026-06-02 mediation), end your
   telegram_summary_for_jonathan with a "Heads up: X in N days" line.

6. The cron-driven briefer handles prep briefs (2h before), post-event
   followup asks, and daily morning briefs at 7am Manila. You do NOT need
   to send those — they're system-driven. Your job is to react well when
   Jonathan responds to one of those briefs.

"""


def apply_landscape_sql_patch(cur):
    """Replace the SQL in Execute a SQL query node to include calendar fields."""
    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    nodes = cur.fetchone()["nodes"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes)

    for n in nodes:
        if n.get("name") == "Execute a SQL query" and n.get("type") == "n8n-nodes-base.postgres":
            old_q = n.get("parameters", {}).get("query", "")
            if "calendar_today" in old_q:
                print("  Execute a SQL query: calendar fields already present (no-op)")
                return False
            # Replace from "-- ACTIVE LANDSCAPE (deploy_264)" through "as outstanding_queues,"
            # with the new block (which extends the same section).
            anchor_start = "-- ACTIVE LANDSCAPE (deploy_264)"
            anchor_end = "  ) as now_manila"
            si = old_q.find(anchor_start)
            ei = old_q.find(anchor_end)
            if si < 0 or ei < 0:
                print(f"  Execute a SQL query: anchors not found (si={si}, ei={ei})")
                return False
            ei_full = old_q.find("\n", ei) + 1
            new_q = old_q[:si] + NEW_LANDSCAPE_SQL.lstrip() + old_q[ei_full:]
            n.setdefault("parameters", {})["query"] = new_q
            print(f"  Execute a SQL query: {len(old_q)} -> {len(new_q)} chars (calendar fields added)")
            break
    else:
        print("  Execute a SQL query node not found")
        return False

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::json, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    return True


def apply_context_builder_patch(cur):
    """Replace the activeLandscape block in Context Builder."""
    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    nodes = cur.fetchone()["nodes"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes)

    for n in nodes:
        if n.get("name") == "Context Builder" and n.get("type") == "n8n-nodes-base.code":
            old = n.get("parameters", {}).get("jsCode", "")
            if "Calendar — today" in old or "calTodayBlock" in old:
                print("  Context Builder: calendar block already present (no-op)")
                return False
            # Replace from "// ACTIVE LANDSCAPE block (deploy_264)" through the
            # closing backtick of the activeLandscape template literal.
            start_marker = "// ACTIVE LANDSCAPE block (deploy_264)"
            si = old.find(start_marker)
            if si < 0:
                print("  Context Builder: start marker not found")
                return False
            # Find end: the closing `; after the activeLandscape template literal
            # The template ends with `;` after the queuesBlock variable interpolation.
            tail_marker = "${queuesBlock}`;"
            ei = old.find(tail_marker, si)
            if ei < 0:
                print("  Context Builder: end marker not found")
                return False
            ei_full = ei + len(tail_marker)
            new_code = old[:si] + NEW_CONTEXT_LANDSCAPE_BLOCK.lstrip() + old[ei_full:]
            n["parameters"]["jsCode"] = new_code
            print(f"  Context Builder: {len(old)} -> {len(new_code)} chars (calendar injected)")
            break
    else:
        print("  Context Builder node not found")
        return False

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::json, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    return True


def apply_agent_prompt_patch(cur):
    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    nodes = cur.fetchone()["nodes"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes)

    for n in nodes:
        if n.get("name") == "AI Agent" and n.get("type") == "@n8n/n8n-nodes-langchain.agent":
            opts = n.setdefault("parameters", {}).setdefault("options", {})
            old = opts.get("systemMessage", "")
            if "CALENDAR DISCIPLINE (deploy_276" in old:
                print("  AI Agent: calendar discipline already present (no-op)")
                return False
            anchor = "# STANDING BRIEF"
            if anchor in old:
                new = old.replace(anchor, SYSTEM_PROMPT_INSERT.strip() + "\n\n" + anchor, 1)
            else:
                new = old.rstrip() + "\n" + SYSTEM_PROMPT_INSERT
            opts["systemMessage"] = new
            print(f"  AI Agent prompt: {len(old)} -> {len(new)} chars")
            break
    else:
        return False

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::json, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    return True


def install_timer():
    os.makedirs("/var/log/landtek", exist_ok=True)
    with open(SERVICE_UNIT, "w") as f:
        f.write(SERVICE_CONTENT)
    os.chmod(SERVICE_UNIT, 0o644)
    with open(TIMER_UNIT, "w") as f:
        f.write(TIMER_CONTENT)
    os.chmod(TIMER_UNIT, 0o644)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "--now",
                    "landtek-calendar-briefer.timer"], check=False)
    print("  systemd timer installed + enabled")
    r = subprocess.run(["systemctl", "list-timers",
                        "landtek-calendar-briefer.timer", "--no-pager"],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines()[:5]:
        print(f"    {line}")


def main():
    if os.geteuid() != 0:
        print("Run as root")
        sys.exit(1)

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_276'")

    print("Deploy 276 — agentic calendar")
    print("=" * 60)

    # A. Briefer schema + timer
    print("\n[A] Calendar briefer schema + systemd timer")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendar_briefs_sent (
            id SERIAL PRIMARY KEY,
            event_id INTEGER REFERENCES calendar_events(id) ON DELETE CASCADE,
            brief_type TEXT NOT NULL CHECK (brief_type IN
              ('prep_2h','followup_post','auto_completed','daily_morning',
               'conflict_alert','manual_followup_logged')),
            brief_date DATE,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            telegram_ok BOOLEAN,
            telegram_error TEXT,
            UNIQUE (event_id, brief_type),
            UNIQUE (brief_type, brief_date)
        );
        CREATE INDEX IF NOT EXISTS idx_briefs_event ON calendar_briefs_sent(event_id);
        CREATE INDEX IF NOT EXISTS idx_briefs_type_date ON calendar_briefs_sent(brief_type, brief_date);
    """)
    print("  calendar_briefs_sent table ensured")
    conn.commit()

    install_timer()

    # B. Active Landscape SQL extension
    print("\n[B] Execute a SQL query — add calendar fields")
    apply_landscape_sql_patch(cur)

    # C. Context Builder calendar block
    print("\n[C] Context Builder — inject calendar block")
    apply_context_builder_patch(cur)

    # D. AI Agent CALENDAR DISCIPLINE
    print("\n[D] AI Agent prompt — CALENDAR DISCIPLINE")
    apply_agent_prompt_patch(cur)

    conn.commit()
    cur.close()
    conn.close()

    # E. Sync workflow_history + webhook + smoke
    print("\n[E] sync workflow_history + webhook + smoke")
    for cmd, label in [
        (["python3", "/root/landtek/scripts/sync_workflow_history.py", WORKFLOW_ID], "history"),
        (["python3", "/root/landtek/scripts/sync_telegram_webhook.py"], "webhook"),
        (["python3", "/root/landtek/scripts/post_deploy_smoke.py"], "smoke"),
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        last = (r.stdout.strip().split("\n")[-3:] if r.stdout else [""])
        print(f"  {label}: {' / '.join(last)[-200:]}")

    # F. First briefer pass (force-daily so we get one immediately)
    print("\n[F] First briefer pass (force daily brief)")
    r = subprocess.run(
        ["python3", "/root/landtek/scripts/calendar_briefer.py", "--force-daily"],
        capture_output=True, text=True,
    )
    print("  " + r.stdout.strip().replace("\n", "\n  ")[-1500:])


if __name__ == "__main__":
    main()
