#!/usr/bin/env python3
"""mwk_priority_ranker.py — autonomous MWK estate priority queue from live DB.

Ranks what matters NOW for MWK-001 without Jonathan telling the system.
Uses the tier formula from memory/feedback_priority_is_goal_weighted_not_date.md:

    rank_score = tier_num * 1000 + time_component   (LOWER = higher priority)

Sources (all SQL, no LLM):
  - case_deadlines (pending/at_risk) — priority_tier P0-P5
  - matters (active) — stage-inferred tier + next_deadline
  - v_filing_gaps — open claims missing primary evidence
  - landtek_obligations (case_file MWK-001)
  - fraud_indicators on T-4497 chain titles
  - capture gaps (stage says outcome unknown)

Usage:
  python3 scripts/mwk_priority_ranker.py              # stdout markdown
  python3 scripts/mwk_priority_ranker.py --json
  python3 scripts/mwk_priority_ranker.py --top 10
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
CASE_FILE = "MWK-001"
CLIENT_CODE = "MWK-001"

TIER_NUM = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}

# Matter stage → strategic tier (substance over admin)
STAGE_TIER = {
    "mediation_held_pending_outcome": "P0",
    "post_pretrial_pending_trial_schedule": "P0",
    "pretrial_scheduled": "P0",
    "complaint_filed_pending_response": "P1",
    "complaint_filed_awaiting_response": "P2",
    "referred_to_csc_dilg_awaiting": "P2",
    "arta_referral_filed_awaiting_response": "P2",
    "petition_drafted_pending_filing": "P2",
    "estate_administration_active_no_immediate_deadline": "P1",
    "just_compensation_halted_pending_substitution": "P2",
    "demand_letter_pending_send": "P4",
    "observation_only": "P5",
    "pending_triage": "P5",
    "pending_context": "P5",
}

CLOSED_STAGES = {
    "resolved_no_merit", "closed", "disposed", "dismissed", "merged",
}


def tier_num(tier: str) -> int:
    return TIER_NUM.get((tier or "P3").upper(), 3)


def rank_score(tier: str, *, due: date | None = None, days_override: int | None = None) -> int:
    """Lower score = higher priority."""
    t = tier_num(tier)
    today = date.today()
    if days_override is not None:
        time_part = days_override
    elif due is not None:
        time_part = (due - today).days
    else:
        time_part = 90
    return t * 1000 + time_part


def fetch_deadlines(cur) -> list[dict]:
    cur.execute("""
        SELECT id, title, due_date, status, priority_tier, stage_key, matter_code,
               priority_consensus_state, priority_leo, priority_jonathan
          FROM case_deadlines
         WHERE case_file = %s AND status IN ('pending', 'at_risk')
    """, (CASE_FILE,))
    items = []
    for r in cur.fetchall():
        tier = r["priority_tier"] or r["priority_leo"] or "P3"
        due = r["due_date"]
        items.append({
            "rank_score": rank_score(tier, due=due),
            "tier": tier,
            "source": "deadline",
            "source_id": str(r["id"]),
            "matter_code": r.get("matter_code"),
            "title": r["title"],
            "due_date": due.isoformat() if due else None,
            "status": r["status"],
            "consensus": r.get("priority_consensus_state") or "leo_only",
            "why": f"Open deadline tier={tier} stage={r.get('stage_key') or '?'}",
            "action_owner": "jonathan",
        })
    return items


def fetch_matters(cur) -> list[dict]:
    cur.execute("""
        SELECT matter_code, title, current_stage, next_deadline, next_event,
               status, stage_updated_at
          FROM matters
         WHERE case_file = %s OR client_code = %s
    """, (CASE_FILE, CLIENT_CODE))
    items = []
    today = date.today()
    for r in cur.fetchall():
        stage = r["current_stage"] or ""
        if stage in CLOSED_STAGES or r["status"] in ("closed", "merged"):
            continue
        tier = STAGE_TIER.get(stage, "P3")
        due = r["next_deadline"]
        # Capture gaps: outcome unknown = treat as near-term P0
        days_override = None
        if "pending_outcome" in stage or "pending_capture" in (r["next_event"] or "").lower():
            tier = "P0"
            days_override = 7
        elif not r["next_event"] and r["status"] == "active":
            days_override = 120
        score = rank_score(tier, due=due, days_override=days_override)
        label = (r["next_event"] or r["title"] or stage)[:200]
        items.append({
            "rank_score": score,
            "tier": tier,
            "source": "matter",
            "source_id": r["matter_code"],
            "matter_code": r["matter_code"],
            "title": label,
            "due_date": due.isoformat() if due else None,
            "status": r["status"],
            "consensus": "leo_only",
            "why": f"Active matter stage={stage}",
            "action_owner": "leo" if "capture" in label.lower() else "jonathan",
        })
    return items


def fetch_evidence_gaps(cur) -> list[dict]:
    cur.execute("""
        SELECT c.id, c.short_label, c.claim_text, c.priority AS claim_priority,
               g.primary_count, g.strong_or_better, g.total_support
          FROM v_filing_gaps g
          JOIN claims c ON c.id = g.claim_id
         WHERE c.case_file = %s
         ORDER BY c.priority DESC, g.primary_count ASC
    """, (CASE_FILE,))
    items = []
    for r in cur.fetchall():
        # Foundational claims (void chain, SPA revocation) = P1 even without date
        tier = "P1" if r["claim_priority"] >= 5 else "P2"
        if r["short_label"] in ("Cesar_SPA_revoked_2005", "Balane_title_void_chain"):
            tier = "P0"
        items.append({
            "rank_score": rank_score(tier, days_override=14),
            "tier": tier,
            "source": "evidence_gap",
            "source_id": str(r["id"]),
            "matter_code": "MWK-CV26360",
            "title": f"Evidence gap: {r['short_label'] or r['claim_text'][:80]}",
            "due_date": None,
            "status": "open",
            "consensus": "leo_only",
            "why": (
                f"Claim has {r['primary_count']} primary exhibits "
                f"({r['strong_or_better']} strong+); pretrial needs paper"
            ),
            "action_owner": "barandon",
        })
    return items


def fetch_obligations(cur) -> list[dict]:
    cur.execute("""
        SELECT id, short_label, description, priority, status, due_by, matter_code
          FROM landtek_obligations
         WHERE case_file = %s AND status IN ('open', 'in_progress', 'blocked')
    """, (CASE_FILE,))
    items = []
    for r in cur.fetchall():
        # DB priority 5 = highest → maps to P0 tier band
        tier = {5: "P0", 4: "P1", 3: "P2", 2: "P3", 1: "P4"}.get(r["priority"], "P3")
        due = r["due_by"].date() if r["due_by"] else None
        items.append({
            "rank_score": rank_score(tier, due=due, days_override=30 if not due else None),
            "tier": tier,
            "source": "obligation",
            "source_id": str(r["id"]),
            "matter_code": r.get("matter_code"),
            "title": r["short_label"],
            "due_date": due.isoformat() if due else None,
            "status": r["status"],
            "consensus": "leo_only",
            "why": (r["description"] or "")[:160],
            "action_owner": "landtek",
        })
    return items


def fetch_fraud_exhibits(cur) -> list[dict]:
    cur.execute("""
        SELECT id, tct_number, indicator_type, severity, description
          FROM fraud_indicators
         WHERE severity IN ('critical', 'high')
           AND tct_number IN ('T-52540', 'T-4497', 'T-079-2021002126', 'T-079-2021002127')
    """)
    items = []
    for r in cur.fetchall():
        tier = "P0" if r["severity"] == "critical" else "P1"
        items.append({
            "rank_score": rank_score(tier, days_override=10),
            "tier": tier,
            "source": "fraud_indicator",
            "source_id": str(r["id"]),
            "matter_code": "MWK-CV26360",
            "title": f"Fraud exhibit: {r['indicator_type']} on {r['tct_number']}",
            "due_date": None,
            "status": "open",
            "consensus": "leo_only",
            "why": (r["description"] or "")[:160],
            "action_owner": "barandon",
        })
    return items


def build_queue(cur) -> list[dict]:
    all_items = []
    all_items.extend(fetch_deadlines(cur))
    all_items.extend(fetch_matters(cur))
    all_items.extend(fetch_evidence_gaps(cur))
    all_items.extend(fetch_obligations(cur))
    all_items.extend(fetch_fraud_exhibits(cur))

    # De-dupe near-identical matter+title pairs; keep best (lowest) rank
    seen: dict[tuple, dict] = {}
    for it in all_items:
        key = (it.get("matter_code"), it["title"][:80], it["source"])
        if key not in seen or it["rank_score"] < seen[key]["rank_score"]:
            seen[key] = it

    queue = sorted(seen.values(), key=lambda x: (x["rank_score"], x["source"]))
    for i, it in enumerate(queue, 1):
        it["rank"] = i
    return queue


def render_markdown(queue: list[dict], top: int | None = None) -> str:
    today = date.today().isoformat()
    lines = [
        f"# MWK Estate — Autonomous Priority Queue ({today})",
        "",
        "_Ranked from live DB. Formula: tier×1000 + days_until (lower = more urgent). "
        "Substance beats admin per feedback_priority_is_goal_weighted_not_date._",
        "",
    ]
    show = queue[:top] if top else queue
    if not show:
        lines.append("_(no priority candidates — check DB linkage)_")
        return "\n".join(lines)

    lines.append("| # | Tier | Score | Matter | Item | Owner | Consensus |")
    lines.append("|---|------|-------|--------|------|-------|-----------|")
    for it in show:
        mc = it.get("matter_code") or "—"
        title = (it["title"] or "")[:70].replace("|", "/")
        lines.append(
            f"| {it['rank']} | {it['tier']} | {it['rank_score']} | {mc} | {title} | "
            f"{it['action_owner']} | {it['consensus']} |"
        )
    lines.append("")
    lines.append("## Top 5 — what to do")
    for it in show[:5]:
        due = f" (due {it['due_date']})" if it.get("due_date") else ""
        lines.append(f"{it['rank']}. **[{it['tier']}]** {it['title']}{due}")
        lines.append(f"   - {it['why']}")
        lines.append(f"   - Source: `{it['source']}#{it['source_id']}` → owner: **{it['action_owner']}**")
    return "\n".join(lines)


def render_leo_const(queue: list[dict]) -> str:
    """Compact block for n8n Context Builder."""
    at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = [
        "",
        f"MWK PRIORITY QUEUE — autonomous rank from DB (refreshed {at}):",
        "LOWER rank_score = MORE urgent. Do NOT rank by date alone.",
        "",
    ]
    for it in queue[:12]:
        due = f" due={it['due_date']}" if it.get("due_date") else ""
        L.append(
            f"  #{it['rank']} score={it['rank_score']} [{it['tier']}] "
            f"{it.get('matter_code') or 'MWK-001'} — {(it['title'] or '')[:90]}{due} "
            f"(owner={it['action_owner']} src={it['source']}#{it['source_id']})"
        )
    L.append("")
    L.append("When Jonathan asks 'what should we focus on for MWK?' → answer from this queue.")
    L.append("Consensus leo_only items: infer tier but flag if human confirmation missing.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--leo-const", action="store_true", help="print Context Builder const body")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    queue = build_queue(cur)
    cur.close()
    conn.close()

    if args.json:
        out = queue[: args.top] if args.top else queue
        print(json.dumps(out, indent=2, default=str))
    elif args.leo_const:
        print(render_leo_const(queue))
    else:
        print(render_markdown(queue, top=args.top))


if __name__ == "__main__":
    main()