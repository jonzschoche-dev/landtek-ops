#!/usr/bin/env python3
"""predict_opposing_responses.py — Opus-driven opposing-counsel prediction.

For each planned_moves row in status='planning' or 'drafted' with zero
predictions, asks Opus: given the move + case context + claims +
opposing counsel posture, what are the 3-5 most likely opposition
responses, with likelihood + counter-strategy?

Inserts results into opposing_responses; doesn't auto-overwrite existing
predictions (those are superseded explicitly via UI/SQL when a planned
move changes substantively).

Pushes summary via push_strict (strict rails) when new predictions land.

Cron: every 6 hours (these are slow-moving; no need for tight loop).
"""
from __future__ import annotations
import json, os, re, sys, urllib.request
from datetime import datetime, timezone
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
from report_publisher import push_strict

DSN          = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OPUS_MODEL   = "claude-opus-4-5-20251101"
OPUS_URL     = "https://api.anthropic.com/v1/messages"
OPUS_VER     = "2023-06-01"
OPUS_MAX_OUT = 8000


def fetch_pending_moves(cur):
    cur.execute("""
        SELECT pm.id, pm.case_file, pm.move_kind, pm.short_label,
               pm.description, pm.intended_filing_date, pm.related_claims
          FROM planned_moves pm
          LEFT JOIN opposing_responses opr ON opr.planned_move_id = pm.id
                                            AND opr.superseded_by IS NULL
         WHERE pm.status IN ('planning', 'drafted')
         GROUP BY pm.id
        HAVING COUNT(opr.id) = 0
    """)
    return cur.fetchall()


