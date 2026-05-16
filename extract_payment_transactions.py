#!/usr/bin/env python3
"""Extract payment-transaction events from corpus (deploy_117-C).

For each document containing an OR number + PHP amount + recognizable issuer:
  - Identify it as a payment receipt vs a statement/letter
  - Extract: OR no, date, amount, payer, payee, category
  - Insert into transactions table with source_doc_id citation
  - Skip ambiguous (no clear OR-amount-date trio)
"""
import argparse
import json
import os
import re
import sys
import time
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def load_api_key():
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.strip().split("=", 1)[1]
    return None


PROMPT_SYSTEM = """You are an extraction engine for Philippine real-property and government receipts.

Given the OCR text of a document, identify if it's a PAYMENT RECEIPT (Official Receipt, OR, tax payment, filing fee, notarial fee, etc.) and extract structured payment data.

If the document is NOT a payment receipt (it's a letter, complaint, statement-of-account, deed, etc.), set is_receipt=false.

Output a JSON object:
{
  "is_receipt": bool,
  "or_no": str or null,
  "or_date": "YYYY-MM-DD" or null,
  "amount_php": number or null,
  "payer": str or null,         // who paid
  "payee": str or null,          // who received (BIR, RD, Municipal Treasurer, etc.)
  "category": "rpt" | "filing_fee" | "notary_fee" | "docket_fee" | "registration_fee" | "cnr" | "transfer_tax" | "doc_stamps" | "cgt" | "other" | null,
  "asset_titles": [str, ...] OR [],  // TCT/OCT numbers referenced
  "case_file_hint": str or null,     // 'MWK-001' if Mary Worrick Keesey context, 'Paracale-001' if Allan Inocalla, else null
  "confidence": number  // 0..1
}

If the doc has MULTIPLE receipts, return the LARGEST or MOST RECENT one. Be conservative — only set is_receipt=true if you see a clear OR/receipt structure.

NO commentary, NO markdown — ONLY the JSON object."""


