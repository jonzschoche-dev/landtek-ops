#!/usr/bin/env python3
"""paracale_intake_research — self-research the 7 Inocalla matters.

Per [[feedback_leo_must_self_research]]: search corpus first, propose answer,
escalate only if truly unknown.

For each pending_context PAR-* matter:
  1. Gather all matter-tagged documents + sample extracted_text
  2. Find all chat_notes mentioning the matter
  3. Send to Haiku with tool-call: emit_matter_intake
     - Output: stage · venue · opposing_party · last_action · next_move ·
       confidence · blockers
  4. Queue ONE atomic intake_item per matter for Jonathan's confirm/correct

Honors:
  - [[feedback_atomic_inquiry_with_followups]] — one matter per inquiry
  - [[feedback_telegram_inquiry_queue]] — coalesce same-matter
  - [[feedback_no_ops_leak_to_client_ever]] — audience=ops (Jonathan only)
  - [[feedback_facts_in_chat_are_first_class]] — propose, don't assert
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/root/landtek")
with open("/root/landtek/.env") as f:
    for line in f:
        if line.startswith("ANTHROPIC_API_KEY="):
            os.environ.setdefault("ANTHROPIC_API_KEY", line.strip().split("=", 1)[1])

import psycopg2
import psycopg2.extras
import anthropic
from llm_billing import anthropic_tool_call

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

PARACALE_MATTERS = [
    "PAR-CV13-131220", "PAR-CASE-88750", "PAR-CAPACUAN",
    "PAR-VITO-CRUZ", "PAR-GOLDEN-SAND", "PAR-TCT1616", "PAR-COMPLAINT-ACE",
]

INTAKE_SYSTEM = """You are a senior Philippine property-law associate triaging a stalled matter.

You are given:
- The matter row from the firm's DB
- Sample extracted_text from documents tagged to this matter
- Chat notes mentioning this matter

Your job: propose the current case state. The supervising attorney has been carrying these matters in his head and the firm needs to encode his knowledge into structured data. Do NOT invent facts; only propose what the corpus supports. Where uncertain, say so.

Output fields to fill (via the emit_matter_intake tool):
- matter_summary: one-paragraph plain-language description of what this matter is
- opposing_party: who the firm is up against (or "unknown" if not derivable)
- venue: the court/agency/tribunal (or "unknown")
- current_stage_proposed: concise stage tag, e.g. "post_motion_pending_response", "decision_received_pending_appeal", "pre-filing_evidence_collection"
- last_action_observed: most recent dated fact from documents
- next_move_proposed: concrete next action the firm should drive (verb-first), with date if knowable
- confidence: 0.0-1.0 — how confident the proposal is from corpus alone
- open_questions: 1-3 specific questions a supervising attorney would need to answer to finalize this matter

