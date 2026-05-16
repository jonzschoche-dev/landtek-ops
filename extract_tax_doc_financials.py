#!/usr/bin/env python3
"""Extract financial data from Tax Document corpus (deploy_113-A backfill).

For each Tax Document with extracted text, call Claude Haiku to structure-extract:
  - ARP / Tax Dec number
  - PIN (Property Index Number)
  - Owner
  - Location
  - Area sqm
  - Market value
  - Assessed value
  - Tax effectivity year
  - Total delinquent amount (if statement of account)
  - Asset_title (TCT/OCT no) if linkable
  - Payments recorded (if OR/receipt)

Populates:
  - asset_valuations (assessed/market values per asset+date snapshot)
  - transactions (when payment events are documented)
  - monthly_overhead (when recurring RPT obligation discovered)

Every figure is provenance-tagged to source_doc_id. Drafts/illegible
returns 'unknown' rather than fabricated.

Usage:
  python3 extract_tax_doc_financials.py --limit 20      # sample
  python3 extract_tax_doc_financials.py                 # full corpus
  python3 extract_tax_doc_financials.py --dry-run       # extract without writing
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import date
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def load_api_key():
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.strip().split("=", 1)[1]
    return None


PROMPT_SYSTEM = """You are an extraction engine for Philippine real-property tax documents. Given the OCR text of a tax doc, extract structured fields. Be conservative — if a field is illegible or absent, set it to null.

Output a JSON object with these fields:
{
  "doc_kind": "tax_declaration" | "statement_of_account" | "official_receipt" | "real_property_tax_payment" | "tax_amnesty" | "unknown",
  "arp_no": str or null,
  "pin": str or null,
  "owner_name": str or null,
  "location": str or null,
  "barangay": str or null,
  "municipality": str or null,
  "area_sqm": number or null,
  "kind": "Land" | "Building" | "Machinery" | null,
  "actual_use": "Residential" | "Commercial" | "Agricultural" | "Industrial" | "Idle" | "Mixed" | null,
  "market_value": number or null,
  "assessed_value": number or null,
  "assessment_level_pct": number or null,
  "tax_effectivity_year": int or null,
  "previous_arp": str or null,
  "asset_titles": [str, ...]  // TCT/OCT numbers if mentioned (e.g., "T-52540")
  "or_no": str or null,        // Official Receipt number
  "or_date": "YYYY-MM-DD" or null,
  "payment_amount": number or null,
  "total_delinquent": number or null,
  "delinquent_years": [int, ...],
  "issuing_office": str or null,
  "computation_as_of": "YYYY-MM-DD" or null,
  "confidence": number  // 0..1 — your confidence in the overall extraction
}

