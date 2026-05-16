#!/usr/bin/env python3
"""Educate Leo about a specific case — knowledge consolidation loop.

Usage:
  python3 educate_leo.py --case MWK-001
  python3 educate_leo.py --case Paracale-001

Steps:
  1. Ensure intelligence columns exist on clients
  2. Pull all docs for case with non-empty extracted_text
  3. Batch-feed to Gemini 2.5 Flash with structured extraction prompt
  4. Parse: entities, key_facts, parties, dates, references, relationships
  5. Upsert entities; aggregate facts
  6. Final synthesis call: 1-page brief covering goals/milestone/risks/gaps
  7. UPDATE clients with intelligence_summary + structured fields
  8. Write long-form briefing to reports/<case>_briefing_<date>.md

Conservative: doesn't modify existing client data unless --commit-clients-update flag.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
JONATHAN_TG_ID = "6513067717"


def tg_send(text, parse_mode=""):
    """Post directly to Telegram Bot API (works regardless of n8n state)."""
    import urllib.request
    import urllib.parse
    tok = None
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                tok = line.split("=", 1)[1].strip()
                break
    if not tok:
        return
    data = {"chat_id": JONATHAN_TG_ID, "text": text[:4090]}
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data=urllib.parse.urlencode(data).encode(),
            timeout=10,
        ).read()
    except Exception as e:
        print(f"    [tg_send failed: {e}]")

INTELLIGENCE_COLUMNS = {
    "client_intelligence_summary": "TEXT",
    "current_goals": "TEXT",
    "next_milestone": "TEXT",
    "key_risks": "TEXT",
    "open_strategic_gaps": "TEXT",
    "priority_level": "VARCHAR(20)",
    "project_status": "TEXT",
    "intelligence_updated_at": "TIMESTAMPTZ",
}


def ensure_intelligence_columns(cur):
    for col, typ in INTELLIGENCE_COLUMNS.items():
        cur.execute(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_name='clients' AND column_name='{col}') THEN
                    ALTER TABLE clients ADD COLUMN {col} {typ};
                END IF;
            END $$;
        """)


def load_corpus(cur, case_file):
    cur.execute("""
        SELECT id, original_filename, smart_filename, mime_type, timestamp::date AS doc_date,
               coalesce(extracted_text,'') AS body
          FROM documents
         WHERE case_file = %s
           AND extracted_text IS NOT NULL
           AND length(extracted_text) >= 200
         ORDER BY timestamp DESC, id DESC;
    """, (case_file,))
    return [dict(r) for r in cur.fetchall()]


def chunk_corpus_by_tokens(docs, max_chars=40_000):
    """Pack docs into chunks under max_chars. 40K = ~10K tokens input,
    leaves room for Gemini's output budget so JSON isn't truncated."""
    chunks = []
    cur, cur_len = [], 0
    for d in docs:
        # Cap individual doc bodies to 4K chars (was 8K — caused JSON truncation)
        body_snip = d['body'][:4_000]
        text = f"\n--- DOC {d['id']} ({d['doc_date']}) {d['original_filename'] or d['smart_filename'] or 'unnamed'} ---\n{body_snip}\n"
        if cur_len + len(text) > max_chars and cur:
            chunks.append(cur)
            cur, cur_len = [text], len(text)
        else:
            cur.append(text)
            cur_len += len(text)
    if cur:
        chunks.append(cur)
    return chunks


EXTRACTION_PROMPT_TMPL = """You are a legal-evidence analyst building a knowledge base for case {case_file}.

You'll receive a batch of source documents (PDFs/letters/titles/court filings, with --- DOC N --- markers).
Extract structured facts. Return ONE JSON object with these keys:

{{
  "per_doc": [
    {{
      "doc_id": <int>,
      "classification": "<one of: Title (TCT/OCT) | Court Filing | Tax Document | Demand Letter | Correspondence | Letter | Deed | Receipt | Contract | Email | Power of Attorney | Notice | Affidavit | Government Submission | Special Power of Attorney | Complaint | Legal Memorandum | Other>",
      "key_facts": ["<short fact 1>", "<fact 2>", ...],   # 1-5 facts each
      "entities": [
        {{"type": "<person|organization|location|property|financial_amount|date_event|reference_number|legal_provision|deed_or_instrument|case_or_docket>",
          "name": "<canonical name>",
          "role": "<optional 1-line context, e.g. 'plaintiff', 'mother title', 'counsel'>"}}
      ],
      "references_other_docs": ["<TCT-NNNN>", "<docket no>", ...],
      "smart_filename_suggestion": "<YYYY-MM-DD_purpose_v1.ext>"
    }}
  ]
}}

Be exhaustive on entities. Be specific on facts (no platitudes). Normalize references (TCT-4497 not "T 4497").
Output ONLY the JSON object, no prose before or after.

--- BATCH OF SOURCE DOCUMENTS ---
{batch_text}
--- END BATCH ---
"""

