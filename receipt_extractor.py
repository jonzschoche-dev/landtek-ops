#!/usr/bin/env python3
"""receipt_extractor — Haiku tool-call to parse a Receipt-classified document
into structured fields (vendor, total, date, category) and propose insertion
into legal_cost_actuals.

By default in CONFIRM mode: extracts → fires one concise intake_item asking
operator to /confirm or /correct. Only on explicit --auto does it write
directly.

Per [[feedback_log_event_before_inferring]] (concision cap 400 chars) +
[[feedback_no_premature_reports]] (no auto-writes that look authoritative
without human confirm).

Usage:
  receipt_extractor.py --doc 960                  # extract + propose
  receipt_extractor.py --doc 960 --matter PAR-X   # extract + propose w/ matter override
  receipt_extractor.py --doc 960 --auto           # auto-write (use sparingly)
  receipt_extractor.py --scan-new                 # process all Receipt docs without legal_cost_actuals row
"""
import argparse
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


EXTRACT_SYSTEM = """You parse Philippine business receipts. Given OCR text from one receipt, extract structured fields.

Each receipt typically shows:
  - Vendor name and address
  - Date and time
  - Line items + amounts
  - Subtotal / VAT / service charge / TOTAL

Output via the emit_receipt tool. CRITICAL rules:
  - Amount goes in `total_php` (in pesos, not centavos). If you can only read line items, sum them; if ambiguous between subtotal/total, choose total.
  - Date: prefer the printed transaction date. If only a time + day is shown without year, use the current year. If unparseable, leave null.
  - Vendor: the business name as printed (DO NOT normalize / DO NOT invent).
  - Category: pick ONE — meal/coffee · transport · filing_fee · counsel_retainer · expert · office_supplies · misc. When in doubt: misc.
  - Confidence: 0.0-1.0 — how confident you are in the AMOUNT. If OCR garbled the total, drop confidence below 0.6 and explain in notes.

DO NOT:
  - Output fields not on the receipt
  - Average or estimate when uncertain — say "unknown" via null + low confidence
  - Treat a Philippine ID, ticket, or unrelated document as a receipt — if it's not a receipt, set is_receipt=false and stop."""


RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_receipt":   {"type": "boolean"},
        "vendor":       {"type": "string", "maxLength": 200},
        "total_php":    {"type": ["number", "null"], "minimum": 0},
        "date":         {"type": ["string", "null"], "description": "YYYY-MM-DD if parseable"},
        "category":     {"type": "string",
                         "enum": ["meal", "coffee", "transport", "filing_fee",
                                  "counsel_retainer", "expert", "office_supplies", "misc"]},
        "confidence":   {"type": "number", "minimum": 0, "maximum": 1},
        "notes":        {"type": "string", "maxLength": 250},
    },
    "required": ["is_receipt", "category", "confidence"],
}