def call_haiku(text, api_key, retries=3):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    backoff = 3
    for attempt in range(retries):
        try:
            import sys as _sys; _sys.path.insert(0, "/root/landtek")
            from llm_billing import anthropic_call
            msg = anthropic_call(
                client,
                called_from="extract_payment_transactions",
                purpose="extract_transaction",
                case_file="MWK-001",
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                system=PROMPT_SYSTEM,
                messages=[{"role": "user", "content": text[:25000]}],
            )
            out = msg.content[0].text.strip()
            m = re.search(r"\{.*\}", out, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0)), None
                except json.JSONDecodeError as e:
                    return None, f"json_err: {e}"
            return None, "no_json"
        except anthropic.RateLimitError as e:
            if attempt < retries - 1:
                time.sleep(backoff); backoff *= 2; continue
            return None, f"rate_limit: {e}"
        except anthropic.APIStatusError as e:
            if attempt < retries - 1 and e.status_code in (429, 503, 529):
                time.sleep(backoff); backoff *= 2; continue
            return None, f"api_err_{e.status_code}: {str(e)[:120]}"
        except Exception as e:
            return None, f"err: {str(e)[:120]}"
    return None, "max_retries"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api_key = load_api_key()
    if not api_key:
        sys.exit("FATAL: ANTHROPIC_API_KEY missing")

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Candidates: docs with OR pattern OR with amount-like text, not already processed for payments
    cur.execute("""
        SELECT DISTINCT source_doc_id FROM transactions
         WHERE source_doc_id IS NOT NULL
    """)
    already = {r["source_doc_id"] for r in cur.fetchall()}
    already_list = list(already) if already else [-1]

    cur.execute("""
        SELECT id, smart_filename, case_file, classification,
               LEFT(extracted_text, 25000) AS text
          FROM documents
         WHERE extracted_text IS NOT NULL
           AND length(extracted_text) >= 200
           AND id <> ALL(%s::int[])
           AND (
             extracted_text ILIKE '%%official receipt%%'
             OR extracted_text ~ 'OR\\s*[Nn]o\\.?\\s*[:]*\\s*[0-9]{4,}'
             OR extracted_text ~ 'OR\\s*[#]\\s*[0-9]{4,}'
             OR (classification IN ('Receipt') AND extracted_text ~ 'P[^A-Za-z]*[0-9]{2,}')
           )
         ORDER BY id DESC
    """, (already_list,))
    docs = cur.fetchall()
    if args.limit:
        docs = docs[:args.limit]
    print(f"  {len(docs)} candidate docs (skipping {len(already)} already processed)")

    # Resolve account_id map (so we can attach transactions properly)
    cur.execute("SELECT id, account_code FROM accounts")
    accounts = {r["account_code"]: r["id"] for r in cur.fetchall()}

    CATEGORY_TO_ACCOUNT = {
        "rpt":                   ("MWK-EXP-RPT",),
        "filing_fee":            ("MWK-EXP-FILING", "LT-EXP-FILING"),
        "notary_fee":            ("MWK-EXP-NOTARY", "LT-EXP-NOTARY"),
        "docket_fee":            ("MWK-EXP-FILING", "LT-EXP-FILING"),
        "registration_fee":     ("MWK-EXP-FILING", "LT-EXP-FILING"),
        "cnr":                   ("MWK-EXP-FILING",),
        "transfer_tax":          ("MWK-EXP-FILING",),
        "doc_stamps":            ("MWK-EXP-FILING",),
        "cgt":                   ("MWK-EXP-MISC",),
        "other":                 ("MWK-EXP-MISC",),
    }

    inserted = errors = skipped = 0
    by_cat = {}

    for d in docs:
        result, err = call_haiku(d["text"], api_key)
        if err or not result:
            errors += 1; continue
        if not result.get("is_receipt"):
            skipped += 1; continue
        amt = result.get("amount_php")
        if not amt or float(amt) <= 0:
            skipped += 1; continue
        or_date = result.get("or_date")
        if not or_date or not re.match(r"^\d{4}-\d{2}-\d{2}$", or_date):
            skipped += 1; continue
        category = result.get("category") or "other"
        case_file = d.get("case_file") or result.get("case_file_hint")

        # Pick account
        account_id = None
        for acc_code in CATEGORY_TO_ACCOUNT.get(category, ("MWK-EXP-MISC",)):
            if acc_code in accounts:
                account_id = accounts[acc_code]; break

        if args.dry_run:
            print(f"  [DRY] doc#{d['id']} {category:14s} OR={result.get('or_no')} amount=₱{amt} date={or_date}")
            inserted += 1
            by_cat[category] = by_cat.get(category, 0) + 1
            continue

        try:
            cur.execute("""
                INSERT INTO transactions
                  (tx_date, case_file, amount, direction, category, description,
                   source_doc_id, source_tx_ref, provenance_level, account_id, counterparty)
                VALUES (%s, %s, %s, 'debit', %s, %s, %s, %s, 'verified', %s, %s)
            """, (or_date, case_file, amt, category,
                  f"{category} payment per OR — {(d['smart_filename'] or '')[:80]}",
                  d["id"], result.get("or_no"), account_id, result.get("payee")))
            inserted += 1
            by_cat[category] = by_cat.get(category, 0) + 1
            if inserted % 10 == 0:
                print(f"  ✓ {inserted} inserted (current: {category} OR={result.get('or_no')} ₱{amt})")
        except Exception as e:
            errors += 1
            print(f"  ⚠ doc#{d['id']} insert fail: {e}")
        time.sleep(0.3)

    print(f"\n  Summary:")
    print(f"    inserted: {inserted}")
    print(f"    skipped:  {skipped} (not receipts or missing data)")
    print(f"    errors:   {errors}")
    print(f"  By category:")
    for c, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"    {c}: {n}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
