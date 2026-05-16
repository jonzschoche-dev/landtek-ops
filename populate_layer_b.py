#!/usr/bin/env python3
"""Populate Layer B (client_goals + landtek_duties + bottlenecks) from
existing case synthesis data.

Pulls clients.{current_goals, key_risks, open_strategic_gaps} JSON arrays
and creates structured rows. For each goal: derives associated duties.
For each risk: creates a bottleneck if the mitigation requires action.
For each open_strategic_gap: creates a missing_doc / unanswered_question
bottleneck.

Idempotent: tries to find existing rows by goal_text/description prefix
before inserting.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
import psycopg2
import psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def parse_json_array(raw):
    """Parse a string that's either a JSON array, Postgres array literal, or bullet list."""
    if not raw:
        return []
    s = raw.strip()
    # JSON array
    if s.startswith("[") and s.endswith("]"):
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(x) if not isinstance(x, str) else x for x in v]
        except Exception:
            pass
    # Postgres array literal {"a","b","c"} — synthesis stored Python lists as text
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1]
        # Split by `","` while respecting escaped quotes
        parts = []
        cur, depth, in_str, esc = "", 0, False, False
        for ch in inner:
            if esc:
                cur += ch
                esc = False
            elif ch == "\\":
                cur += ch
                esc = True
            elif ch == '"':
                in_str = not in_str
                cur += ch
            elif ch == "," and not in_str:
                parts.append(cur.strip())
                cur = ""
            else:
                cur += ch
        if cur.strip():
            parts.append(cur.strip())
        # Strip surrounding quotes
        return [p.strip('"').replace('\\"', '"') for p in parts if p.strip('"').strip()]
    # Fallback: bullet/newline
    items = []
    for line in s.split("\n"):
        line = re.sub(r"^[\s\-•*\d.)]+", "", line).strip()
        if line:
            items.append(line)
    return items


def goal_category_from_text(text):
    """Heuristic: derive category from goal text keywords."""
    t = text.lower()
    if any(k in t for k in ("file", "petition", "case", "complaint", "court", "rtc", "mtc", "appeal", "motion", "verify")):
        return "legal"
    if any(k in t for k in ("tax", "payment", "compensation", "rpt", "fee", "valuation")):
        return "financial"
    if any(k in t for k in ("audit", "compile", "organize", "review", "track", "monitor")):
        return "operational"
    return "strategic"


def severity_from_text(text):
    t = text.lower()
    if any(k in t for k in ("critical", "urgent", "emergency", "immediately", "lapse", "default")):
        return "critical"
    if any(k in t for k in ("important", "must", "required", "mandatory")):
        return "high"
    return "medium"


def upsert_goal(cur, client_id, case_file, goal_text, category, priority="medium"):
    cur.execute("""
        SELECT id FROM client_goals
         WHERE case_file = %s
           AND LEFT(goal_text, 80) = LEFT(%s, 80)
         LIMIT 1
    """, (case_file, goal_text))
    existing = cur.fetchone()
    if existing:
        return existing["id"], False
    cur.execute("""
        INSERT INTO client_goals (client_id, case_file, goal_text, goal_category, priority, status, progress_pct)
        VALUES (%s, %s, %s, %s, %s, 'active', 0)
        RETURNING id
    """, (client_id, case_file, goal_text, category, priority))
    return cur.fetchone()["id"], True


def upsert_duty(cur, client_id, case_file, goal_id, duty_text, duty_type="follow_up", assigned_to="jonathan"):
    cur.execute("""
        SELECT id FROM landtek_duties
         WHERE case_file = %s
           AND LEFT(duty_text, 80) = LEFT(%s, 80)
         LIMIT 1
    """, (case_file, duty_text))
    existing = cur.fetchone()
    if existing:
        return existing["id"], False
    cur.execute("""
        INSERT INTO landtek_duties
          (client_id, case_file, goal_id, duty_text, duty_type, assigned_to, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'pending')
        RETURNING id
    """, (client_id, case_file, goal_id, duty_text, duty_type, assigned_to))
    return cur.fetchone()["id"], True


