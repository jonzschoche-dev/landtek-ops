#!/usr/bin/env python3
"""fact_extractor — Haiku-driven extraction of encodable facts from chat_notes.

Enforces [[feedback_facts_in_chat_are_first_class]] (P0).

For each chat_note since the last run:
  1. Run a tool-call Haiku request that extracts structured facts
  2. Compare extracted facts against current DB state
  3. For unambiguous matches → propose AUTO-encoding
  4. For ambiguous → mark INQUIRY-needed
  5. Write to fact_encoding_log (audit trail)

Initial mode: DRY-RUN. Nothing writes to canonical tables.
Switch to live mode after operator review of the audit log.

Run cadence: every 5 minutes via systemd timer.
Cost: ~$0.001-0.005 per chat_note; ~$0.10/month at current volume.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
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


# ─── HAIKU EXTRACTION ────────────────────────────────────────────────────

EXTRACT_SYSTEM = """You are a fact extractor for a legal-ops AI for a Philippine property law firm.

Given a chat note (Telegram message text + summary), extract every encodable fact. Encodable = a structured datum that should live in the firm's database, not as free text.

Fact types to extract:
- COUNSEL: a lawyer named ("Atty. X", "Attorney Y", "Atty. Z of Firm Q")
- DATE: a specific date or relative date ("June 2", "next Friday", "May 22")
- DOCKET: a case number / docket reference ("Civil Case 26-360", "CTN SL-2026-...", "G.R. No. ...")
- COURT: a court / agency / forum ("RTC Daet Branch 64", "Court of Appeals", "ARTA")
- PARTY: a plaintiff / defendant / witness / co-heir named
- MATTER_STATUS: a status update on an ongoing matter ("the petition is drafted", "the case is pending writ of execution", "pretrial completed")
- DOCUMENT_REF: a document referenced ("the draft", "DOC 623", "the SPA from 1991")
- DEADLINE: a deadline or due date ("file the brief by Friday", "the answer is due in 5 days")
- MEETING: a meeting/hearing scheduled ("May 22 Naga meeting with Atty. Botor")

For each fact, return:
- fact_type
- raw_text (exact substring from the note)
- normalized_value (cleaned up; for dates, ISO YYYY-MM-DD if resolvable)
- confidence (0.0-1.0)
- proposed_action (one of: create_entity, update_entity_role, create_matter, update_matter, create_deadline, create_calendar_event, link_document, status_update, none)

CRITICAL constraints:
- Do NOT invent facts not in the text
- Do NOT extract Jonathan's commentary as fact ("Jonathan thinks..." is NOT a fact)
- If a fact is mentioned with hedging ("maybe", "I think", "possibly") → confidence ≤ 0.5
- For dates: only output ISO if the year is unambiguous; otherwise leave normalized_value as the raw phrase

