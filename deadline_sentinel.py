#!/usr/bin/env python3
"""Deadline sentinel — Leo never misses a deadline (deploy_112-D).

Runs every 15 min via systemd timer. For each active case_deadlines row:
  - Compute days_until = due_date - today
  - Pick tier:
      days >= 14 : NONE (still calm)
      14 > days >= 7 : 't14'
      7  > days >= 3 : 't7'
      3  > days >= 1 : 't3'
      days == 1      : 't1'
      days == 0      : 't0'
      days <  0      : 'overdue'
  - If tier reminder hasn't been sent yet (or overdue: pulse every 4h), send to Jonathan
  - Log to deadline_alerts (audit trail)
  - For overdue: also pull bottlenecks + suggested actions

Usage:
  python3 deadline_sentinel.py            # send any due reminders
  python3 deadline_sentinel.py --dry-run  # show what would fire
"""
import argparse
import json
import os
import sys
from datetime import datetime, date, timedelta, timezone
import psycopg2
import psycopg2.extras
import requests

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN_TG_ID = "6513067717"

# Tier thresholds (in days). Order matters — lowest threshold wins.
TIER_FOR_DAYS = [
    (-9999, "overdue"),
    (0,     "t0"),
    (1,     "t1"),
    (3,     "t3"),   # 1..3
    (7,     "t7"),   # 3..7
    (14,    "t14"),  # 7..14
    # >= 14 → no tier
]

REMINDER_COL = {
    "t14": "reminder_t14_sent_at",
    "t7":  "reminder_t7_sent_at",
    "t3":  "reminder_t3_sent_at",
    "t1":  "reminder_t1_sent_at",
    "t0":  "reminder_t0_sent_at",
    "dayof": "reminder_dayof_sent_at",
}

TIER_EMOJI = {"t14": "🟢", "t7": "🟡", "t3": "🟠", "t1": "🔴", "t0": "🚨", "overdue": "🆘"}
OVERDUE_PULSE_HOURS = 4


def pick_tier(days_until):
    if days_until < 0: return "overdue"
    if days_until == 0: return "t0"
    if days_until == 1: return "t1"
    if days_until <= 3: return "t3"
    if days_until <= 7: return "t7"
    if days_until <= 14: return "t14"
    return None


def maybe_fire_consensus_ask(cur, deadline):
    """If deadline is in leo_only state and within 21 days, enqueue ONE atomic
    consensus-ask to Jonathan. Per [[feedback_priority_consensus_required]]:
    Leo's inference cannot drive action until Jonathan + client weigh in.

    Idempotent — only fires once per (deadline_id, 'consensus_ask').
    """
    if (deadline.get("priority_consensus_state") or "leo_only") != "leo_only":
        return False, "not_leo_only"
    # Already asked?
    cur.execute("""
        SELECT id FROM tg_inquiry_queue
         WHERE source_table = 'consensus_ask' AND source_id = %s
           AND status IN ('queued','active','answered')
         LIMIT 1
    """, (str(deadline["id"]),))
    if cur.fetchone():
        return False, "already_asked"
    days_until = (deadline["due_date"] - __import__("datetime").date.today()).days
    if days_until is None or days_until < 0 or days_until > 21:
        return False, "out_of_window"

    title = deadline.get("title") or "(untitled deadline)"
    leo_tier = deadline.get("priority_leo") or "P3"
    html = (
        f"🎯 <b>Consensus check — priority tier</b>\n\n"
        f"Deadline #{deadline['id']}: <i>{title[:200]}</i>\n"
        f"Case: <code>{deadline.get('case_file') or '—'}</code> · "
        f"Due: {deadline['due_date']} (T+{days_until}d)\n\n"
        f"Leo's inference: <b>{leo_tier}</b>\n\n"
        f"Reply <code>/priority {deadline['id']} P0</code> (or P1..P5) to confirm or override. "
        f"<code>/skip</code> if not applicable. Per memory: Leo cannot drive action on this "
        f"deadline until Jonathan + client signal priority."
    )
    cur.execute("""
        INSERT INTO tg_inquiry_queue
          (kind, priority, source_table, source_id, composed_html, notes)
        VALUES ('clarification', 8, 'consensus_ask', %s, %s,
                'auto-fired by deadline_sentinel — consensus state was leo_only')
        RETURNING id
    """, (str(deadline["id"]), html))
    return True, f"consensus_ask_enqueued #{cur.fetchone()[0]}"