def upsert_bottleneck(cur, client_id, case_file, blocker_type, description, severity, owner, blocked_goal_ids=None):
    cur.execute("""
        SELECT id FROM bottlenecks
         WHERE case_file = %s
           AND blocker_type = %s
           AND LEFT(description, 100) = LEFT(%s, 100)
           AND status = 'open'
         LIMIT 1
    """, (case_file, blocker_type, description))
    existing = cur.fetchone()
    if existing:
        return existing["id"], False
    cur.execute("""
        INSERT INTO bottlenecks
          (client_id, case_file, blocker_type, description, severity, owner, blocked_goal_ids, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'open')
        RETURNING id
    """, (client_id, case_file, blocker_type, description, severity, owner, blocked_goal_ids or []))
    return cur.fetchone()["id"], True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    args = ap.parse_args()

    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, case_file, name, priority_level, current_goals, key_risks,
               open_strategic_gaps, project_status, next_milestone
          FROM clients WHERE case_file = %s LIMIT 1
    """, (args.case,))
    client = cur.fetchone()
    if not client:
        sys.exit(f"FATAL: no client for case_file={args.case}")
    print(f"  client: {client['name']} (priority {client['priority_level']})")

    # ── Goals ────────────────────────────────────────────────────────────
    goals_raw = parse_json_array(client["current_goals"])
    case_priority = client.get("priority_level") or "medium"
    goal_ids = []
    new_goals = 0
    for g in goals_raw:
        category = goal_category_from_text(g)
        gid, created = upsert_goal(cur, client["id"], args.case, g, category, case_priority)
        goal_ids.append(gid)
        if created: new_goals += 1
    print(f"  goals: {len(goal_ids)} total ({new_goals} new)")

    # ── Duties from goals (each goal → 1-2 derived duties for Jonathan/Leo) ──
    new_duties = 0
    for gid, gtext in zip(goal_ids, goals_raw):
        # Derive a duty text from the goal
        if "file" in gtext.lower() or "petition" in gtext.lower():
            duty_text = f"Coordinate filing — {gtext[:200]}"
            dtype = "file"
        elif "compile" in gtext.lower() or "audit" in gtext.lower():
            duty_text = f"Compile and review — {gtext[:200]}"
            dtype = "draft"
        elif "obtain" in gtext.lower() or "retrieve" in gtext.lower():
            duty_text = f"Retrieve documents — {gtext[:200]}"
            dtype = "research"
        else:
            duty_text = f"Track progress on — {gtext[:200]}"
            dtype = "follow_up"
        _, created = upsert_duty(cur, client["id"], args.case, gid, duty_text, dtype, "jonathan")
        if created: new_duties += 1
    print(f"  duties: {new_duties} new")

    # ── Bottlenecks from risks ──────────────────────────────────────────
    risks_raw = parse_json_array(client["key_risks"])
    new_bottlenecks_risk = 0
    for r in risks_raw:
        if isinstance(r, dict):
            risk_text = r.get("risk") or r.get("Risk") or json.dumps(r)
        else:
            risk_text = str(r)
        severity = severity_from_text(risk_text)
        _, created = upsert_bottleneck(
            cur, client["id"], args.case,
            blocker_type="risk_event",
            description=risk_text[:1000],
            severity=severity,
            owner="jonathan",
            blocked_goal_ids=goal_ids[:3],
        )
        if created: new_bottlenecks_risk += 1

    # ── Bottlenecks from gaps ───────────────────────────────────────────
    gaps_raw = parse_json_array(client["open_strategic_gaps"])
    new_bottlenecks_gap = 0
    for g in gaps_raw:
        gtext = str(g) if not isinstance(g, dict) else json.dumps(g)
        # Heuristic blocker type
        gl = gtext.lower()
        if "doc" in gl or "deed" in gl or "instrument" in gl or "certificate" in gl or "petition" in gl:
            btype = "missing_doc"
        elif "?" in gtext or "what" in gl.split()[:3] or "which" in gl or "who" in gl:
            btype = "unanswered_question"
        elif "lgu" in gl or "court" in gl or "agency" in gl:
            btype = "waiting_party"
        else:
            btype = "other"
        _, created = upsert_bottleneck(
            cur, client["id"], args.case,
            blocker_type=btype,
            description=gtext[:1000],
            severity="medium",
            owner="jonathan",
            blocked_goal_ids=goal_ids[:3],
        )
        if created: new_bottlenecks_gap += 1

    # ── Bottlenecks from open pending_questions ─────────────────────────
    cur.execute("""
        SELECT id, question FROM pending_questions
         WHERE case_file = %s AND status = 'pending'
         ORDER BY id LIMIT 30
    """, (args.case,))
    open_qs = cur.fetchall()
    new_bottlenecks_q = 0
    for q in open_qs:
        _, created = upsert_bottleneck(
            cur, client["id"], args.case,
            blocker_type="unanswered_question",
            description=f"Open Q#{q['id']}: {q['question'][:600]}",
            severity="medium",
            owner="jonathan",
            blocked_goal_ids=goal_ids[:3],
        )
        if created: new_bottlenecks_q += 1

    total_bottlenecks = new_bottlenecks_risk + new_bottlenecks_gap + new_bottlenecks_q
    print(f"  bottlenecks: {total_bottlenecks} new ({new_bottlenecks_risk} risks, {new_bottlenecks_gap} gaps, {new_bottlenecks_q} questions)")

    # Summary
    cur.execute("SELECT count(*) AS n FROM client_goals WHERE case_file = %s", (args.case,))
    g_total = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM landtek_duties WHERE case_file = %s", (args.case,))
    d_total = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n, status FROM bottlenecks WHERE case_file = %s GROUP BY status", (args.case,))
    b_rows = cur.fetchall()
    print(f"\n  After populate — {args.case}:")
    print(f"    client_goals:   {g_total}")
    print(f"    landtek_duties: {d_total}")
    b_summary = ", ".join(f"{r['status']}={r['n']}" for r in b_rows)
    print(f"    bottlenecks:    {sum(r['n'] for r in b_rows)} total ({b_summary})")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