SYNTHESIS_PROMPT_TMPL = """You are a senior legal strategist. Below is a structured knowledge inventory built from {n_docs} documents in case {case_file}.

Produce a SINGLE JSON object with these fields. Be concrete, specific, and actionable. Cite doc_ids where helpful.

{{
  "intelligence_summary": "<3-5 paragraph briefing capturing: what this case is, the parties, the legal posture, the evidence on hand, the open fronts. Written for the operator (Jonathan Zschoche).>",
  "current_goals": "<bullet list of 3-5 active goals, each one specific & verifiable>",
  "next_milestone": "<single most-important upcoming event with date if known>",
  "key_risks": "<bullet list of 3-5 risks, each with brief mitigation idea>",
  "open_strategic_gaps": "<bullet list of 3-5 gaps in evidence / posture / process>",
  "clarification_questions": [
    "<question 1: something Leo NEEDS Jonathan to clarify in order to be a competent assistant on this case. Examples: 'Is Cesar de la Fuente still alive?' 'Which TCT lots are claimed in Civil Case 26-360?' 'Is Atty Botor still active as guardianship counsel?'>",
    "<question 2>",
    "<question 3>",
    "<...up to 7 questions, prioritized by impact>"
  ],
  "priority_level": "<one of: critical | high | medium | low>",
  "project_status": "<single sentence: where we are right now>"
}}

Output ONLY the JSON, no prose before or after.

--- KNOWLEDGE INVENTORY ---
{inventory_json}
--- END INVENTORY ---
"""


def call_claude(prompt, max_output=8000, timeout_s=180):
    """Call Claude Haiku 4.5 — paid tier, no free quota constraints.
    Switched from Gemini after hitting 20-request/day free limit 2026-05-16."""
    from dotenv import load_dotenv
    load_dotenv("/root/landtek/.env")
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
    import sys as _sys; _sys.path.insert(0, "/root/landtek")
    from llm_billing import anthropic_call
    resp = anthropic_call(
        client,
        called_from="educate_leo",
        purpose="knowledge_consolidation",
        case_file="MWK-001",
        model="claude-haiku-4-5",
        max_tokens=max_output,
        messages=[{
            "role": "user",
            "content": prompt + "\n\nIMPORTANT: respond with ONLY the JSON object — no prose before or after, no markdown fences."
        }],
    )
    raw = "".join(b.text for b in resp.content if hasattr(b, "text"))
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    # First try clean parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: salvage what we can — find the per_doc array and parse complete entries
        m = re.search(r'"per_doc"\s*:\s*\[', raw)
        if not m:
            raise
        salvaged = []
        # Walk forward parsing one balanced { ... } at a time
        i = m.end()
        depth = 0
        start = None
        in_str = False
        esc = False
        while i < len(raw):
            c = raw[i]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = not in_str
            elif not in_str:
                if c == "{":
                    if depth == 0:
                        start = i
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0 and start is not None:
                        snippet = raw[start:i+1]
                        try:
                            salvaged.append(json.loads(snippet))
                        except json.JSONDecodeError:
                            pass
                        start = None
            i += 1
        return {"per_doc": salvaged}