def event_already_occurred(cur, deadline):
    """Stage-awareness guard per [[feedback_legal_status_awareness]].

    If there's at least one executed_filed / executed_notarized / government_issued doc
    for the same case dated AFTER the deadline.due_date, the event the deadline tracks
    has already happened — auto-complete the deadline, don't alert.

    Returns: (event_occurred: bool, evidence_doc_id: int|None, evidence_summary: str)
    """
    cur.execute("""
        SELECT id, smart_filename, classification, execution_status, doc_date_norm
          FROM documents
         WHERE case_file = %s
           AND doc_date_norm IS NOT NULL
           AND doc_date_norm > %s::date
           AND execution_status IN ('executed_filed', 'executed_notarized',
                                    'government_issued', 'executed_signed_only')
         ORDER BY doc_date_norm ASC
         LIMIT 1
    """, (deadline["case_file"], deadline["due_date"]))
    row = cur.fetchone()
    if row:
        summary = (f"{row['classification'] or '?'} dated {row['doc_date']} "
                   f"({(row['smart_filename'] or '')[:60]})")
        return True, row["id"], summary
    return False, None, ""


def maybe_fire_intake(cur, deadline, timing, days_until=None, token=None):
    """ATOMIC intake firing (deploy_138). Per [[feedback_atomic_inquiry_with_followups]]:
    each checklist item becomes its own tg_inquiry_queue row. The dispatcher fires
    them ONE AT A TIME, in order. After each answer, satisfaction_evaluator runs;
    if not satisfied, a follow-up row is enqueued with higher priority so it fires
    BEFORE the next planned item.

    Idempotent — once intake_response exists, won't re-queue.
    Returns (ok: bool, info: str).
    """
    if not deadline.get("stage_key"):
        return False, "no_stage_key"
    cur.execute("""
        SELECT id, title, checklist, fire_days_before, notes
          FROM stage_intake_template
         WHERE stage_key = %s AND timing = %s
    """, (deadline["stage_key"], timing))
    tpl = cur.fetchone()
    if not tpl:
        return False, "no_template"

    # Already fired?
    cur.execute("""
        SELECT id FROM stage_intake_response
         WHERE deadline_id = %s AND timing = %s LIMIT 1
    """, (deadline["id"], timing))
    if cur.fetchone():
        return False, "already_fired"

    # Pre gating
    if timing == "pre" and tpl.get("fire_days_before") is not None:
        if days_until is None or days_until > tpl["fire_days_before"] or days_until < 0:
            return False, "not_yet_or_past"

    checklist = tpl["checklist"] if isinstance(tpl["checklist"], list) else []
    if not checklist:
        return False, "empty_checklist"

    # 1. Create the stage_intake_response parent row
    cur.execute("""
        INSERT INTO stage_intake_response
          (deadline_id, template_id, timing, items_total, status, notes, item_status)
        VALUES (%s, %s, %s, %s, 'open', %s, %s::jsonb)
        RETURNING id
    """, (deadline["id"], tpl["id"], timing, len(checklist),
          "fired atomically via deadline_sentinel (deploy_138)",
          '{}'))
    intake_resp_id = cur.fetchone()["id"]

    # 2. Enqueue ONE atomic row per checklist item
    when = deadline["due_date"].strftime("%a %b %d, %Y")
    icon = "🔔" if timing == "pre" else "📋"
    header_ctx = (f"<i>{icon} {tpl['title']}</i>\n"
                  f"<i>Case: {deadline['case_file']} · {deadline['title'][:70]}</i>\n"
                  f"<i>{'Due' if timing=='pre' else 'Was due'}: {when}</i>")

    enqueued = 0
    for i, item in enumerate(checklist):
        html = (
            f"{header_ctx}\n\n"
            f"<b>Question {i+1} of {len(checklist)}:</b>\n"
            f"{item}\n\n"
            f"<i>Reply with the specific factual answer (doc, photo, or text). "
            f"<code>/skip</code> if this item doesn't apply. "
            f"One question at a time — Leo will follow up if your answer is incomplete.</i>"
        )
        cur.execute("""
            INSERT INTO tg_inquiry_queue
              (kind, priority, source_table, source_id, matter_code,
               composed_html, intake_response_id, item_index, is_followup, notes)
            VALUES ('intake_item', %s, 'stage_intake_response', %s, %s,
                    %s, %s, %s, false, %s)
        """, (
            # Atomic intake items at priority 5 (between jump=0 and P1=10) so an
            # in-progress conversation isn't interrupted by gap_alerts at P1.
            # The +i adds ordering within the intake (Q1 fires before Q2).
            5 + i,
            str(intake_resp_id),
            None,
            html,
            intake_resp_id,
            i,
            f"atomic intake_item {i+1}/{len(checklist)} for intake#{intake_resp_id}"
        ))
        enqueued += 1
    return True, f"enqueued {enqueued} atomic items for intake#{intake_resp_id}"


