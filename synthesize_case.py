#!/usr/bin/env python3
"""Case synthesis — runs over already-extracted entities/notes (no doc re-pull).

Uses the rich entities table (populated by educate_leo's per-batch extraction)
+ chat_notes + action_items to compose:
  - intelligence_summary
  - current_goals, next_milestone, key_risks, open_strategic_gaps
  - clarification_questions for Jonathan

This bypasses the 200K-token blow-up the original educate_leo synthesis hit
when it tried to feed all per-doc records back to Claude in one prompt.

Cost: ~$0.06 (Claude Haiku 4.5 on a compact inventory).
Usage: python3 synthesize_case.py --case MWK-001 --commit
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
JONATHAN_TG_ID = "6513067717"


def _token():
    for l in open("/root/landtek/.env"):
        if l.startswith("TELEGRAM_BOT_TOKEN="):
            return l.split("=", 1)[1].strip()


def tg_send(text, parse_mode=""):
    tok = _token()
    if not tok: return
    data = {"chat_id": JONATHAN_TG_ID, "text": text[:4090]}
    if parse_mode: data["parse_mode"] = parse_mode
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage",
                               data=urllib.parse.urlencode(data).encode(), timeout=10).read()
    except Exception as e:
        print(f"tg fail: {e}", file=sys.stderr)


def build_compact_inventory(cur, case_file):
    """Pull top entities + key chat_notes + action items into a compact dict."""
    inv = {"case_file": case_file}

    cur.execute("""
        SELECT case_file, name, company FROM clients WHERE case_file = %s LIMIT 1
    """, (case_file,))
    client = cur.fetchone()
    inv["client"] = dict(client) if client else None

    # Top entities by mentions, grouped by type (capped per type)
    cur.execute("""
        SELECT type, canonical_name, mentions_count, notes
          FROM entities
         WHERE provenance_level IN ('verified', 'inferred_strong')
           AND mentions_count >= 2
         ORDER BY mentions_count DESC LIMIT 200;
    """)
    rows = cur.fetchall()
    by_type = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append({
            "name": r["canonical_name"],
            "mentions": r["mentions_count"],
            "note": (r["notes"] or "")[:120],
        })
    # Cap each type to top 20
    inv["entities"] = {t: v[:20] for t, v in by_type.items()}

    # Doc counts by classification (if available)
    cur.execute("""
        SELECT classification, count(*) AS n
          FROM documents WHERE case_file = %s
         GROUP BY classification ORDER BY n DESC LIMIT 15;
    """, (case_file,))
    inv["doc_classifications"] = [dict(r) for r in cur.fetchall()]

    # Recent chat_notes (especially evidence)
    cur.execute("""
        SELECT topic, importance, summary, LEFT(content, 300) AS content_excerpt
          FROM chat_notes
         WHERE related_case = %s
         ORDER BY importance DESC NULLS LAST, id DESC LIMIT 30;
    """, (case_file,))
    inv["chat_notes"] = [dict(r) for r in cur.fetchall()]

    # Open action items
    cur.execute("""
        SELECT description, due_date, priority
          FROM action_items
         WHERE case_file = %s AND status = 'Open'
         ORDER BY due_date ASC NULLS LAST LIMIT 30;
    """, (case_file,))
    inv["open_action_items"] = [
        {"description": r["description"], "due_date": str(r["due_date"]) if r["due_date"] else None, "priority": r["priority"]}
        for r in cur.fetchall()
    ]

    # Pending inquiries
    cur.execute("""
        SELECT target_client_name, question_text, asked_at::text, status
          FROM pending_inquiries
         WHERE target_client_code = %s
         ORDER BY asked_at DESC LIMIT 10;
    """, (case_file,))
    inv["recent_inquiries"] = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT count(*) AS n FROM documents WHERE case_file = %s", (case_file,))
    inv["doc_count_total"] = cur.fetchone()["n"]

    return inv


SYNTH_PROMPT = """You are a senior legal strategist building a case briefing for the operator (Jonathan Zschoche).

