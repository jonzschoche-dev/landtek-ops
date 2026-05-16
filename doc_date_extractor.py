#!/usr/bin/env python3
"""Backfill documents.doc_date_norm for executed_filed/government_issued docs
that have no parseable date.

Per meta-agent invariant EXECUTED_FILED_NO_DATE (~74 docs flagged 2026-05-16):
those docs are invisible in their matter's timeline. Critical data-quality
blocker.

Approach: for each undated doc, take the first ~6000 chars of extracted_text
and ask Haiku (cheap) to extract the document's primary date in YYYY-MM-DD form.
Cost: ~$0.001 per doc → ~$0.08 for 74 docs. All cost-logged via llm_billing.

Usage:
  python3 doc_date_extractor.py            # report-only (dry run)
  python3 doc_date_extractor.py --apply    # actually write to doc_date_norm
  python3 doc_date_extractor.py --limit 20 --apply
"""
import argparse
import json
import os
import re
import sys
from datetime import date
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek")
from llm_billing import anthropic_call

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SYSTEM_PROMPT = """You are reading the extracted text of a Philippine legal document.
Determine the document's PRIMARY DATE — the date the document was signed, executed,
filed, dated, or issued (whichever applies).

Priority order for "primary date":
  1. The DATED/EXECUTED date in the body or signature block (most authoritative).
  2. The filed/received stamp date (court Receiving stamp).
  3. The notarized/jurat date (for affidavits, deeds, SPAs).
  4. The Issued On / Effective date (for notices, orders).

Output JSON ONLY (no prose, no markdown fences):
  {"date": "YYYY-MM-DD" | null, "kind": "executed"|"filed"|"notarized"|"issued"|"unknown", "source_quote": "<short verbatim text>", "confidence": 0.0-1.0}

If you cannot find a clear primary date, return {"date": null, "confidence": 0.0}."""


def call_haiku(client, text: str):
    msg = anthropic_call(
        client,
        called_from="doc_date_extractor",
        purpose="extract_primary_date",
        case_file="MWK-001",
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text[:6000]}],
    )
    out = msg.content[0].text.strip()
    # Strip code fences if any
    out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out)
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return j


def parse_iso(s):
    if not s: return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s.strip())
    if not m: return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--min-confidence", type=float, default=0.6)
    args = ap.parse_args()

    api_key = None
    with open("/root/landtek/.env") as f:
        for ln in f:
            if ln.startswith("ANTHROPIC_API_KEY="):
                api_key = ln.strip().split("=", 1)[1]
    if not api_key:
        sys.exit("FATAL: ANTHROPIC_API_KEY missing")

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, smart_filename, classification, execution_status, doc_date,
               LEFT(extracted_text, 6500) AS text
          FROM documents
         WHERE execution_status IN ('executed_filed','executed_notarized','government_issued')
           AND doc_date_norm IS NULL
           AND extracted_text IS NOT NULL AND length(extracted_text) >= 200
         ORDER BY id
         LIMIT %s
    """, (args.limit,))
    docs = cur.fetchall()
    print(f"  {len(docs)} undated executed/filed docs to process")

    extracted = skipped = low_conf = 0
    for d in docs:
        result = call_haiku(client, d["text"])
        if not result:
            skipped += 1
            print(f"  ⊘ doc#{d['id']}: no_json")
            continue
        date_str = result.get("date")
        confidence = float(result.get("confidence") or 0)
        parsed = parse_iso(date_str)
        if not parsed:
            skipped += 1
            print(f"  ⊘ doc#{d['id']}: no_valid_date (conf={confidence:.2f})")
            continue
        if confidence < args.min_confidence:
            low_conf += 1
            print(f"  ↯ doc#{d['id']}: low_conf {confidence:.2f} → {parsed}  ({result.get('kind')})")
            continue
        if args.apply:
            cur.execute("""
                UPDATE documents
                   SET doc_date_norm = %s,
                       doc_date_quality = 'parsed_by_haiku',
                       doc_date = COALESCE(doc_date, %s)
                 WHERE id = %s
            """, (parsed, parsed.isoformat(), d["id"]))
        extracted += 1
        kind = result.get("kind", "?")
        quote = (result.get("source_quote") or "")[:50]
        print(f"  ✓ doc#{d['id']}: {parsed} ({kind}, conf={confidence:.2f}) — {quote!r}")

    print(f"\n  extracted: {extracted}  low_conf: {low_conf}  skipped: {skipped}  total: {len(docs)}")
    if not args.apply:
        print(f"  (dry run — pass --apply to write doc_date_norm)")

    # Cost
    cur.execute("""
        SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost
          FROM llm_calls
         WHERE called_from='doc_date_extractor' AND called_at >= NOW() - INTERVAL '15 min'
    """)
    r = cur.fetchone()
    print(f"  cost: {r['calls']} Haiku calls = ${float(r['cost']):.4f}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