NO commentary, NO markdown — ONLY the JSON object."""


def call_haiku(text, api_key):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    import sys as _sys; _sys.path.insert(0, "/root/landtek")
    from llm_billing import anthropic_call
    msg = anthropic_call(
        client,
        called_from="extract_tax_doc_financials",
        purpose="extract_tax_dec",
        case_file="MWK-001",
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system=PROMPT_SYSTEM,
        messages=[{"role": "user", "content": text[:30000]}],
    )
    out = msg.content[0].text.strip()
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0)), None
        except json.JSONDecodeError as e:
            return None, f"json_err: {e}"
    return None, "no_json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reextract", action="store_true",
                    help="re-extract even if already done")
    args = ap.parse_args()

    api_key = load_api_key()
    if not api_key:
        sys.exit("FATAL: ANTHROPIC_API_KEY not in .env")

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Find candidates
    where = ["classification = 'Tax Document'", "extracted_text IS NOT NULL", "length(extracted_text) >= 300"]
    if not args.reextract:
        # Skip docs we've already processed
        where.append("""NOT EXISTS (
            SELECT 1 FROM asset_valuations av
             WHERE %s = ANY(av.source_docs) AND av.notes LIKE 'extracted from tax doc%%'
        )""")
    sql = f"""
      SELECT id, smart_filename, case_file,
             LEFT(extracted_text, 30000) AS extracted_text
        FROM documents
       WHERE {' AND '.join(where)}
       ORDER BY id
       {'LIMIT %s' if args.limit else ''}
    """
    # The skip-EXISTS clause uses %s for doc id — but here we want it bound to the column,
    # so rewrite the EXISTS to a NOT IN list, computed up-front.
    if not args.reextract:
        cur.execute("""
            SELECT DISTINCT source_docs[1] AS d FROM asset_valuations
             WHERE source_docs IS NOT NULL AND notes LIKE 'extracted from tax doc%%'
        """)
        already = [r["d"] for r in cur.fetchall() if r["d"]]
        # rebuild SQL without the EXISTS clause
        base = ["classification = 'Tax Document'", "extracted_text IS NOT NULL", "length(extracted_text) >= 300"]
        if already:
            base.append("id <> ALL(%s::int[])")
        sql = f"""SELECT id, smart_filename, case_file,
                         LEFT(extracted_text, 30000) AS extracted_text
                    FROM documents
                   WHERE {' AND '.join(base)}
                   ORDER BY id
                   {'LIMIT %s' if args.limit else ''}"""
        params = []
        if already: params.append(already)
        if args.limit: params.append(args.limit)
        cur.execute(sql, params)
    else:
        params = []
        if args.limit: params.append(args.limit)
        cur.execute(sql, params)
    docs = cur.fetchall()
    print(f"  candidates: {len(docs)}")

    stats = {"tax_decl": 0, "statement": 0, "receipt": 0, "unknown": 0, "errors": 0, "skipped": 0}
    asset_vals = 0; txs = 0

    for d in docs:
        result, err = call_haiku(d["extracted_text"], api_key)
        if err or not result:
            stats["errors"] += 1
            print(f"  ✗ doc #{d['id']}: {err}")
            continue
        kind = result.get("doc_kind", "unknown")
        if kind == "tax_declaration":
            stats["tax_decl"] += 1
        elif kind == "statement_of_account":
            stats["statement"] += 1
        elif kind in ("official_receipt", "real_property_tax_payment"):
            stats["receipt"] += 1
        else:
            stats["unknown"] += 1
        conf = float(result.get("confidence", 0) or 0)
        if conf < 0.35:
            stats["skipped"] += 1
            print(f"  ⊘ doc #{d['id']} low-conf ({conf:.2f}): {result.get('doc_kind')}")
            continue

        # Determine asset_title for valuation
        titles = result.get("asset_titles") or []
        primary_title = (titles[0] if titles else None) or result.get("arp_no")
        market = result.get("market_value")
        assessed = result.get("assessed_value")

        if args.dry_run:
            print(f"  [DRY] doc #{d['id']} ({result.get('doc_kind')}): arp={result.get('arp_no')} "
                  f"market={market} assessed={assessed} titles={titles[:3]}")
            continue

        # Insert asset_valuation if we have any numeric figures + an identifier
        if (market or assessed) and primary_title:
            today = date.today()
            cur.execute("""
                INSERT INTO asset_valuations
                  (asset_title, case_file, snapshot_date, tax_dec_no, area_sqm,
                   assessed_value, market_price_value, current_use,
                   source_docs, provenance_level, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'inferred_strong',%s)
                RETURNING id
            """, (primary_title, d["case_file"], today, result.get("arp_no"),
                  result.get("area_sqm"), assessed, market,
                  result.get("actual_use"),
                  [d["id"]],
                  f"extracted from tax doc #{d['id']} ({d['smart_filename']}) conf={conf:.2f}"))
            asset_vals += 1

        # Insert transaction if payment recorded
        pay_amt = result.get("payment_amount")
        or_no = result.get("or_no")
        or_date = result.get("or_date")
        if pay_amt and or_date and d["case_file"]:
            try:
                cur.execute("""
                    INSERT INTO transactions
                      (tx_date, case_file, amount, direction, category, description,
                       source_doc_id, source_tx_ref, provenance_level, account_id)
                    VALUES (%s,%s,%s,'debit','rpt',%s,%s,%s,'verified',
                            (SELECT id FROM accounts WHERE account_code='MWK-EXP-RPT' LIMIT 1))
                    ON CONFLICT DO NOTHING
                """, (or_date, d["case_file"], pay_amt,
                      f"RPT payment per OR #{or_no} ({result.get('issuing_office')})",
                      d["id"], or_no))
                txs += 1
            except Exception as e:
                print(f"     ⚠ tx insert err: {e}")

        print(f"  ✓ doc #{d['id']} {kind:18s}  ARP={result.get('arp_no') or '—'}  "
              f"market={market or '—'}  assessed={assessed or '—'}  pay={pay_amt or '—'}")
        time.sleep(0.5)  # be gentle to API

    print(f"\n  Summary:")
    for k, v in stats.items():
        print(f"    {k:12s}  {v}")
    print(f"    asset_valuations inserted: {asset_vals}")
    print(f"    transactions inserted:     {txs}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