def load_env_token():
    env = {}
    with open("/root/landtek/.env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, _, v = line.strip().partition("=")
                env[k.strip()] = v.strip()
    return env.get("TELEGRAM_BOT_TOKEN")


def tg_send(text, token, assigned_to=None, case_file="MWK-001"):
    """Route via comms_send. audience derived from case_deadlines.assigned_to:
        'administrator' / 'don_qi'        → both (Don Qi + Jonathan)
        'both'                            → both
        'client'                          → both (alias)
        'ops' / NULL / anything else      → ops (Jonathan only — safe default)
    """
    import sys as _sys
    _sys.path.insert(0, "/root/landtek")
    from comms import comms_send
    at = (assigned_to or "").strip().lower()
    if at in ("administrator", "don_qi", "donqi", "client", "both"):
        audience = "both"
    else:
        audience = "ops"
    ok, results = comms_send(text, audience=audience, kind="report",
                              case_file=case_file, token=token,
                              strict_audit=False)  # reminders aren't fact-heavy
    if not ok:
        first = results[0] if results else {}
        return False, str(first.get("reason") or first.get("tg_description") or "")[:200]
    fails = [r for r in results if not r.get("ok")]
    if fails:
        return True, f"partial: {len(fails)} fail"
    return True, "ok"


def compose_reminder(d, tier, days_until, bottlenecks):
    em = TIER_EMOJI.get(tier, "⏰")
    title = d["title"]
    when = d["due_date"].strftime("%Y-%m-%d")
    if tier == "overdue":
        line2 = f"⚠️ <b>OVERDUE by {abs(days_until)} day(s)</b> (was due {when})"
    elif tier == "t0":
        line2 = f"<b>DUE TODAY</b> — {when}"
    else:
        line2 = f"Due {when} — <b>T-{days_until}d</b>"

    lines = [
        f"{em} <b>Deadline alert ({tier.upper()}) — {d['case_file']}</b>",
        f"<b>{title}</b>",
        line2,
    ]
    if d.get("description"):
        lines.append(f"<i>{d['description'][:300]}</i>")
    if tier in ("overdue", "t0", "t1", "t3") and bottlenecks:
        lines.append("")
        lines.append("<b>Blocking bottlenecks:</b>")
        for b in bottlenecks[:3]:
            lines.append(f"  • {b['description'][:200]} <i>(severity={b['severity']})</i>")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-tier", choices=list(REMINDER_COL.keys()),
                    help="re-send for this tier even if already sent")
    args = ap.parse_args()

    today = date.today()
    token = load_env_token()
    if not token and not args.dry_run:
        sys.exit("FATAL: TELEGRAM_BOT_TOKEN not found")

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Backstop: any deadline marked completed without a post-intake gets one fired.
    # Catches manual completions and any code path that bypassed maybe_fire_intake(post).
    cur.execute("""
        SELECT cd.id, cd.case_file, cd.title, cd.due_date, cd.deadline_type, cd.stage_key
          FROM case_deadlines cd
          LEFT JOIN stage_intake_response r
            ON r.deadline_id = cd.id AND r.timing = 'post'
         WHERE cd.status = 'completed'
           AND cd.stage_key IS NOT NULL
           AND r.id IS NULL
           AND EXISTS (SELECT 1 FROM stage_intake_template t
                        WHERE t.stage_key = cd.stage_key AND t.timing = 'post')
    """)
    missed = cur.fetchall()
    post_backfilled = 0
    for d in missed:
        if args.dry_run:
            print(f"  ↳ DRY: would backfill post-intake for #{d['id']} ({d['stage_key']})")
            continue
        ok, info = maybe_fire_intake(cur, d, "post", token=None)
        if ok:
            post_backfilled += 1
            print(f"  📋 POST-INTAKE BACKFILLED for completed deadline #{d['id']} ({d['stage_key']}) — {info}")
    if missed and not args.dry_run:
        print(f"  backfilled {post_backfilled}/{len(missed)} missed post-intakes")

    cur.execute("""
        SELECT id, case_file, title, description, due_date, deadline_type, status,
               source_doc_id, stage_key, priority_tier, priority_leo,
               priority_jonathan, priority_client, priority_consensus_state,
               reminder_t14_sent_at, reminder_t7_sent_at, reminder_t3_sent_at,
               reminder_t1_sent_at, reminder_t0_sent_at, reminder_dayof_sent_at,
               assigned_to,
               (SELECT max(sent_at) FROM deadline_alerts a
                 WHERE a.deadline_id = case_deadlines.id AND a.tier='overdue') AS last_overdue_alert
          FROM case_deadlines
         WHERE status = 'pending'
         ORDER BY due_date ASC NULLS LAST
    """)
    deadlines = cur.fetchall()
    print(f"  scanning {len(deadlines)} active deadlines (today={today})")

    sent_count = 0
    auto_completed = 0
    intakes_fired = 0
    consensus_asks = 0
    for d in deadlines:
        days = (d["due_date"] - today).days
        tier = args.force_tier or pick_tier(days)

        # Consensus-ask gate: if deadline is leo_only, fire an atomic consensus
        # question first (per feedback_priority_consensus_required). Don't fire
        # intakes / escalations until Jonathan has weighed in on priority.
        consensus_state = d.get("priority_consensus_state") or "leo_only"
        if consensus_state == "leo_only" and not args.dry_run:
            ok_c, info_c = maybe_fire_consensus_ask(cur, d)
            if ok_c:
                consensus_asks += 1
                print(f"  🎯 CONSENSUS-ASK fired for deadline #{d['id']} (leo_only) — {info_c}")
            # Skip intake firing — wait for Jonathan to confirm priority first
            continue

        # Pre-event intake: fires once per deadline, gated by template's fire_days_before
        if d.get("stage_key") and days >= 0 and tier is not None:
            if not args.dry_run:
                ok, info = maybe_fire_intake(cur, d, "pre", days_until=days, token=token)
                if ok and info != "dry":
                    intakes_fired += 1
                    print(f"  📨 PRE-INTAKE fired for deadline #{d['id']} ({d['stage_key']}, T-{days}d)")

        if tier is None:
            continue

        # STAGE-AWARENESS GUARD (per feedback_legal_status_awareness):
        # If a court/filed doc dated after this deadline exists, the event has
        # already happened. Auto-complete and suppress alert.
        if tier == "overdue":
            occurred, evidence_id, evidence_summary = event_already_occurred(cur, d)
            if occurred:
                cur.execute("""
                    UPDATE case_deadlines
                       SET status = 'completed',
                           updated_at = NOW(),
                           notes = COALESCE(notes,'') ||
                                   ' | AUTO-COMPLETED ' || %s ||
                                   ' by sentinel (post-deadline evidence: doc#' || %s || ': ' || %s || ')'
                     WHERE id = %s
                """, (today.isoformat(), evidence_id, evidence_summary, d["id"]))
                cur.execute("""
                    INSERT INTO deadline_alerts (deadline_id, tier, channel, message_text, delivery_ok)
                    VALUES (%s, 'auto_completed', 'system',
                            'Stage-awareness: post-deadline executed_filed doc#' || %s || ' (' || %s || ') exists. Marked completed.',
                            true)
                """, (d["id"], evidence_id, evidence_summary))
                auto_completed += 1
                print(f"  ⏭ AUTO-COMPLETED deadline #{d['id']} ({d['title'][:50]}) — evidence: {evidence_summary}")
                # Fire the post-event intake checklist
                if d.get("stage_key") and not args.dry_run:
                    ok, info = maybe_fire_intake(cur, d, "post", token=token)
                    if ok:
                        intakes_fired += 1
                        print(f"  📋 POST-INTAKE fired for deadline #{d['id']} ({d['stage_key']})")
                continue

            # Pulse every OVERDUE_PULSE_HOURS hours
            last = d.get("last_overdue_alert")
            if last and (datetime.now(timezone.utc) - last) < timedelta(hours=OVERDUE_PULSE_HOURS):
                continue
        else:
            col = REMINDER_COL[tier]
            if d.get(col) and not args.force_tier:
                continue  # already sent for this tier

        # Pull bottlenecks for context
        cur.execute("""
            SELECT description, severity FROM bottlenecks
             WHERE case_file = %s AND status IN ('open','attempting')
             ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                                    WHEN 'medium' THEN 3 ELSE 4 END
             LIMIT 5
        """, (d["case_file"],))
        bn = cur.fetchall()

        text = compose_reminder(d, tier, days, bn)
        if args.dry_run:
            print(f"  → [DRY] would fire {tier.upper()} for deadline #{d['id']} ({d['title'][:60]})")
            print("    ---")
            print("    " + text.replace("\n", "\n    "))
            print("    ---")
            continue

        ok, info = tg_send(text, token,
                            assigned_to=d.get("assigned_to"),
                            case_file=d.get("case_file", "MWK-001"))
        if ok:
            sent_count += 1
            if tier != "overdue":
                cur.execute(f"UPDATE case_deadlines SET {REMINDER_COL[tier]}=now() WHERE id=%s",
                            (d["id"],))
            cur.execute("""
                INSERT INTO deadline_alerts (deadline_id, tier, channel, message_text, delivery_ok)
                VALUES (%s,%s,'telegram',%s, true)
            """, (d["id"], tier, text[:2000]))
            print(f"  ✓ fired {tier.upper()} for deadline #{d['id']}: {d['title'][:70]}")
        else:
            cur.execute("""
                INSERT INTO deadline_alerts (deadline_id, tier, channel, message_text, delivery_ok)
                VALUES (%s,%s,'telegram',%s, false)
            """, (d["id"], tier, f"FAILED: {info}"[:2000]))
            print(f"  ✗ FAILED {tier.upper()} for deadline #{d['id']}: {info}")

    # Emit heartbeat
    try:
        cur.execute("""INSERT INTO system_heartbeat (source, status, metadata)
                       VALUES ('deadline-sentinel', 'ok', %s::jsonb)""",
                    (json.dumps({"sent": sent_count, "scanned": len(deadlines)}),))
    except Exception: pass

    print(f"\n  sent {sent_count} reminder(s), auto-completed {auto_completed} stale deadline(s), "
          f"fired {intakes_fired} intake(s), {consensus_asks} consensus-ask(s)")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