CRITICAL: be specific. "Pending counsel input" is not a stage. "Awaiting RTC Br 23 ruling on Sep 2025 motion" is."""

INTAKE_SCHEMA = {
    "type": "object",
    "properties": {
        "matter_summary":          {"type": "string", "maxLength": 500},
        "opposing_party":          {"type": "string", "maxLength": 200},
        "venue":                   {"type": "string", "maxLength": 200},
        "current_stage_proposed":  {"type": "string", "maxLength": 100},
        "last_action_observed":    {"type": "string", "maxLength": 300},
        "next_move_proposed":      {"type": "string", "maxLength": 400},
        "confidence":              {"type": "number", "minimum": 0, "maximum": 1},
        "open_questions": {
            "type": "array",
            "items": {"type": "string", "maxLength": 200},
            "maxItems": 4,
        },
    },
    "required": ["matter_summary","opposing_party","venue",
                 "current_stage_proposed","last_action_observed",
                 "next_move_proposed","confidence","open_questions"],
}


def gather_matter_context(cur, matter_code):
    """Build the Haiku input payload."""
    cur.execute("SELECT * FROM matters WHERE matter_code=%s", (matter_code,))
    matter = cur.fetchone()
    if not matter:
        return None

    cur.execute("""
        SELECT id, doc_date_norm, classification, execution_status,
               COALESCE(smart_filename, document_title, original_filename) AS name,
               LEFT(COALESCE(extracted_text,''), 1200) AS excerpt
          FROM documents
         WHERE matter_code = %s
         ORDER BY doc_date_norm DESC NULLS LAST LIMIT 12
    """, (matter_code,))
    docs = cur.fetchall()

    # Chat notes mentioning the matter by code or by partial title
    title_kw = matter["title"].split("—")[0].strip().split()[0] if matter["title"] else ""
    cur.execute("""
        SELECT id, created_at::date AS d, sender_name, LEFT(content, 400) AS content
          FROM chat_notes
         WHERE created_at > NOW() - INTERVAL '180 days'
           AND (content ILIKE %s OR content ILIKE %s)
         ORDER BY created_at DESC LIMIT 6
    """, (f"%{matter_code}%", f"%{title_kw}%" if title_kw else "%____never____%"))
    notes = cur.fetchall()

    return {"matter": dict(matter), "docs": [dict(d) for d in docs], "notes": [dict(n) for n in notes]}


def build_user_msg(ctx):
    m = ctx["matter"]
    parts = [
        f"MATTER: {m['matter_code']}",
        f"Title: {m['title']}",
        f"Description: {m.get('description') or '(none)'}",
        f"Court_or_agency: {m.get('court_or_agency') or '(unknown)'}",
        f"Docket: {m.get('docket_number') or '(unknown)'}",
        f"Lead_counsel: {m.get('lead_counsel') or '(unset)'}",
        f"Current_stage: {m.get('current_stage') or '(unset)'}",
        f"Stage_notes: {(m.get('stage_notes') or '')[:300]}",
        "",
        f"━━ {len(ctx['docs'])} TAGGED DOCUMENTS ━━",
    ]
    for d in ctx["docs"]:
        parts.append(f"  [doc#{d['id']}] {d.get('doc_date_norm') or '(undated)'} · "
                     f"{d.get('classification') or 'Other'} · {d.get('execution_status') or 'unknown'} · "
                     f"{(d.get('name') or '(unnamed)')[:60]}")
        if d.get("excerpt"):
            excerpt = " ".join(d["excerpt"].split())[:500]
            parts.append(f"    excerpt: {excerpt}")
        parts.append("")
    parts.append(f"━━ {len(ctx['notes'])} RELATED CHAT NOTES ━━")
    for n in ctx["notes"]:
        parts.append(f"  [{n['d']}] {n.get('sender_name')}: {(n.get('content') or '')[:300]}")
    return "\n".join(parts)


def queue_intake_inquiry(cur, matter_code, ctx, result):
    """Enqueue one atomic intake_item for this matter.
    Per [[feedback_log_event_before_inferring]]: max 400 chars, ONE question, NO inference dump.
    Full Haiku proposal stored in DB notes; user requests details only if desired."""
    m = ctx["matter"]
    # Stash the full research result in notes for /detail retrieval (NOT in the Telegram body)
    detail_blob = json.dumps({
        "matter_summary":       result.get("matter_summary",""),
        "opposing_party":       result.get("opposing_party",""),
        "venue":                result.get("venue",""),
        "current_stage_proposed": result.get("current_stage_proposed",""),
        "last_action_observed": result.get("last_action_observed",""),
        "next_move_proposed":   result.get("next_move_proposed",""),
        "confidence":           result.get("confidence",0),
        "open_questions":       result.get("open_questions",[]),
    })[:5000]
    # Compose the SHORT intake body: 1 heading line + 1 question + reply options. ~280 chars.
    short_title = (m['title'] or matter_code)[:60]
    body = (
        f"📋 <b>{matter_code}</b> — {short_title}\n"
        f"Stage guess: <b>{(result.get('current_stage_proposed') or 'unknown')[:50]}</b> "
        f"(conf {result.get('confidence',0):.0%}).\n"
        f"<b>Confirm in 1-2 lines</b>: client · opposing party · current stage. "
        f"Or <code>/skip</code>."
    )
    body = body[:1100]  # safety upper bound
    # source_id is integer (matter pk), not matter_code; use matters.id
    cur.execute("SELECT id FROM matters WHERE matter_code=%s", (matter_code,))
    matter_id_row = cur.fetchone()
    matter_pk = matter_id_row["id"] if matter_id_row else None
    cur.execute("""
        INSERT INTO tg_inquiry_queue
          (kind, audience, priority, source_table, source_id, matter_code,
           composed_html, notes)
        VALUES ('intake_item', 'ops', 15, 'paracale_intake_research', %s, %s,
                %s, %s)
        RETURNING id
    """, (matter_pk, matter_code, body[:6000],
          f"paracale_intake_research:matter={matter_code}:confidence={result.get('confidence',0):.2f}"))
    row = cur.fetchone()
    # RealDictCursor returns a dict; fallback for tuple
    return row["id"] if isinstance(row, dict) else row[0]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Compose proposals + print, but don't enqueue inquiries")
    ap.add_argument("--matters", nargs="+", default=PARACALE_MATTERS)
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"paracale_intake_research — {len(args.matters)} matter(s) [{mode}]")
    print()

    queued = []
    for mc in args.matters:
        ctx = gather_matter_context(cur, mc)
        if not ctx:
            print(f"  ✗ {mc}: matter not found")
            continue

        user_msg = build_user_msg(ctx)
        try:
            result = anthropic_tool_call(
                client,
                tool_name="emit_matter_intake",
                tool_description="Emit the proposed matter intake fields.",
                input_schema=INTAKE_SCHEMA,
                called_from="paracale_intake_research",
                purpose=f"intake_proposal_{mc}",
                case_file="Paracale-001",
                model="claude-haiku-4-5",
                max_tokens=1500,
                system=INTAKE_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
        except Exception as e:
            print(f"  ✗ {mc}: Haiku failed — {e}")
            continue

        print(f"  ✓ {mc} (confidence {result.get('confidence',0):.0%})")
        print(f"    summary: {(result.get('matter_summary','')[:120])}")
        print(f"    stage:   {result.get('current_stage_proposed','?')}")
        print(f"    next:    {result.get('next_move_proposed','?')[:120]}")
        print(f"    opp:     {result.get('opposing_party','?')[:80]}")
        if result.get('open_questions'):
            print(f"    open qs: {len(result['open_questions'])}")
        print()

        if not args.dry_run:
            inquiry_id = queue_intake_inquiry(cur, mc, ctx, result)
            queued.append((mc, inquiry_id))

    if queued:
        print(f"━━━ Queued {len(queued)} intake inquiries ━━━")
        for mc, iid in queued:
            print(f"  tg_inquiry_queue.id={iid}  matter={mc}")
        print()
        print("Dispatcher will fire them sequentially (one-at-a-time rule). Reply /confirm /correct /skip per matter.")


if __name__ == "__main__":
    main()