def extract_receipt(client, doc_id, extracted_text):
    """Call Haiku tool-call to parse a receipt."""
    user_msg = (
        f"OCR'd receipt text (doc#{doc_id}):\n\n"
        f"```\n{extracted_text[:3000]}\n```\n\n"
        f"Extract structured fields. Today's date is 2026-05-20."
    )
    try:
        result = anthropic_tool_call(
            client,
            tool_name="emit_receipt",
            tool_description="Emit structured receipt fields.",
            input_schema=RECEIPT_SCHEMA,
            called_from="receipt_extractor",
            purpose=f"extract_doc_{doc_id}",
            case_file="MWK-001",
            model="claude-haiku-4-5",
            max_tokens=600,
            system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        return result
    except Exception as e:
        return {"is_receipt": False, "notes": f"extractor exception: {e}"[:250]}


def write_cost_from_receipt(matter_code: str, doc_id: int, result: dict):
    """Insert into legal_cost_actuals. Caller must pass a real matter_code —
    refuse to write if matter_code is falsy (no silent fallback to a guessed
    matter, per 2026-05-20 DOC 960 incident)."""
    if not matter_code:
        raise ValueError("write_cost_from_receipt: matter_code is required")
    map_category = {
        "meal": "misc", "coffee": "misc", "transport": "travel",
        "filing_fee": "filing_fee", "counsel_retainer": "counsel_retainer",
        "expert": "expert", "office_supplies": "admin", "misc": "misc",
    }
    cat = map_category.get(result.get("category", "misc"), "misc")
    with psycopg2.connect(DSN) as conn:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO legal_cost_actuals
              (matter_code, category, amount_php, incurred_date, description,
               source, source_doc_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (matter_code, cat, result.get("total_php") or 0,
              result.get("date") or "2026-05-20",
              f"{result.get('vendor','(unknown vendor)')} — {result.get('notes','')[:180]}",
              f"receipt_extractor:doc#{doc_id}:confidence={result.get('confidence',0):.2f}",
              doc_id))
        return cur.fetchone()[0]


def _resolve_client_code(cur, case_file):
    """case_file → client_code via clients table, fall back to matters."""
    if not case_file:
        return None
    cur.execute("SELECT client_code FROM clients WHERE case_file = %s LIMIT 1", (case_file,))
    r = cur.fetchone()
    if r:
        return r["client_code"] if isinstance(r, dict) else r[0]
    cur.execute("SELECT DISTINCT client_code FROM matters WHERE case_file = %s LIMIT 1", (case_file,))
    r = cur.fetchone()
    if not r:
        return None
    return r["client_code"] if isinstance(r, dict) else r[0]


def propose_matter_from_context(cur, doc_id, case_file, lookback_minutes=120):
    """Look at the doc's neighbours (chat_notes + other recent uploads in the
    same case_file) and propose the matter_code this receipt most likely
    belongs to. Pure SQL — no LLM call. Returns dict with proposed_matter,
    confidence, evidence_summary, or None if nothing to lean on.

    Per Jonathan 2026-05-20: 'If there is a receipt involved it should be
    classified with follow up question from Leo as well as any pertinent
    clues or notes from the meeting' + 'I uploaded detailed documents with
    it as well' — co-uploaded docs and recent chat notes are the clues."""
    if not case_file:
        return None
    interval = f"{int(lookback_minutes)} minutes"

    # 1. Documents uploaded in the same case_file within the lookback window,
    #    excluding self — their matter_codes are votes.
    cur.execute(f"""
        SELECT id, matter_code, classification,
               COALESCE(smart_filename, document_title, original_filename) AS name
          FROM documents
         WHERE case_file = %s
           AND id != %s
           AND matter_code IS NOT NULL
           AND created_at > NOW() - INTERVAL '{interval}'
         ORDER BY created_at DESC
         LIMIT 5
    """, (case_file, doc_id))
    nearby_docs = cur.fetchall() or []

    # 2. Recent chat_notes from the operator — content text + provenance only;
    #    look for matter mentions in the content.
    cur.execute(f"""
        SELECT id, content, created_at
          FROM chat_notes
         WHERE content IS NOT NULL
           AND created_at > NOW() - INTERVAL '{interval}'
         ORDER BY created_at DESC
         LIMIT 5
    """)
    notes = cur.fetchall() or []

    votes = {}
    evidence = []
    for d in nearby_docs:
        mc = d["matter_code"] if isinstance(d, dict) else d[1]
        votes[mc] = votes.get(mc, 0) + 1
        name = (d["name"] if isinstance(d, dict) else d[3]) or "?"
        evidence.append(f"co-uploaded doc#{d['id'] if isinstance(d, dict) else d[0]}: {name[:50]}")

    # Scan recent matter_codes in this client's universe so we can match
    # mentions inside chat_notes.content (no FTS — simple substring scan).
    cur.execute("""
        SELECT matter_code FROM matters
         WHERE case_file = %s AND status = 'active'
        ORDER BY length(matter_code) DESC
    """, (case_file,))
    client_matters = [r["matter_code"] if isinstance(r, dict) else r[0]
                      for r in (cur.fetchall() or [])]

    for n in notes:
        content = (n["content"] if isinstance(n, dict) else n[1]) or ""
        for mc in client_matters:
            if mc and mc in content:
                votes[mc] = votes.get(mc, 0) + 2  # chat-stated matters weighted higher
                evidence.append(f"chat: …{content[:60].strip()}…")
                break

    if not votes:
        return None

    top_matter, top_votes = max(votes.items(), key=lambda kv: kv[1])
    total = sum(votes.values()) or 1
    confidence = top_votes / total
    return {
        "proposed_matter": top_matter,
        "confidence": round(confidence, 2),
        "evidence_summary": " · ".join(evidence[:3])[:200],
        "evidence_count": len(nearby_docs) + len([n for n in notes if any(mc in ((n["content"] if isinstance(n, dict) else n[1]) or "") for mc in client_matters)]),
    }


def log_receipt_to_client_history(cur, doc_id, case_file, result, matter_code):
    """Insert the receipt as a canonical-bible event the moment it's extracted
    — even before a matter is assigned. Idempotent via the (source_table,
    source_id) UNIQUE constraint on client_history. Per P0 rule
    [[feedback_log_event_before_inferring]]: log first, infer later."""
    client_code = _resolve_client_code(cur, case_file)
    if not client_code:
        return None
    vendor = (result.get("vendor") or "(unknown vendor)")[:60]
    total = result.get("total_php") or 0
    date = result.get("date")
    pending_marker = "" if matter_code else " · PENDING matter assignment"
    summary = (f"Receipt: {vendor} · ₱{total:,.2f}"
               + (f" · {date}" if date else "")
               + pending_marker)
    matter_codes_arr = [matter_code] if matter_code else []
    cur.execute("""
        INSERT INTO client_history
          (client_code, case_file, matter_code, matter_codes, event_date,
           event_kind, source_table, source_id,
           what_summary, citation_ref, provenance)
        VALUES (%s, %s, %s, %s, %s,
                'receipt_submitted', 'receipt_extractor', %s,
                %s, %s, 'inferred_strong')
        ON CONFLICT (source_table, source_id) DO NOTHING
        RETURNING id
    """, (client_code, case_file, matter_code, matter_codes_arr, date,
          str(doc_id), summary[:300], f"doc#{doc_id}"))
    r = cur.fetchone()
    if not r:
        return None
    return r["id"] if isinstance(r, dict) else r[0]


def queue_confirmation_intake(matter_code, doc_id, result, proposal=None, case_file=None):
    """Queue one concise intake. Three modes:
      a) matter_code is set → /confirm logs to that matter
      b) matter_code is null but a proposal exists → /confirm logs to proposal
      c) matter_code is null and no proposal → ask cold for a matter_code

    matter_code on the queue row is NULL in modes (b) and (c); the proposed
    code is embedded in notes (JSON) so the dispatcher reply router can read
    it back without re-running propose_matter_from_context."""
    total = result.get("total_php") or 0
    vendor = result.get("vendor") or "(unknown vendor)"
    date = result.get("date") or "(no date)"
    cat = result.get("category", "misc")
    conf = result.get("confidence", 0)
    confirm_target = matter_code or (proposal["proposed_matter"] if proposal else None)

    if matter_code:
        body = (
            f"🧾 <b>Receipt — doc#{doc_id}</b>\n"
            f"<b>{vendor[:50]}</b> · ₱{total:,.2f} · {date} · {cat} (conf {conf:.0%})\n\n"
            f"Reply <code>/confirm</code> to log to <code>{matter_code}</code>, "
            f"a different matter_code, or <code>/skip</code>."
        )[:400]
        notes_obj = {"kind": "receipt_extractor", "doc_id": doc_id,
                     "case_file": case_file, "vendor": vendor[:60],
                     "total_php": total, "date": date, "category": cat,
                     "matter_code": matter_code, "proposed_matter": None,
                     "proposal_evidence": None}
    elif proposal:
        body = (
            f"🧾 <b>Receipt — doc#{doc_id}</b> (UNCLASSIFIED, proposal below)\n"
            f"<b>{vendor[:40]}</b> · ₱{total:,.2f} · {date} · {cat}\n"
            f"<b>Likely matter:</b> <code>{proposal['proposed_matter']}</code> "
            f"(conf {proposal['confidence']:.0%})\n"
            f"<i>From: {proposal['evidence_summary'][:120]}</i>\n"
            f"Reply <code>/confirm</code>, a different matter_code, or <code>/skip</code>."
        )[:400]
        notes_obj = {"kind": "receipt_extractor", "doc_id": doc_id,
                     "case_file": case_file, "vendor": vendor[:60],
                     "total_php": total, "date": date, "category": cat,
                     "matter_code": None,
                     "proposed_matter": proposal["proposed_matter"],
                     "proposal_evidence": proposal["evidence_summary"][:200]}
    else:
        body = (
            f"🧾 <b>Receipt — doc#{doc_id} (UNCLASSIFIED)</b>\n"
            f"<b>{vendor[:50]}</b> · ₱{total:,.2f} · {date} · {cat} (conf {conf:.0%})\n\n"
            f"Which matter? Reply with a matter_code (e.g. <code>MWK-CV26360</code>) "
            f"or <code>/skip</code>. Not logged until assigned."
        )[:400]
        notes_obj = {"kind": "receipt_extractor", "doc_id": doc_id,
                     "case_file": case_file, "vendor": vendor[:60],
                     "total_php": total, "date": date, "category": cat,
                     "matter_code": None, "proposed_matter": None,
                     "proposal_evidence": None}
    with psycopg2.connect(DSN) as conn:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tg_inquiry_queue
              (kind, audience, priority, source_table, source_id, matter_code,
               composed_html, notes)
            VALUES ('intake_item', 'ops', 18, 'receipt_extractor', %s, %s,
                    %s, %s)
            RETURNING id
        """, (doc_id, matter_code, body, json.dumps(notes_obj)))
        return cur.fetchone()[0]


def process_doc(client, doc_id, matter_override=None, auto=False):
    with psycopg2.connect(DSN) as conn:
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, matter_code, case_file, classification, extracted_text,
                   COALESCE(smart_filename, document_title, original_filename) AS name
              FROM documents WHERE id = %s
        """, (doc_id,))
        doc = cur.fetchone()
        if not doc:
            print(f"  ✗ doc#{doc_id} not found")
            return None
        if not doc["extracted_text"] or len(doc["extracted_text"]) < 30:
            print(f"  ✗ doc#{doc_id} has no OCR text")
            return None

        # Resolve the matter — explicit override, then doc's own field.
        # If neither: leave it NULL and let downstream propose_or_ask handle it.
        # NO silent fallback to a specific matter (e.g. PAR-CAPACUAN) — that
        # caused DOC 960 to be misfiled on 2026-05-20.
        matter = matter_override or doc["matter_code"]

        print(f"  parsing doc#{doc_id} ({(doc['name'] or '(unnamed)')[:50]})...")
        result = extract_receipt(client, doc_id, doc["extracted_text"])

        if not result.get("is_receipt"):
            print(f"    not a receipt: {result.get('notes','')[:80]}")
            return None
        print(f"    vendor={result.get('vendor','?')[:40]} total={result.get('total_php')} "
              f"date={result.get('date')} cat={result.get('category')} "
              f"conf={result.get('confidence',0):.2f}")

        # Canonical-bible event — log immediately, before any classification
        # uncertainty causes us to stall (per P0 rule log_event_before_inferring).
        ch_id = log_receipt_to_client_history(cur, doc_id, doc["case_file"], result, matter)
        if ch_id:
            print(f"    ✓ client_history #{ch_id} (canonical bible)")

        # Try a context-aware proposal when no matter is set yet.
        proposal = None
        if not matter and doc["case_file"]:
            proposal = propose_matter_from_context(cur, doc_id, doc["case_file"])
            if proposal:
                print(f"    proposal: {proposal['proposed_matter']} "
                      f"(conf {proposal['confidence']:.0%}, "
                      f"from {proposal['evidence_count']} signal(s))")

    # Auto-write only if we have a concrete matter AND high confidence.
    # A proposal is NEVER sufficient to auto-write — Jonathan must confirm.
    if auto and matter and result.get("confidence", 0) >= 0.8:
        row_id = write_cost_from_receipt(matter, doc_id, result)
        print(f"    ✓ AUTO-wrote legal_cost_actuals.id={row_id}")
        return {"action": "auto_written", "row_id": row_id}

    inq_id = queue_confirmation_intake(matter, doc_id, result,
                                        proposal=proposal,
                                        case_file=doc["case_file"])
    print(f"    ✓ queued confirmation intake #{inq_id}")
    return {"action": "intake_queued", "inquiry_id": inq_id,
            "matter": matter, "proposal": proposal}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", type=int, help="Process one doc by id")
    ap.add_argument("--matter", help="Override matter_code")
    ap.add_argument("--scan-new", action="store_true",
                    help="Find all Receipt-classified docs without a legal_cost_actuals row")
    ap.add_argument("--auto", action="store_true",
                    help="Auto-write at confidence >= 0.8 (skip operator confirm)")
    args = ap.parse_args()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if args.doc:
        process_doc(client, args.doc, matter_override=args.matter, auto=args.auto)
        return

    if args.scan_new:
        with psycopg2.connect(DSN) as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT d.id, d.matter_code, COALESCE(d.smart_filename, d.document_title) AS name
                  FROM documents d
                 WHERE d.classification = 'Receipt'
                   AND NOT EXISTS (SELECT 1 FROM legal_cost_actuals lca
                                    WHERE lca.source_doc_id = d.id)
                 ORDER BY d.id DESC LIMIT 20
            """)
            todo = cur.fetchall()
        print(f"receipt_extractor: {len(todo)} Receipt docs to process")
        for d in todo:
            process_doc(client, d["id"], auto=args.auto)


if __name__ == "__main__":
    main()