def fetch_case_context(cur, case_file: str, related_claim_ids: list[int] | None) -> str:
    parts = []
    parts.append(f"=== CASE CONTEXT: {case_file} ===\n")
    # Claims
    cur.execute("""
        SELECT id, short_label, claim_text, claim_kind, status, priority
          FROM claims WHERE case_file = %s
         ORDER BY priority DESC, id
    """, (case_file,))
    parts.append("\n## Claims at issue:\n")
    for r in cur.fetchall():
        marker = "★" if related_claim_ids and r["id"] in related_claim_ids else "·"
        parts.append(f"  {marker} [{r['id']}] {r['short_label']} ({r['status']}, p{r['priority']}): {r['claim_text'][:240]}")
    # Transferees / defendants
    cur.execute("""
        SELECT canonical_name, accion_status, current_possession
          FROM transferees WHERE case_file = %s
         ORDER BY CASE accion_status WHEN 'lead_defendant' THEN 1 ELSE 2 END, canonical_name
    """, (case_file,))
    rows = cur.fetchall()
    if rows:
        parts.append(f"\n## Defendants ({len(rows)} transferees):\n")
        for r in rows[:8]:
            parts.append(f"  - {r['canonical_name']} ({r['accion_status']})")
        if len(rows) > 8:
            parts.append(f"  … and {len(rows)-8} more")
    # Evidence-trail state
    cur.execute("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE et.weight='primary') AS primary_links
          FROM claims c
          LEFT JOIN evidence_trail et ON et.claim_id = c.id
         WHERE c.case_file = %s AND c.status = 'open'
    """, (case_file,))
    r = cur.fetchone()
    parts.append(f"\n## Evidence trail: {r['primary_links']} primary exhibits linked across {r['total']} open claims")
    # Title chain summary
    cur.execute("""SELECT COUNT(*) FROM title_chain WHERE case_file = %s AND provenance_level='verified'""", (case_file,))
    n = cur.fetchone()["count"]
    parts.append(f"## Verified title-chain edges: {n}")
    return "\n".join(parts)


def call_opus(system_text: str, user_text: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    body = json.dumps({
        "model": OPUS_MODEL,
        "max_tokens": OPUS_MAX_OUT,
        "system": system_text,
        "messages": [{"role": "user", "content": user_text}],
    }).encode()
    req = urllib.request.Request(OPUS_URL, data=body,
        headers={"x-api-key": api_key, "anthropic-version": OPUS_VER,
                 "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read())
    txt = "\n".join(c["text"] for c in payload.get("content", []) if c.get("type") == "text")
    txt = re.sub(r"^```(?:json)?\s*", "", txt.strip())
    txt = re.sub(r"\s*```$", "", txt)
    return txt


def build_prompt(move, case_ctx: str) -> str:
    return f"""You are predicting how Philippine opposing counsel will respond
to a planned LandTek move in property litigation. Be specific, conservative,
and source your reasoning in Philippine civil procedure + the case context.

== PLANNED MOVE ==
  case:         {move['case_file']}
  kind:         {move['move_kind']}
  label:        {move['short_label']}
  intended:     {move['intended_filing_date']}
  description:  {move['description']}

== CASE CONTEXT ==
{case_ctx}

== TASK ==
Identify the 3-5 most likely opposition responses to this move. For each:
  - response_kind: one of motion_to_dismiss | answer | counterclaim | demurrer |
    reply | silence | settlement_offer | procedural_objection | recusal_motion |
    third_party_complaint | other
  - likelihood: 0.0 to 1.0 (your honest probability estimate)
  - rationale: 2-3 sentences citing the specific procedural basis or case-fact
    pressure point
  - counter_strategy: 1-2 sentence LandTek-side preparation
  - cited_basis: rule number, doctrine name, or precedent if applicable

Return STRICT JSON: a list of objects with those exact fields.
Be conservative — only include responses with likelihood >= 0.15.
No commentary, no code fences.
""".strip()


def parse(raw: str):
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m: return []
        try:
            items = json.loads(m.group(0))
        except Exception:
            return []
    valid = []
    for i in items:
        if not isinstance(i, dict): continue
        if i.get("response_kind") not in (
            "motion_to_dismiss","answer","counterclaim","demurrer","reply",
            "silence","settlement_offer","procedural_objection","recusal_motion",
            "third_party_complaint","other"): continue
        try: lk = float(i.get("likelihood", 0))
        except: continue
        if lk < 0.15: continue
        i["likelihood"] = lk
        valid.append(i)
    return valid


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    moves = fetch_pending_moves(cur)
    if not moves:
        print("[predict_opposing] no moves needing predictions")
        return

    inserted = 0
    pushed_for = []
    for m in moves:
        ctx = fetch_case_context(cur, m["case_file"], m.get("related_claims"))
        sys_text = ("You are a precise Philippine civil-procedure analyst. "
                    "You output ONLY valid JSON, no commentary. Predictions reflect "
                    "real opposing-counsel behavior, not idealized lawyering.")
        try:
            raw = call_opus(sys_text, build_prompt(m, ctx))
        except Exception as e:
            print(f"  Opus error for move {m['id']}: {e}")
            continue
        preds = parse(raw)
        for p in preds:
            cur.execute("""
                INSERT INTO opposing_responses (planned_move_id, response_kind, likelihood,
                  rationale, counter_strategy, cited_basis, generated_by)
                VALUES (%s, %s, %s, %s, %s, %s, 'opus_predictor')
            """, (m["id"], p["response_kind"], p["likelihood"], p.get("rationale",""),
                  p.get("counter_strategy",""), p.get("cited_basis","")))
            inserted += 1
        if preds:
            pushed_for.append((m, preds))
        print(f"  move {m['id']} ({m['short_label']}): {len(preds)} predictions inserted")

    if pushed_for:
        # Push a Telegram summary via strict rails
        headline = f"⚖️ Opus predicted opposing responses for {len(pushed_for)} planned move(s)"
        report = ["## Opposing-Counsel Response Predictions", ""]
        for m, preds in pushed_for:
            report.append(f"### {m['short_label']}  ({m['case_file']})")
            report.append(f"_kind: {m['move_kind']} · intended: {m['intended_filing_date']}_")
            report.append("")
            for p in preds:
                report.append(f"**{p['response_kind']}** (likelihood {p['likelihood']:.2f})")
                report.append(f"- Rationale: {p.get('rationale','')}")
                report.append(f"- Counter: {p.get('counter_strategy','')}")
                if p.get('cited_basis'):
                    report.append(f"- Basis: {p['cited_basis']}")
                report.append("")
        push_strict(
            headline=headline,
            body_md="\n".join(report),
            source="watchdog",
            slug=f"opposing-responses-{datetime.now(timezone.utc):%Y%m%d-%H%M}",
        )
    print(f"[predict_opposing] {inserted} total predictions")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
