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
    """Insert into legal_cost_actuals."""
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


def queue_confirmation_intake(matter_code: str, doc_id: int, result: dict):
    """Queue ONE concise intake asking operator to /confirm or /correct."""
    total = result.get("total_php")
    vendor = result.get("vendor") or "(unknown vendor)"
    date = result.get("date") or "(no date)"
    cat = result.get("category", "misc")
    conf = result.get("confidence", 0)
    body = (
        f"🧾 <b>Receipt extracted — doc#{doc_id}</b>\n"
        f"<b>{vendor[:50]}</b> · ₱{total:,.2f} · {date} · {cat} (conf {conf:.0%})\n\n"
        f"Reply <code>/confirm</code> to log to {matter_code}, "
        f"<code>cost</code> + corrections, or <code>/skip</code>."
    )[:400]
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
        """, (doc_id, matter_code, body,
              f"receipt_extractor:doc={doc_id}:pending_confirmation:"
              f"vendor={vendor[:40]}:total={total}:category={cat}"))
        return cur.fetchone()[0]


def process_doc(client, doc_id, matter_override=None, auto=False):
    with psycopg2.connect(DSN) as conn:
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

    matter = matter_override or doc["matter_code"] or (
        "MWK-001" if doc["case_file"] == "MWK-001" else "PAR-CAPACUAN")

    print(f"  parsing doc#{doc_id} ({(doc['name'] or '(unnamed)')[:50]})...")
    result = extract_receipt(client, doc_id, doc["extracted_text"])

    if not result.get("is_receipt"):
        print(f"    not a receipt: {result.get('notes','')[:80]}")
        return None
    print(f"    vendor={result.get('vendor','?')[:40]} total={result.get('total_php')} "
          f"date={result.get('date')} cat={result.get('category')} "
          f"conf={result.get('confidence',0):.2f}")

    if auto and result.get("confidence", 0) >= 0.8:
        row_id = write_cost_from_receipt(matter, doc_id, result)
        print(f"    ✓ AUTO-wrote legal_cost_actuals.id={row_id}")
        return {"action": "auto_written", "row_id": row_id}

    inq_id = queue_confirmation_intake(matter, doc_id, result)
    print(f"    ✓ queued confirmation intake #{inq_id}")
    return {"action": "intake_queued", "inquiry_id": inq_id}


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