def upsert_entity(cur, etype, name, role, doc_id):
    """Upsert an entity. ON CONFLICT bumps mentions_count + last_seen_doc."""
    if not name or not etype:
        return
    name = name.strip()[:200]
    if len(name) < 2:
        return
    try:
        cur.execute("""
            INSERT INTO entities (type, canonical_name, notes, mentions_count, confidence,
                                  provenance_level, extraction_method, last_seen_doc, first_seen_doc, updated_at)
            VALUES (%s, %s, %s, 1, 0.75, 'inferred_strong', 'educate_leo_v1', %s, %s, now())
            ON CONFLICT (type, canonical_name) DO UPDATE
              SET mentions_count = entities.mentions_count + 1,
                  last_seen_doc = EXCLUDED.last_seen_doc,
                  updated_at = now(),
                  notes = COALESCE(NULLIF(entities.notes, ''), EXCLUDED.notes)
        """, (etype, name, role[:500] if role else None, doc_id, doc_id))
    except Exception as e:
        print(f"    [entity-skip] {etype}/{name[:40]}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--max-docs", type=int, default=999)
    ap.add_argument("--commit-clients-update", action="store_true",
                    help="Actually UPDATE the clients row with synthesis result (otherwise just print)")
    args = ap.parse_args()

    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(f"  [1/8] ensuring intelligence columns on clients table...")
    ensure_intelligence_columns(cur)
    print(f"  [2/8] loading corpus for {args.case}...")
    docs = load_corpus(cur, args.case)
    docs = docs[: args.max_docs]
    print(f"        loaded {len(docs)} docs (total chars: {sum(len(d['body']) for d in docs):,})")

    # ── 3. Batch ─────────────────────────────────────────────────────────
    chunks = chunk_corpus_by_tokens(docs, max_chars=40_000)
    print(f"  [3/8] {len(chunks)} batches (max ~40K chars each, ~30-60s per batch)", flush=True)

    # ── 4-5. Per-batch extraction + observation telegram to Jonathan ─────
    tg_send(f"🎓 Educating Leo about {args.case} — {len(docs)} docs in {len(chunks)} batches. I'll post observations as I learn.")
    all_per_doc = []
    for i, batch in enumerate(chunks, 1):
        print(f"  [4/8] batch {i}/{len(chunks)} ({sum(len(x) for x in batch):,} chars, {len(batch)} docs)...")
        prompt = EXTRACTION_PROMPT_TMPL.format(case_file=args.case, batch_text="".join(batch))
        try:
            t0 = time.time()
            out = call_claude(prompt, max_output=16_000)
            dt = time.time() - t0
            per_doc = out.get("per_doc", [])
            all_per_doc.extend(per_doc)
            print(f"        {len(per_doc)} doc-records in {dt:.1f}s")

            # Upsert entities + count new ones for the observation
            new_entity_count = 0
            sample_entities = []
            for rec in per_doc:
                for e in rec.get("entities", []):
                    upsert_entity(cur, e.get("type"), e.get("name"), e.get("role"), rec.get("doc_id"))
                    new_entity_count += 1
                    if len(sample_entities) < 6 and e.get("name"):
                        sample_entities.append(f"{e.get('type','?')[:8]}:{e.get('name','')[:30]}")

            # Build classification distribution for this batch
            classifications = {}
            for rec in per_doc:
                k = rec.get("classification", "?")
                classifications[k] = classifications.get(k, 0) + 1

            # Find unusual / interesting findings worth flagging
            interesting = []
            for rec in per_doc[:50]:
                facts = rec.get("key_facts", [])
                refs = rec.get("references_other_docs", [])
                if len(refs) >= 3:
                    interesting.append(f"DOC {rec.get('doc_id')}: refs {', '.join(refs[:3])}")

            obs = f"📚 Batch {i}/{len(chunks)} — {len(per_doc)} docs in {dt:.0f}s\n\n"
            obs += f"Classifications: " + ", ".join(f"{k}={v}" for k,v in sorted(classifications.items(), key=lambda x: -x[1])[:5]) + "\n"
            obs += f"Entities captured: {new_entity_count}\n"
            if sample_entities:
                obs += f"Sample: {', '.join(sample_entities[:5])}\n"
            if interesting:
                obs += f"\nCross-refs noted:\n" + "\n".join(f"  • {x}" for x in interesting[:3])
            tg_send(obs)
        except Exception as e:
            err_msg = f"⚠️ Batch {i}/{len(chunks)} failed: {type(e).__name__}: {str(e)[:200]}"
            print(f"        FAILED: {type(e).__name__}: {str(e)[:200]}")
            tg_send(err_msg)

    # ── 6. Final synthesis ───────────────────────────────────────────────
    print(f"  [6/8] synthesis pass over {len(all_per_doc)} doc-records...")
    inventory = {
        "case_file": args.case,
        "doc_count": len(all_per_doc),
        "docs": all_per_doc,
    }
    inv_json = json.dumps(inventory, default=str)[: 700_000]
    syn_prompt = SYNTHESIS_PROMPT_TMPL.format(
        n_docs=len(all_per_doc), case_file=args.case, inventory_json=inv_json
    )
    try:
        synthesis = call_claude(syn_prompt, max_output=8000)
    except Exception as e:
        print(f"        synthesis FAILED: {e}")
        synthesis = {}

    # ── 7. Save briefing ─────────────────────────────────────────────────
    out_dir = "/root/landtek/reports"
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md_path = f"{out_dir}/{args.case}_briefing_{ts}.md"
    with open(md_path, "w") as f:
        f.write(f"# {args.case} Case Briefing — {ts}\n\n")
        f.write(f"Generated by educate_leo.py over {len(all_per_doc)} documents.\n\n")
        for k in ["intelligence_summary", "current_goals", "next_milestone", "key_risks",
                  "open_strategic_gaps", "priority_level", "project_status"]:
            if synthesis.get(k):
                f.write(f"## {k.replace('_', ' ').title()}\n\n{synthesis[k]}\n\n")
        f.write("\n---\n## Per-doc extraction sample (first 30)\n\n")
        for rec in all_per_doc[:30]:
            f.write(f"### DOC {rec.get('doc_id')} — {rec.get('classification', '?')}\n")
            for fact in rec.get("key_facts", [])[:5]:
                f.write(f"- {fact}\n")
            f.write("\n")
    print(f"  [7/8] briefing written: {md_path}")

    # Send synthesis to Telegram in chunks (4090 char limit per message)
    if synthesis:
        summary_msg = f"📊 {args.case} synthesis complete ({len(all_per_doc)} docs analyzed)\n\n"
        summary_msg += f"Priority: {synthesis.get('priority_level','?').upper()}\n"
        summary_msg += f"Status: {synthesis.get('project_status','')}\n\n"
        summary_msg += f"Next milestone: {synthesis.get('next_milestone','')}\n\n"
        summary_msg += "Full briefing saved to /root/landtek/reports/"
        tg_send(summary_msg)

        # Send the intelligence_summary itself
        intel = synthesis.get("intelligence_summary", "")
        for chunk_start in range(0, len(intel), 3900):
            tg_send(f"🧠 Intelligence summary (part):\n\n{intel[chunk_start:chunk_start+3900]}")

        # Goals / risks / gaps
        for k, emoji in [("current_goals", "🎯"), ("key_risks", "⚠️"), ("open_strategic_gaps", "🔍")]:
            val = synthesis.get(k)
            if val:
                tg_send(f"{emoji} {k.replace('_', ' ').title()}:\n\n{val[:3900]}")

        # CLARIFICATION QUESTIONS — the most important new output
        questions = synthesis.get("clarification_questions") or []
        if questions:
            q_msg = f"❓ Questions Leo needs YOUR answers on (top {len(questions)}):\n\n"
            for n, q in enumerate(questions, 1):
                q_msg += f"{n}. {q}\n\n"
            tg_send(q_msg)

    # ── 8. Update clients row if --commit-clients-update ─────────────────
    if args.commit_clients_update and synthesis:
        cur.execute("""
            UPDATE clients
               SET client_intelligence_summary = %s,
                   current_goals = %s,
                   next_milestone = %s,
                   key_risks = %s,
                   open_strategic_gaps = %s,
                   priority_level = %s,
                   project_status = %s,
                   intelligence_updated_at = now()
             WHERE case_file = %s
             RETURNING id, name;
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
            print(f"  [8/8] updated clients row id={r['id']} ({r['name']})")
    else:
        print(f"  [8/8] dry run (use --commit-clients-update to write to clients row)")

    cur.close(); conn.close()
    print(f"\n  ✓ Done. Total entities upserted from this pass.")
    print(f"  ✓ Briefing: {md_path}")


if __name__ == "__main__":
    main()
