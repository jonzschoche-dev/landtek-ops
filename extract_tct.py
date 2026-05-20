#!/usr/bin/env python3
"""extract_tct — document-type-specific TCT/OCT extractor (Mac Claude's fix #1).

Per Jonathan + Mac Claude analysis 2026-05-20: the generic regex extractor
treats T-YYYY tax years, T-NN-NN PINs, ARP numbers, and OCR garbage as
"titles." This extractor uses a document-type GATE first — refuses to
extract title facts from non-title documents — then applies a TCT-aware
prompt to actual TCT/OCT documents.

System prompt: /root/landtek/prompts/tct_extractor.md
Output: structured rows in extraction_chunks (chunk_type='tct_extracted')
        + optional update to titles table if all required fields present
Confidence: per [[feedback_first_principles_before_proposal]] only
        auto-applies at >= 0.80; otherwise queues a confirmation intake.

Usage:
  extract_tct.py --doc 666                 # one doc
  extract_tct.py --doc 666 --auto          # auto-apply at >= 0.80 confidence
  extract_tct.py --scan-classified         # all docs classified Title that haven't been re-extracted
  extract_tct.py --dry-run                 # never writes; just prints
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
PROMPT_PATH = Path("/root/landtek/prompts/tct_extractor.md")

CONFIDENCE_FLOOR = 0.80


# ─── EXTRACTION SCHEMA ────────────────────────────────────────────────────

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_title_document":  {"type": "boolean"},
        "actual_type":        {"type": "string",
                               "enum": ["TCT","OCT","TAX_DECLARATION","DEED",
                                        "SUBDIVISION_PLAN","OTHER"]},
        "rejection_reason":   {"type": ["string","null"], "maxLength": 250},

        "title_number":       {"type": ["string","null"], "maxLength": 50},
        "title_kind":         {"type": ["string","null"],
                               "enum": ["TCT","OCT","DUPLICATE","RECONSTITUTED",None]},
        "registered_owners":  {"type": "array", "items": {"type": "string"},
                               "maxItems": 20},
        "issued_date":        {"type": ["string","null"]},
        "previous_title_ref": {"type": ["string","null"], "maxLength": 80,
                               "description": "Explicit 'previously TCT-X' or 'in lieu of [prior]' citation only"},
        "cancelled_by_ref":   {"type": ["string","null"], "maxLength": 80,
                               "description": "If this title was cancelled, the title that cancelled it"},
        "lot_number":         {"type": ["string","null"], "maxLength": 50},
        "block_number":       {"type": ["string","null"], "maxLength": 30},
        "survey_plan_ref":    {"type": ["string","null"], "maxLength": 80,
                               "description": "PSD-XXXX / PSU-XXXX / PSD-E-XXXX format"},
        "area_sqm":           {"type": ["number","null"]},
        "location":           {"type": ["string","null"], "maxLength": 250},

        "encumbrances": {
            "type": "array",
            "maxItems": 30,
            "items": {
                "type": "object",
                "properties": {
                    "entry_number":     {"type": ["string","null"], "maxLength": 30},
                    "instrument_type":  {"type": ["string","null"], "maxLength": 80},
                    "instrument_date":  {"type": ["string","null"]},
                    "executor_name":    {"type": ["string","null"], "maxLength": 150},
                    "notary":           {"type": ["string","null"], "maxLength": 150},
                    "recording_date":   {"type": ["string","null"]},
                    "quoted_text":      {"type": ["string","null"], "maxLength": 400},
                },
            },
        },

        "confidence":         {"type": "number", "minimum": 0, "maximum": 1},
        "ocr_quality_flag":   {"type": "string",
                               "enum": ["high","medium","low"]},
        "notes":              {"type": "string", "maxLength": 500},
    },
    "required": ["is_title_document","actual_type","confidence","ocr_quality_flag"],
}


# ─── EXTRACTION ───────────────────────────────────────────────────────────

def extract_one_tct(client, doc_id: int, extracted_text: str, model="claude-haiku-4-5"):
    """Run the document-type-aware TCT extractor on one document."""
    system = PROMPT_PATH.read_text()
    user_msg = (
        f"Document #{doc_id} OCR text:\n\n"
        f"```\n{extracted_text[:12000]}\n```\n\n"
        f"Apply the document-type gate first, then extract per schema if it's a TCT/OCT."
    )
    try:
        result = anthropic_tool_call(
            client,
            tool_name="emit_tct_facts",
            tool_description="Emit the structured TCT/OCT extraction (or rejection if non-title).",
            input_schema=EXTRACT_SCHEMA,
            called_from="extract_tct",
            purpose=f"extract_doc_{doc_id}",
            case_file="MWK-001",
            model=model,
            max_tokens=2500,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return result
    except Exception as e:
        return {"is_title_document": False, "actual_type": "OTHER",
                "confidence": 0.0, "ocr_quality_flag": "low",
                "rejection_reason": f"extractor exception: {e}"[:240],
                "notes": ""}


# ─── PERSISTENCE ──────────────────────────────────────────────────────────

def store_extraction_chunk(cur, doc_id: int, result: dict):
    """Always persist the result to extraction_chunks as an audit trail,
    regardless of confidence. Provenance based on confidence."""
    prov = ("verified" if result.get("confidence", 0) >= CONFIDENCE_FLOOR
            else "inferred_strong" if result.get("confidence", 0) >= 0.50
            else "inferred_weak")
    cur.execute("""
        INSERT INTO extraction_chunks
            (doc_id, chunk_type, raw_json, provenance, created_at)
        VALUES (%s, 'tct_extracted', %s::jsonb, %s, NOW())
        ON CONFLICT DO NOTHING
        RETURNING id
    """, (doc_id, json.dumps(result), prov))
    row = cur.fetchone()
    return row[0] if row else None


def maybe_update_titles_table(cur, doc_id: int, result: dict, auto=False):
    """Only auto-update titles if confidence >= floor AND we have title_number.
    Otherwise queue a confirmation intake."""
    if not result.get("is_title_document"):
        return {"action": "rejected_not_title",
                "actual_type": result.get("actual_type"),
                "reason": result.get("rejection_reason")}

    tn = result.get("title_number")
    conf = result.get("confidence", 0)

    if not tn:
        return {"action": "skipped_no_title_number",
                "reason": "is_title_document=true but title_number is null (likely OCR low-quality)"}

    if conf < CONFIDENCE_FLOOR:
        return {"action": "below_confidence_floor",
                "confidence": conf,
                "reason": f"confidence {conf:.2f} < floor {CONFIDENCE_FLOOR} — needs operator confirm"}

    if not auto:
        return {"action": "extracted_pending_review",
                "title_number": tn, "confidence": conf}

    # Check if title already exists
    cur.execute("SELECT tct_number, registrant_canonical, provenance_level FROM titles WHERE tct_number=%s", (tn,))
    existing = cur.fetchone()
    if existing:
        # Don't overwrite verified rows; only enrich missing fields
        return {"action": "title_already_exists", "title_number": tn,
                "existing_provenance": existing[2]}

    owners = result.get("registered_owners") or []
    registrant = "; ".join(owners[:5]) if owners else None
    cur.execute("""
        INSERT INTO titles (tct_number, case_file, registrant_canonical, parent_title,
                            source_doc_id, location, area_sqm, status,
                            provenance_level)
        VALUES (%s, 'MWK-001', %s, %s, %s, %s, %s, 'active', 'verified')
        ON CONFLICT (tct_number) DO NOTHING
        RETURNING tct_number
    """, (tn, registrant, result.get("previous_title_ref"),
          doc_id, result.get("location"), result.get("area_sqm")))
    inserted = cur.fetchone()
    return {"action": "inserted" if inserted else "noop",
            "title_number": tn, "confidence": conf}


def queue_review_intake(cur, doc_id: int, result: dict):
    """Concise (per concision cap) intake for low-confidence / pending-review extractions."""
    tn = result.get("title_number") or "(no title # found)"
    actual = result.get("actual_type", "?")
    conf = result.get("confidence", 0)
    notes = (result.get("notes") or "")[:120]

    if not result.get("is_title_document"):
        body = (
            f"🔎 <b>Doc#{doc_id} — extractor rejected as non-TCT</b>\n"
            f"Actual type: <b>{actual}</b> (conf {conf:.0%})\n"
            f"{result.get('rejection_reason','')[:120]}\n"
            f"<code>/confirm</code> to re-classify · <code>/skip</code> to leave."
        )
    else:
        body = (
            f"🏷 <b>TCT extracted — doc#{doc_id}</b>\n"
            f"Title: <b>{tn}</b> · conf {conf:.0%} · OCR={result.get('ocr_quality_flag','?')}\n"
            f"{notes[:100]}\n"
            f"<code>/confirm</code> to insert into titles · <code>/skip</code>."
        )

    cur.execute("""
        INSERT INTO tg_inquiry_queue
            (kind, audience, priority, source_table, source_id, matter_code,
             composed_html, notes)
        VALUES ('intake_item', 'ops', 18, 'extract_tct', %s, %s, %s, %s)
        RETURNING id
    """, (doc_id, 'MWK-CV26360', body[:400],
          f"extract_tct:doc={doc_id}:conf={conf:.2f}:type={actual}:title={tn}"))
    return cur.fetchone()[0]


# ─── MAIN ─────────────────────────────────────────────────────────────────

def process_doc(client, doc_id: int, dry_run=False, auto=False):
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, classification, extracted_text,
                   COALESCE(smart_filename, document_title, original_filename) AS name
              FROM documents WHERE id = %s
        """, (doc_id,))
        doc = cur.fetchone()
        if not doc:
            print(f"  ✗ doc#{doc_id} not found"); return None
        if not doc["extracted_text"] or len(doc["extracted_text"]) < 100:
            print(f"  ✗ doc#{doc_id} has < 100 chars of OCR text"); return None

        print(f"  parsing doc#{doc_id} ({(doc['name'] or '?')[:50]})")
        result = extract_one_tct(client, doc_id, doc["extracted_text"])

        # Summary line
        if result.get("is_title_document"):
            print(f"    type={result.get('actual_type','?')} title={result.get('title_number','?')} "
                  f"conf={result.get('confidence',0):.2f} ocr={result.get('ocr_quality_flag','?')}")
        else:
            print(f"    REJECTED as non-TCT: actual_type={result.get('actual_type','?')} "
                  f"reason={(result.get('rejection_reason') or '')[:80]}")

        if dry_run:
            return result

        # Always store the extraction chunk for audit
        chunk_id = store_extraction_chunk(cur, doc_id, result)
        if chunk_id:
            print(f"    ✓ extraction_chunks.id={chunk_id} (audit row)")

        # Maybe update titles + maybe queue intake
        action = maybe_update_titles_table(cur, doc_id, result, auto=auto)
        print(f"    action: {action.get('action')}")
        if action["action"] not in ("inserted","title_already_exists","rejected_not_title"):
            inq_id = queue_review_intake(cur, doc_id, result)
            print(f"    → review intake #{inq_id}")

        return result
    finally:
        cur.close(); conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", type=int, help="One doc id")
    ap.add_argument("--scan-classified", action="store_true",
                    help="All Title-classified docs without a tct_extracted chunk")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--auto", action="store_true",
                    help="Auto-update titles table at confidence >= 0.80")
    args = ap.parse_args()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if args.doc:
        process_doc(client, args.doc, dry_run=args.dry_run, auto=args.auto)
        return

    if args.scan_classified:
        with psycopg2.connect(DSN) as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT d.id FROM documents d
                 WHERE d.classification = 'Title (TCT/OCT)'
                   AND d.extracted_text IS NOT NULL
                   AND LENGTH(d.extracted_text) >= 100
                   AND NOT EXISTS (
                     SELECT 1 FROM extraction_chunks ec
                      WHERE ec.doc_id = d.id AND ec.chunk_type = 'tct_extracted')
                 ORDER BY d.id LIMIT 50
            """)
            todo = [r["id"] for r in cur.fetchall()]
        print(f"extract_tct: {len(todo)} Title-classified docs to process")
        for did in todo:
            process_doc(client, did, dry_run=args.dry_run, auto=args.auto)


if __name__ == "__main__":
    main()
