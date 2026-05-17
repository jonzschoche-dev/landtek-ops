#!/usr/bin/env python3
"""doc_meta_extractor — fill classification + doc_date + summary + parties for
unclassified docs in one Haiku call each.

Consolidates doc_date_extractor logic + adds classification + parties + summary.
Cost: ~$0.002/doc. Cost-logged via llm_billing.

Usage:
  python3 doc_meta_extractor.py --case Paracale-001 --apply
  python3 doc_meta_extractor.py --doc 633 --apply   # single doc
  python3 doc_meta_extractor.py --case Paracale-001 --limit 5   # dry preview
"""
import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, "/root/landtek")
from landtek_core import db, get
from llm_billing import anthropic_call

SYSTEM_PROMPT = """You are reading the OCR'd text of a Philippine legal/business document.
Extract the document's metadata.

OUTPUT JSON ONLY (no prose, no markdown fences):
{
  "classification": "<one of: Title (TCT/OCT) | Tax Document | Deed | Affidavit | Judicial Affidavit | Complaint | Answer | Motion | Reply | Order | Resolution | Decision | Notice | Letter | Demand Letter | Special Power of Attorney | Power of Attorney | Contract | Receipt | Government Submission | Court Filing | Plan | Survey | Email | Correspondence | Memorandum | Transcript | Other>",
  "doc_date": "YYYY-MM-DD or null",
  "date_kind": "executed | filed | notarized | issued | unknown",
  "case_or_docket": "<civil case no., docket no., or null>",
  "parties": ["<list of named parties>"],
  "subject_brief": "<one-sentence summary, max 200 chars>",
  "confidence": 0.0-1.0
}

Be conservative. Use null when uncertain. The text may be OCR-damaged."""


def call_haiku(client, text):
    msg = anthropic_call(
        client,
        called_from="doc_meta_extractor",
        purpose="classify_and_date",
        case_file=None,
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text[:6000]}],
    )
    out = msg.content[0].text.strip()
    out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out)
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


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
    ap.add_argument("--case", default=None)
    ap.add_argument("--doc", type=int, default=None)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-conf", type=float, default=0.5)
    args = ap.parse_args()

    import anthropic
    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))

    with db() as cur:
        if args.doc:
            cur.execute("SELECT id, extracted_text, classification, smart_filename FROM documents WHERE id=%s", (args.doc,))
        elif args.case:
            cur.execute("""
                SELECT id, extracted_text, classification, smart_filename
                  FROM documents
                 WHERE case_file = %s
                   AND extracted_text IS NOT NULL AND length(extracted_text) >= 200
                   AND (classification IS NULL OR classification = '')
                 ORDER BY id LIMIT %s
            """, (args.case, args.limit))
        else:
            sys.exit("Usage: --case CASE | --doc N")
        docs = cur.fetchall()

        print(f"  {len(docs)} docs to process")
        applied = skipped = err = 0
        for d in docs:
            r = call_haiku(client, d["extracted_text"])
            if not r:
                err += 1
                print(f"  ⊘ doc#{d['id']}: no_json")
                continue
            cls = (r.get("classification") or "").strip()
            iso = parse_iso(r.get("doc_date"))
            conf = float(r.get("confidence") or 0)
            parties = ", ".join((r.get("parties") or [])[:5])[:200]
            summary = (r.get("subject_brief") or "")[:300]
            docket = r.get("case_or_docket")

            if conf < args.min_conf:
                print(f"  ↯ doc#{d['id']} low_conf={conf:.2f} cls={cls!r}")
                skipped += 1
                continue
            print(f"  ✓ doc#{d['id']}: {cls} · {iso or '—'} · parties={parties[:60]!r} · {summary[:80]!r}")

            if args.apply:
                cur.execute("""
                    UPDATE documents
                       SET classification = COALESCE(NULLIF(classification,''), %s),
                           doc_date_norm  = COALESCE(doc_date_norm, %s),
                           doc_date_quality = CASE WHEN doc_date_norm IS NULL AND %s IS NOT NULL
                                                 THEN 'parsed_by_haiku' ELSE doc_date_quality END,
                           doc_date = CASE WHEN doc_date IS NULL AND %s IS NOT NULL
                                        THEN %s::text ELSE doc_date END
                     WHERE id = %s
                """, (cls, iso, iso, iso, (iso.isoformat() if iso else None), d["id"]))
                # Save into extraction_chunks as audit
                cur.execute("""
                    INSERT INTO extraction_chunks
                      (doc_id, chunk_type, field_name, field_status, structured_value, provenance_level)
                    VALUES (%s, 'meta_extraction', 'haiku_meta', 'extracted', %s::jsonb, 'inferred_strong')
                    ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
                      SET structured_value = EXCLUDED.structured_value
                """, (d["id"], json.dumps(r)))
                applied += 1

        # Cost
        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(cost_usd),0)
              FROM llm_calls WHERE called_from='doc_meta_extractor'
                AND called_at >= NOW() - INTERVAL '15 min'
        """)
        n, cost = cur.fetchone().values()
        print(f"\n  applied={applied} skipped={skipped} err={err}")
        print(f"  cost: {n} Haiku calls = ${float(cost):.4f}")


if __name__ == "__main__":
    main()