Below is a STRUCTURED INVENTORY of the case knowledge graph — already extracted from {n_docs} documents:
  - Top entities by mention frequency (parties, properties, dates, organizations)
  - Recent chat_notes from operator + client interactions
  - Open action items with due dates
  - Pending inquiries

Produce ONE JSON object with these fields. Be CONCRETE and SPECIFIC. Cite entity names and dates verbatim. Avoid platitudes.

{{
  "intelligence_summary": "<3-5 paragraph strategic brief. What this case is. Parties. Legal posture (cite specific case numbers, key dates, principal counsel). Evidence on hand (cite most-mentioned docs/entities). Open fronts. Strategic linkages between them.>",
  "current_goals": "<bullet list of 3-5 specific verifiable goals derived from the action items + recent activity>",
  "next_milestone": "<single most-important upcoming event with date, if any in the inventory>",
  "key_risks": "<bullet list of 3-5 risks. Each: 'Risk: X — Mitigation: Y'.>",
  "open_strategic_gaps": "<bullet list of 3-5 gaps in evidence/process. What we still don't know.>",
  "clarification_questions": [
    "<question 1: something only Jonathan can answer. Examples: 'Is Civil Case 6839 the same matter as 26-360 or a separate parallel case?' 'Is Cesar de la Fuente alive?' 'Is Atty Botor's guardianship matter related to 26-360?'>",
    "<question 2>", "<question 3>", "<question 4>", "<question 5>", "<question 6>", "<question 7>"
  ],
  "priority_level": "<one of: critical | high | medium | low>",
  "project_status": "<one sentence: current operational state>"
}}

Output ONLY the JSON. No prose. No markdown fences.

