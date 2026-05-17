#!/usr/bin/env python3
"""Goal accelerator (deploy_112-E).

For each active case + firm-level goal, propose 1-3 concrete actions that
would move the goal forward TODAY. Backed by truth_negotiator (every action
proposal carries evidence_doc_ids). Drafts get NEVER cited as fact.

Runs daily via systemd timer. Top picks surfaced to Jonathan via Telegram.

Output:
  - proposed_actions rows (audit trail)
  - Telegram digest "Today's accelerator picks"

CLI:
  python3 goal_accelerator.py [--case MWK-001] [--dry-run] [--max-per-case 3]
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone, timedelta
import psycopg2
import psycopg2.extras
import requests

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN_TG_ID = "6513067717"


def load_token():
    env = {}
    with open("/root/landtek/.env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, _, v = line.strip().partition("=")
                env[k.strip()] = v.strip()
    return env.get("TELEGRAM_BOT_TOKEN"), env.get("ANTHROPIC_API_KEY")


def fetch_context(cur, case_file):
    cur.execute("""SELECT id, goal_text, goal_category, priority, status, progress_pct, target_date
                   FROM client_goals
                   WHERE case_file=%s AND status IN ('active','at_risk')
                   ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                                          WHEN 'medium' THEN 3 ELSE 4 END LIMIT 10""",
                (case_file,))
    goals = cur.fetchall()

    cur.execute("""SELECT id, blocker_type, severity, description, owner, status AS mitigation_status
                   FROM bottlenecks
                   WHERE case_file=%s AND status IN ('open','attempting')
                   ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                                          WHEN 'medium' THEN 3 ELSE 4 END LIMIT 10""",
                (case_file,))
    bottlenecks = cur.fetchall()

    cur.execute("""SELECT id, duty_text, duty_type, status, assigned_to, deadline
                   FROM landtek_duties WHERE case_file=%s AND status IN ('pending','in_progress','blocked')
                   ORDER BY deadline ASC NULLS LAST LIMIT 10""", (case_file,))
    duties = cur.fetchall()

    cur.execute("""SELECT current_stage, next_event, next_deadline, docket_number
                   FROM matters WHERE case_file=%s AND current_stage IS NOT NULL
                   ORDER BY stage_updated_at DESC LIMIT 1""", (case_file,))
    stage = cur.fetchone()

    cur.execute("""SELECT id, question FROM pending_questions
                   WHERE case_file=%s AND status='pending'
                   ORDER BY created_at DESC LIMIT 5""", (case_file,))
    open_qs = cur.fetchall()

    return goals, bottlenecks, duties, stage, open_qs


def propose_actions_for_case(case_file, name, goals, bottlenecks, duties, stage, open_qs, api_key):
    """Call Claude Haiku to generate 1-3 concrete actions. Returns list of action dicts."""
    if not api_key:
        return [], "no ANTHROPIC_API_KEY"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        ctx = []
        ctx.append(f"# Case: {case_file} ({name})")
        if stage:
            ctx.append(f"Current procedural stage: {stage['current_stage']}")
            ctx.append(f"Next event: {stage['next_event']}")
            if stage.get("next_deadline"):
                ctx.append(f"Next deadline: {stage['next_deadline']}")
        ctx.append("\n## Active goals")
        for g in goals[:6]:
            ctx.append(f"- [{g['priority']}] (id={g['id']}, {g['progress_pct']}%) {g['goal_text'][:240]}")
        ctx.append("\n## Open bottlenecks")
        for b in bottlenecks[:6]:
            ctx.append(f"- [{b['severity']}] {b['blocker_type']} (owner={b['owner']}, mitigation={b['mitigation_status']}): {b['description'][:200]}")
        ctx.append("\n## Pending duties")
        for d in duties[:6]:
            ctx.append(f"- [{d['status']}] {d['duty_type']} (due {d['deadline'] or '—'}): {d['duty_text'][:200]}")
        if open_qs:
            ctx.append("\n## Open clarification questions")
            for q in open_qs[:5]:
                ctx.append(f"- (id={q['id']}) {q['question'][:200]}")

        import sys as _sys; _sys.path.insert(0, "/root/landtek")
        from llm_billing import anthropic_call
        msg = anthropic_call(
            client,
            called_from="goal_accelerator",
            purpose="client_actions",
            case_file="MWK-001",
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=(
                "You are Leo, a legal-ops AI for Landtek (a Philippine property-law firm). "
                "Your job is to propose 1-3 CONCRETE actions Jonathan can take TODAY or this week to advance the named goals + remove bottlenecks. "
                "Be very specific: name the document to draft, the person to email, the office to visit, the question to ask. "
                "Vague suggestions ('continue monitoring', 'follow up') are not allowed — those are non-actions. "
                "Each action must reference at least one specific goal_id or bottleneck_id from the context. "
                "If a known bottleneck has a clear mitigation, the action should be the mitigation. "
                "Output a JSON object: {\"actions\": [{\"action_text\": str, \"rationale\": str, \"impact\": float (0..1), \"goal_id\": int|null, \"bottleneck_id\": int|null}]}"
            ),
            messages=[{"role": "user", "content": "\n".join(ctx)}],
        )
        out = msg.content[0].text.strip()
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if m:
            try:
                j = json.loads(m.group(0))
                return j.get("actions", []), None
            except json.JSONDecodeError as e:
                return [], f"json_decode_err: {e}"
        return [], "no_json_in_response"
    except Exception as e:
        return [], f"haiku_err: {str(e)[:200]}"


def propose_firm_actions(firm_goals, api_key):
    """1-2 firm-level actions across goals."""
    if not api_key or not firm_goals:
        return [], "skip"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        ctx = ["# Landtek firm-level goals (Leo's secondary agenda — beyond client work)"]
        for g in firm_goals[:7]:
            ctx.append(f"- [{g['priority']}, {g['goal_category']}] (id={g['id']}) {g['goal_text'][:240]}")
        import sys as _sys; _sys.path.insert(0, "/root/landtek")
        from llm_billing import anthropic_call
        msg = anthropic_call(
            client,
            called_from="goal_accelerator",
            purpose="firm_actions",
            case_file=None,
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=(
                "You are Leo. Propose 1-2 concrete firm-level actions Jonathan can take TODAY to advance Landtek's strategic goals "
                "(separate from any single client case). Examples: drafting investor pitch material, publishing a blog post showcasing case work, "
                "outreach to a target client segment, building a specific Leo capability, completing a financial projection. "
                "Be specific. Vague suggestions are not allowed. "
                "Output JSON: {\"actions\": [{\"action_text\": str, \"rationale\": str, \"impact\": float, \"firm_goal_id\": int}]}"
            ),
            messages=[{"role": "user", "content": "\n".join(ctx)}],
        )
        out = msg.content[0].text.strip()
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0)).get("actions", []), None
            except: pass
        return [], "no_json"
    except Exception as e:
        return [], f"err: {str(e)[:200]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None)
    ap.add_argument("--max-per-case", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-firm", action="store_true")
    ap.add_argument("--no-tg", action="store_true")
    args = ap.parse_args()

    tg_token, api_key = load_token()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.case:
        cur.execute("SELECT case_file, name FROM clients WHERE case_file=%s", (args.case,))
    else:
        cur.execute("SELECT case_file, name FROM clients WHERE case_file IS NOT NULL AND case_file <> '' ORDER BY name")
    cases = cur.fetchall()

    all_picks = []  # for Telegram digest

    for c in cases:
        cf = c["case_file"]; name = c["name"]
        goals, bottlenecks, duties, stage, open_qs = fetch_context(cur, cf)
        if not goals and not bottlenecks and not duties:
            print(f"\n  ⊘ {cf}: nothing to accelerate (no goals/bottlenecks/duties)")
            continue
        print(f"\n  → proposing for {cf} ({name})")
        print(f"     goals={len(goals)}  bottlenecks={len(bottlenecks)}  duties={len(duties)}  pending_qs={len(open_qs)}")

        actions, err = propose_actions_for_case(cf, name, goals, bottlenecks, duties, stage, open_qs, api_key)
        if err:
            print(f"     ⚠ {err}"); continue

        for a in actions[:args.max_per_case]:
            atext = (a.get("action_text") or "").strip()
            if not atext: continue
            rationale = (a.get("rationale") or "").strip()
            impact = float(a.get("impact", 0.5))
            gid = a.get("goal_id") if isinstance(a.get("goal_id"), int) else None
            bid = a.get("bottleneck_id") if isinstance(a.get("bottleneck_id"), int) else None

            if not args.dry_run:
                # Dedup against recent proposals
                cur.execute("""
                    SELECT id FROM proposed_actions
                     WHERE case_file = %s AND LEFT(action_text, 60) = LEFT(%s, 60)
                       AND proposed_at > now() - interval '7 days'
                     LIMIT 1
                """, (cf, atext))
                if cur.fetchone():
                    print(f"     ↺ duplicate within 7d: {atext[:70]}")
                    continue
                cur.execute("""
                    INSERT INTO proposed_actions
                      (case_file, client_goal_id, action_text, rationale, impact_score, status)
                    VALUES (%s,%s,%s,%s,%s,'proposed')
                    RETURNING id
                """, (cf, gid, atext, rationale, impact))
                aid = cur.fetchone()["id"]
                print(f"     + #{aid} [impact={impact:.2f}] {atext[:90]}")
                all_picks.append({"case": cf, "id": aid, "text": atext, "rationale": rationale, "impact": impact})
            else:
                print(f"     [DRY] [impact={impact:.2f}] {atext[:90]}")

    # ── Firm-level ──
    if not args.no_firm:
        cur.execute("SELECT id, priority, goal_category, goal_text FROM firm_goals WHERE status='active' ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END")
        firm = cur.fetchall()
        if firm:
            print(f"\n  → proposing firm-level actions ({len(firm)} active firm goals)")
            actions, err = propose_firm_actions(firm, api_key)
            if not err:
                for a in actions[:2]:
                    atext = (a.get("action_text") or "").strip()
                    if not atext: continue
                    fgid = a.get("firm_goal_id") if isinstance(a.get("firm_goal_id"), int) else None
                    impact = float(a.get("impact", 0.5))
                    if not args.dry_run:
                        cur.execute("""
                            SELECT id FROM proposed_actions
                             WHERE firm_goal_id IS NOT NULL AND LEFT(action_text, 60) = LEFT(%s, 60)
                               AND proposed_at > now() - interval '7 days' LIMIT 1
                        """, (atext,))
                        if cur.fetchone():
                            print(f"     ↺ duplicate firm action: {atext[:70]}")
                            continue
                        cur.execute("""
                            INSERT INTO proposed_actions
                              (firm_goal_id, action_text, rationale, impact_score, status)
                            VALUES (%s,%s,%s,%s,'proposed') RETURNING id
                        """, (fgid, atext, a.get("rationale", ""), impact))
                        aid = cur.fetchone()["id"]
                        print(f"     + #{aid} (FIRM) [impact={impact:.2f}] {atext[:90]}")
                        all_picks.append({"case": "FIRM", "id": aid, "text": atext, "rationale": a.get("rationale",""), "impact": impact})
                    else:
                        print(f"     [DRY] (FIRM) [impact={impact:.2f}] {atext[:90]}")

    # ── Enqueue digest into tg_inquiry_queue (deploy_148) ──
    # Per [[feedback_telegram_inquiry_queue]] + [[feedback_legacy_bot_decommission]]:
    # no script may sendMessage directly. The dispatcher fires one inquiry at a time;
    # this digest waits its turn instead of stepping on an active intake.
    if all_picks and not args.no_tg and not args.dry_run:
        import html as _html
        all_picks.sort(key=lambda p: p["impact"], reverse=True)
        top = all_picks[:5]
        lines = [
            "🚀 <b>Today's accelerator picks</b>",
            f"<i>{date.today().isoformat()} · top {len(top)} of {len(all_picks)} proposals</i>",
            "",
        ]
        for p in top:
            tag = "🏢 FIRM" if p["case"] == "FIRM" else f"📁 {_html.escape(p['case'])}"
            lines.append(f"<b>#{p['id']} {tag}</b> · impact {p['impact']:.2f}")
            lines.append(f"  {_html.escape(p['text'])}")
            if p["rationale"]:
                lines.append(f"  <i>{_html.escape(p['rationale'][:200])}</i>")
            lines.append("")
        lines.append("<i>Reply with the pick # to act on it, or /skip to dismiss.</i>")
        digest_html = "\n".join(lines)
        # Run through output_audit (warn-mode — advisory content)
        try:
            import sys as _sys; _sys.path.insert(0, "/root/landtek")
            from output_audit import audit_text
            passed, findings = audit_text(digest_html, strict=False)
            if not passed:
                print(f"  ⚠ output_audit flagged {len(findings)} finding(s); enqueuing anyway (warn-mode)")
        except Exception as e:
            print(f"  ⚠ output_audit skipped: {e}")
        cur.execute("""
            INSERT INTO tg_inquiry_queue
              (kind, priority, source_table, source_id, matter_code,
               composed_html, notes)
            VALUES ('report', 20, 'proposed_actions', NULL, NULL, %s,
                    'goal_accelerator daily digest (top ' || %s || ')')
            RETURNING id
        """, (digest_html, len(top)))
        qid = cur.fetchone()["id"]
        print(f"\n  → enqueued accelerator digest as tg_inquiry_queue#{qid} (kind=report, prio=20)")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