Return: list of facts (may be empty)."""


FACT_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact_type": {
                        "type": "string",
                        "enum": ["counsel", "date", "docket", "court", "party",
                                 "matter_status", "document_ref", "deadline", "meeting"]
                    },
                    "raw_text": {"type": "string", "maxLength": 250},
                    "normalized_value": {"type": "string", "maxLength": 250},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "proposed_action": {
                        "type": "string",
                        "enum": ["create_entity", "update_entity_role",
                                 "create_matter", "update_matter",
                                 "create_deadline", "create_calendar_event",
                                 "link_document", "status_update", "none"]
                    },
                    "context": {"type": "string", "maxLength": 250,
                                "description": "Surrounding context (matter/case if mentioned)"}
                },
                "required": ["fact_type", "raw_text", "normalized_value",
                             "confidence", "proposed_action"]
            },
            "maxItems": 20
        }
    },
    "required": ["facts"]
}


def extract_facts(client, content: str, summary: str | None,
                  sender_name: str | None, related_case: str | None) -> list[dict]:
    """Run Haiku tool-call to extract structured facts from one chat_note."""
    user_msg = (
        f"sender_name: {sender_name or '(unknown)'}\n"
        f"related_case: {related_case or '(unknown)'}\n\n"
        f"=== CONTENT ===\n{content or ''}\n\n"
        f"=== SUMMARY ===\n{summary or ''}\n"
    )
    try:
        result = anthropic_tool_call(
            client,
            tool_name="emit_facts",
            tool_description="Emit the structured fact list extracted from the chat note.",
            input_schema=FACT_EXTRACTION_SCHEMA,
            called_from="fact_extractor",
            purpose="extract_facts_from_chat_note",
            case_file=related_case,
            model="claude-haiku-4-5",
            max_tokens=2000,
            system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        return result.get("facts", [])
    except Exception as e:
        print(f"  ✗ extract failed: {e}", file=sys.stderr)
        return []


# ─── ENCODING PROPOSAL (resolve against DB) ──────────────────────────────

def resolve_counsel(cur, raw_text, normalized):
    """Is this counsel already in entities? Use pg_trgm similarity (not substring)
    because canonical names contain middle initials/suffixes that break ILIKE.
    Threshold 0.35: a "fuzzy" but not crazy match.
    """
    # Prefer to match the canonical (canonical_id IS NULL) — not an alias row
    cur.execute("""
        SELECT id, canonical_name, role, mentions_count,
               similarity(canonical_name, %s) AS sim
          FROM entities
         WHERE canonical_id IS NULL
           AND (canonical_name ILIKE 'atty.%%' OR role ILIKE '%%counsel%%'
                OR similarity(canonical_name, %s) > 0.35)
         ORDER BY sim DESC, mentions_count DESC
         LIMIT 1
    """, (normalized, normalized))
    row = cur.fetchone()
    if not row or row["sim"] < 0.35:
        return {"action": "create_entity",
                "reason": f"counsel {normalized!r} not in entities (best sim: {(row['sim'] if row else 0):.2f})",
                "proposed_payload": {"canonical_name": normalized, "type": "person",
                                     "role": "Counsel (matter TBC)"}}
    if not row["role"]:
        return {"action": "update_entity_role", "entity_id": row["id"],
                "reason": f"matched {row['canonical_name']!r} (id={row['id']}, sim={row['sim']:.2f}) — has NULL role",
                "proposed_payload": {"role": "Counsel (matter TBC)"}}
    return {"action": "none",
            "reason": f"matched {row['canonical_name']!r} (id={row['id']}, sim={row['sim']:.2f}) — role already: {row['role'][:60]}"}


def resolve_matter_status(cur, related_case, normalized):
    """Status update — find the matter, propose stage update."""
    if not related_case:
        return {"action": "none", "reason": "matter_status with no related_case context"}
    cur.execute("""
        SELECT matter_code, current_stage FROM matters
         WHERE case_file = %s AND status = 'active' LIMIT 5
    """, (related_case,))
    rows = cur.fetchall()
    if len(rows) == 1:
        return {"action": "update_matter", "matter_code": rows[0]["matter_code"],
                "reason": f"single active matter in {related_case}; status update applies",
                "proposed_payload": {"current_stage_hint": normalized}}
    return {"action": "inquiry", "reason": f"{len(rows)} active matters in {related_case}; ambiguous which",
            "proposed_payload": {"candidates": [r["matter_code"] for r in rows], "status": normalized}}


def resolve_docket(cur, normalized):
    """Docket number — find matching matter via trigram (handles formatting variants like
    'Civil Case 26-360' vs 'Civil Case No. 26-360' vs 'CV-2026-360')."""
    cur.execute("""
        SELECT matter_code, docket_number, title,
               similarity(COALESCE(docket_number,'') || ' ' || COALESCE(title,''), %s) AS sim
          FROM matters
         WHERE status = 'active'
         ORDER BY sim DESC LIMIT 3
    """, (normalized,))
    rows = cur.fetchall()
    if rows and rows[0]["sim"] >= 0.35:
        return {"action": "none",
                "reason": f"docket {normalized!r} matches matter {rows[0]['matter_code']} (sim={rows[0]['sim']:.2f})"}
    return {"action": "create_matter",
            "reason": f"docket {normalized!r} has no matching matters row (best sim: {(rows[0]['sim'] if rows else 0):.2f})",
            "proposed_payload": {"docket_number": normalized}}


def resolve_deadline(cur, related_case, raw, normalized):
    """Deadline mentioned — check if already in case_deadlines."""
    if not related_case:
        return {"action": "none", "reason": "deadline with no related_case"}
    cur.execute("""
        SELECT id, title, due_date FROM case_deadlines
         WHERE case_file = %s AND status = 'pending'
    """, (related_case,))
    rows = cur.fetchall()
    # Crude match — if normalized appears in any pending deadline title, assume covered
    for r in rows:
        if normalized.lower() in (r["title"] or "").lower():
            return {"action": "none", "reason": f"deadline {normalized!r} appears covered by case_deadlines.id={r['id']}"}
    return {"action": "create_deadline", "reason": f"deadline {raw!r} not in case_deadlines",
            "proposed_payload": {"title": raw, "case_file": related_case, "raw_value": normalized}}


def resolve_meeting(cur, raw, normalized):
    """Meeting mentioned — check calendar_events."""
    cur.execute("""
        SELECT id, title FROM calendar_events
         WHERE start_at > NOW() - INTERVAL '7 days'
           AND (title ILIKE %s OR description ILIKE %s)
         LIMIT 3
    """, (f"%{normalized[:30]}%", f"%{normalized[:30]}%"))
    rows = cur.fetchall()
    if rows:
        return {"action": "none", "reason": f"meeting matches calendar_events.id={rows[0]['id']}"}
    return {"action": "create_calendar_event", "reason": f"meeting {raw!r} not in calendar_events",
            "proposed_payload": {"title": raw}}


RESOLVERS = {
    "counsel":       lambda cur, c, n, r: resolve_counsel(cur, c, n),
    "matter_status": lambda cur, c, n, r: resolve_matter_status(cur, r, n),
    "docket":        lambda cur, c, n, r: resolve_docket(cur, n),
    "deadline":      lambda cur, c, n, r: resolve_deadline(cur, r, c, n),
    "meeting":       lambda cur, c, n, r: resolve_meeting(cur, c, n),
    # date, court, party, document_ref: leave for inquiry (lower-confidence auto-resolve)
}


def propose_encoding(cur, fact, related_case):
    """Return proposed encoding for one extracted fact."""
    ft = fact["fact_type"]
    resolver = RESOLVERS.get(ft)
    if not resolver:
        return {"action": "inquiry", "reason": f"fact_type={ft} requires operator review"}
    return resolver(cur, fact["raw_text"], fact["normalized_value"], related_case)


# ─── MAIN LOOP ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-last-run", action="store_true",
                    help="Process chat_notes inserted since the last fact_encoding_log entry")
    ap.add_argument("--note-id", type=int, help="Process a specific chat_note (testing)")
    ap.add_argument("--days-back", type=int, default=7,
                    help="If no --since-last-run, scan past N days")
    ap.add_argument("--live", action="store_true",
                    help="Live mode — apply unambiguous encodings. Default is dry-run.")
    ap.add_argument("--max-notes", type=int, default=20)
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Pick notes to process
    if args.note_id:
        cur.execute("SELECT id, content, summary, sender_name, related_case FROM chat_notes WHERE id = %s",
                    (args.note_id,))
    elif args.since_last_run:
        cur.execute("""
            SELECT id, content, summary, sender_name, related_case
              FROM chat_notes
             WHERE id > COALESCE((SELECT MAX(chat_note_id) FROM fact_encoding_log), 0)
               AND content IS NOT NULL AND LENGTH(content) > 20
             ORDER BY id ASC LIMIT %s
        """, (args.max_notes,))
    else:
        cur.execute("""
            SELECT id, content, summary, sender_name, related_case
              FROM chat_notes
             WHERE created_at > NOW() - (%s || ' days')::interval
               AND content IS NOT NULL AND LENGTH(content) > 20
               AND NOT EXISTS (SELECT 1 FROM fact_encoding_log fel WHERE fel.chat_note_id = chat_notes.id)
             ORDER BY id ASC LIMIT %s
        """, (str(args.days_back), args.max_notes))
    notes = cur.fetchall()

    if not notes:
        print(f"fact_extractor: 0 notes to process")
        return 0

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    mode = "LIVE" if args.live else "DRY-RUN"
    print(f"fact_extractor: processing {len(notes)} chat_notes [{mode} mode]")

    total_facts = 0
    auto_applied = 0
    inquiries_queued = 0
    for n in notes:
        facts = extract_facts(client, n["content"], n["summary"],
                              n["sender_name"], n["related_case"])
        if not facts:
            # Log "no facts" so we don't re-process
            cur.execute("""
                INSERT INTO fact_encoding_log
                  (chat_note_id, fact_type, status, reason, dry_run)
                VALUES (%s, 'noop', 'skipped', 'no facts extracted', %s)
            """, (n["id"], not args.live))
            continue
        for fact in facts:
            proposal = propose_encoding(cur, fact, n["related_case"])
            action = proposal.get("action", "none")
            status = ("auto_applied" if action != "inquiry" and action != "none" and args.live
                      else "inquiry_queued" if action == "inquiry"
                      else "extracted")
            if action == "none":
                status = "skipped"

            cur.execute("""
                INSERT INTO fact_encoding_log
                  (chat_note_id, fact_type, extracted_text, proposed_encoding, status,
                   confidence, reason, dry_run)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                RETURNING id
            """, (n["id"], fact["fact_type"], fact["raw_text"],
                  json.dumps({"normalized": fact["normalized_value"],
                              "proposed_action": fact["proposed_action"],
                              "resolution": proposal}),
                  status, fact.get("confidence", 0.5),
                  proposal.get("reason", "")[:300], not args.live))
            total_facts += 1
            if status == "auto_applied":
                auto_applied += 1
            elif status == "inquiry_queued":
                inquiries_queued += 1
        print(f"  ✓ note #{n['id']}: {len(facts)} fact(s)")

    print()
    print(f"━━━ SUMMARY ({mode}) ━━━")
    print(f"  notes processed:    {len(notes)}")
    print(f"  total facts:        {total_facts}")
    print(f"  would auto-apply:   {auto_applied}")
    print(f"  inquiries queued:   {inquiries_queued}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