--- INVENTORY ---
{inventory_json}
--- END INVENTORY ---"""


def call_claude(prompt, max_output=8000):
    import anthropic
    api_key = None
    for l in open("/root/landtek/.env"):
        if l.startswith("ANTHROPIC_API_KEY="):
            api_key = l.split("=", 1)[1].strip()
    client = anthropic.Anthropic(api_key=api_key, timeout=120)
    import sys as _sys; _sys.path.insert(0, "/root/landtek")
    from llm_billing import anthropic_call
    # Upgraded to sonnet-4-6 (was 4-5). Sonnet allowed per cost-rule #2: high-level synthesis.
    resp = anthropic_call(
        client,
        called_from="synthesize_case",
        purpose="case_synthesis",
        case_file="MWK-001",
        model="claude-sonnet-4-6",
        max_tokens=max_output,
        messages=[{"role": "user", "content": prompt + "\n\nIMPORTANT: respond with ONLY the JSON, no prose."}],
    )
    raw = "".join(b.text for b in resp.content if hasattr(b, "text"))
    import re
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    return json.loads(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(f"  [1/5] building compact inventory for {args.case}...")
    inv = build_compact_inventory(cur, args.case)
    inv_json = json.dumps(inv, default=str, indent=1)
    print(f"        inventory size: {len(inv_json):,} chars (~{len(inv_json)//4:,} tokens)")

    print(f"  [2/5] calling Claude Sonnet 4.5 for synthesis...")
    prompt = SYNTH_PROMPT.format(n_docs=inv["doc_count_total"], inventory_json=inv_json)
    synthesis = call_claude(prompt, max_output=8000)
    print(f"  [3/5] synthesis received — {len(synthesis)} keys")

    if args.commit:
        cur.execute("""
            UPDATE clients SET
              client_intelligence_summary = %s,
              current_goals = %s,
              next_milestone = %s,
              key_risks = %s,
              open_strategic_gaps = %s,
              priority_level = %s,
              project_status = %s,
              intelligence_updated_at = now()
             WHERE case_file = %s RETURNING id, name;
        """, (
            synthesis.get("intelligence_summary"),
            synthesis.get("current_goals"),
            synthesis.get("next_milestone"),
            synthesis.get("key_risks"),
            synthesis.get("open_strategic_gaps"),
            synthesis.get("priority_level"),
            synthesis.get("project_status"),
            args.case,
        ))
        for r in cur.fetchall():
            print(f"  [4/5] clients row updated: id={r['id']} ({r['name']})")

        # Self-research each clarification_question BEFORE queuing.
        # Per feedback_leo_must_self_research: only escalate truly-unanswerable
        # questions to Jonathan. For derivable ones, derive the answer and
        # log as chat_note instead.
        from self_research import extract_search_terms, search_corpus, call_claude_research
        questions = synthesis.get("clarification_questions") or []
        derived = 0
        escalated = 0
        for q in questions:
            terms = extract_search_terms(q)
            docs = search_corpus(cur, terms, case_file=args.case) if terms else []
            if docs:
                result = call_claude_research(q, docs)
                conf = result.get("confidence", 0.0)
                ans = result.get("answer", "")
                cit = result.get("citations", [])
            else:
                conf, ans, cit = 0.0, "", []

            if conf >= 0.6 and ans:
                # Derivable — log as chat_note + DM Jonathan with the derived answer
                cur.execute("""
                    INSERT INTO chat_notes (content, summary, topic, importance, related_case, created_at)
                    VALUES (%s, %s, 'legal_strategy', 3, %s, now()) RETURNING id;
                """, (
                    f"Q: {q[:500]}\nA (corpus-derived, conf={conf:.2f}): {ans[:1000]}\nCitations: {', '.join(cit[:5])}",
                    f"Self-researched: {q[:80]}",
                    args.case,
                ))
                derived += 1
                tg_send(
                    f"🔎 <b>Self-researched</b> (conf {conf:.0%})\n\n"
                    f"<b>Q</b>: {q[:300]}\n\n"
                    f"<b>Leo's derived answer</b>: {ans[:2000]}\n\n"
                    f"Citations: {', '.join(cit[:5])}\n\n"
                    f"👉 Reply 'correct' or correct the answer.",
                    parse_mode="HTML"
                )
            else:
                # Truly unanswerable — escalate to Jonathan
                cur.execute("""
                    INSERT INTO pending_questions
                      (asked_of_telegram_id, asked_by, case_file, topic, question, context, source, priority, status)
                    VALUES (%s, 'educate_leo', %s, 'case-synthesis', %s, %s, 'synthesize_case_v2_self_researched', '3', 'pending')
                    ON CONFLICT DO NOTHING;
                """, (JONATHAN_TG_ID, args.case, q[:1000],
                      f"From {args.case} synthesis 2026-05-16. Self-research confidence {conf:.2f} — true external/subjective question."))
                escalated += 1
        print(f"  [5/5] self-researched {len(questions)} questions: {derived} derived, {escalated} escalated to Jonathan")
    else:
        print(f"  (dry run — use --commit to write to clients row)")

    # Telegram send
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tg_send(f"📊 <b>{args.case} synthesis complete</b>\n\n"
            f"Priority: {synthesis.get('priority_level','?').upper()}\n"
            f"Status: {synthesis.get('project_status','')[:200]}\n"
            f"Next milestone: {synthesis.get('next_milestone','(none)')[:200]}", parse_mode="HTML")

    summary = synthesis.get("intelligence_summary", "")
    for i in range(0, len(summary), 3800):
        tg_send(f"🧠 Intelligence summary:\n\n{summary[i:i+3800]}")

    for k, emoji in [("current_goals", "🎯"), ("key_risks", "⚠️"), ("open_strategic_gaps", "🔍")]:
        v = synthesis.get(k)
        if v:
            tg_send(f"{emoji} <b>{k.replace('_',' ').title()}</b>:\n\n{v[:3800]}", parse_mode="HTML")

    # Note: clarification_questions are now self-researched + tg-sent inside
    # the commit branch above. No final batch DM here — they surface one at
    # a time as derived or escalated.
    cur.close(); conn.close()
    print(f"\n  ✓ Done.")


if __name__ == "__main__":
    main()
