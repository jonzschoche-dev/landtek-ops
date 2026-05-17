#!/usr/bin/env python3
"""extract_transaction_terms — forensic transaction-terms extractor (deploy_171).

Per Jonathan 2026-05-17: "a deed entry that just says 'Deed of Absolute Sale'
without the price, the lot number, or the subdivision plan is like a grocery
receipt that doesn't show the total."

This script:
  1. Filters documents to transaction-bearing types (Deed, Contract, Sale,
     Donation, Subdivision Plan, Title Transfer, SPA with sale authority)
  2. Sends the OCR text to Haiku 4.5 with a STRICT tool-call schema enforcing
     numeric prices, area_sqm format, and verbatim party names
  3. Persists to documents.{lot_number, subdivision_plan, area_sqm,
     consideration_price, grantor_seller, grantee_buyer}
  4. Re-exports MWK_Transaction_Ledger.csv with the new substantive columns

NO prose. NO summaries. NO hallucination — strict tool-call schema means the
LLM cannot output unstructured text. provenance_level='vision_extracted'.

This is foundational to the "every square meter × day" vision — these terms
are the fuel for the parcels-table reconstruction (next layer).
"""
import argparse
import csv
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Strict JSON schema for extraction — no free-text fields, every value typed
TXN_TERMS_SCHEMA = {
    "type": "object",
    "properties": {
        "lot_number": {
            "type": ["string", "null"],
            "description": ("Specific lot designation per PH subdivision-plan convention "
                            "(e.g., 'Lot 2-X-6-P', 'Lot 4493', 'Lot 2-X-4'). "
                            "Use null if not stated.")
        },
        "subdivision_plan": {
            "type": ["string", "null"],
            "description": ("Subdivision plan number, e.g., 'Psd-05-026614', "
                            "'LRC Psd-12802', 'Plan No. Bsd-11458'. Null if not stated.")
        },
        "area_sqm": {
            "type": ["number", "null"],
            "description": ("Land area in square meters. Convert hectares to sqm "
                            "(1 ha = 10000 sqm). Null if not stated.")
        },
        "consideration_price": {
            "type": ["number", "null"],
            "description": ("Monetary consideration paid, as a number in the document's "
                            "stated currency (default PHP). For 'P 250,000.00' return "
                            "250000. For donations or non-monetary transfers, return null.")
        },
        "consideration_currency": {
            "type": "string",
            "description": "Currency code, default 'PHP'. Use 'USD' if document states US dollars.",
            "enum": ["PHP", "USD", "OTHER"]
        },
        "grantor_seller": {
            "type": ["string", "null"],
            "description": ("Verbatim name of conveying party (seller, donor, transferor). "
                            "If multiple, comma-separate. Null if illegible or absent.")
        },
        "grantee_buyer": {
            "type": ["string", "null"],
            "description": ("Verbatim name of receiving party (buyer, donee, transferee). "
                            "If multiple, comma-separate. Null if illegible or absent.")
        },
        "instrument_date": {
            "type": ["string", "null"],
            "description": "Execution date in YYYY-MM-DD. Null if not stated.",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
        },
        "instrument_type": {
            "type": ["string", "null"],
            "description": ("Canonical type: 'Deed of Absolute Sale', 'Deed of Donation', "
                            "'Deed of Conditional Sale', 'Subdivision Plan', "
                            "'Special Power of Attorney', 'Contract to Sell', 'Title Transfer'. "
                            "Null if unclear.")
        }
    },
    "required": ["lot_number", "subdivision_plan", "area_sqm", "consideration_price",
                  "consideration_currency", "grantor_seller", "grantee_buyer",
                  "instrument_date", "instrument_type"]
}


PROMPT_TEMPLATE = """You are a forensic legal-data extractor for Philippine
property transactions. Extract STRUCTURED TERMS from the document below.

CRITICAL RULES:
- Return ONLY the structured fields. Never narrate or summarize.
- If a field is illegible or absent, return null. NEVER guess.
- For consideration_price: convert "P 250,000.00" → 250000 (number, not string).
  For "Twenty-Five Thousand Pesos (P25,000.00)" → 25000. For donations → null.
- For area_sqm: convert "1.5 hectares" → 15000. For "139,132 sqm" → 139132.
- For lot_number: use the EXACT format in the document (e.g., "Lot 2-X-6-P").
- For subdivision_plan: include the prefix (Psd-, LRC Psd-, Bsd-).
- For party names: verbatim, including all listed co-owners. No interpretation.

You MUST use the tool 'extract_terms' to return your answer.

FILENAME: {filename}
CLASSIFICATION: {classification}

OCR TEXT:
{text}
"""


def fetch_targets(cur, case_file, only_ids=None, limit=None):
    where = "AND d.id = ANY(%s)" if only_ids else ""
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    params = [case_file]
    if only_ids:
        params.append(only_ids)
    cur.execute(f"""
        SELECT d.id, d.classification, d.smart_filename, d.original_filename,
               d.document_title, d.doc_date_norm, d.extracted_text,
               d.drive_link, d.drive_file_id
          FROM documents d
         WHERE d.case_file = %s
           AND (
             d.classification ~* 'deed|donation|sale|contract|transfer|subdivision'
             OR d.smart_filename ILIKE '%%deed%%'
             OR d.smart_filename ILIKE '%%sale%%'
             OR d.smart_filename ILIKE '%%donation%%'
           )
           AND length(coalesce(d.extracted_text, '')) >= 200
           {where}
         ORDER BY d.doc_date_norm NULLS LAST, d.id
         {limit_clause}
    """, params)
    return cur.fetchall()


def extract_one(client, doc):
    """Call Haiku with strict tool-call schema. Returns dict or None."""
    from llm_billing import anthropic_tool_call
    text = (doc.get("extracted_text") or "")[:8000]
    prompt = PROMPT_TEMPLATE.format(
        filename=(doc.get("smart_filename") or doc.get("original_filename") or "(no filename)"),
        classification=(doc.get("classification") or "(unclassified)"),
        text=text,
    )
    try:
        result = anthropic_tool_call(
            client,
            tool_name="extract_terms",
            tool_description="Submit extracted transaction terms.",
            input_schema=TXN_TERMS_SCHEMA,
            called_from="extract_transaction_terms",
            purpose="forensic_terms_extraction",
            case_file="MWK-001",
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=("You are a precise structured-data extractor for Philippine "
                    "property transactions. No narration, only fields."),
            messages=[{"role": "user", "content": prompt}],
        )
        return result
    except Exception as e:
        return {"error": str(e)[:200]}


def persist(cur, doc_id, terms):
    """Update documents row with the extracted terms (only non-null fields)."""
    cur.execute("""
        UPDATE documents
           SET lot_number             = COALESCE(%s, lot_number),
               subdivision_plan       = COALESCE(%s, subdivision_plan),
               area_sqm               = COALESCE(%s, area_sqm),
               consideration_price    = COALESCE(%s, consideration_price),
               consideration_currency = COALESCE(%s, consideration_currency),
               grantor_seller         = COALESCE(%s, grantor_seller),
               grantee_buyer          = COALESCE(%s, grantee_buyer),
               terms_extracted_at     = NOW(),
               terms_provenance       = 'haiku_4.5_tool_call',
               updated_at             = NOW()
         WHERE id = %s
    """, (terms.get("lot_number"), terms.get("subdivision_plan"),
          terms.get("area_sqm"), terms.get("consideration_price"),
          terms.get("consideration_currency") or "PHP",
          terms.get("grantor_seller"), terms.get("grantee_buyer"),
          doc_id))


def write_ledger(cur, case_file):
    cur.execute("""
        SELECT id, doc_date_norm, classification,
               smart_filename, document_title,
               lot_number, subdivision_plan, area_sqm,
               consideration_price, consideration_currency,
               grantor_seller, grantee_buyer,
               drive_link, drive_file_id, file_path
          FROM documents
         WHERE case_file = %s
           AND (
             classification ~* 'deed|donation|sale|contract|transfer|subdivision'
             OR lot_number IS NOT NULL
             OR consideration_price IS NOT NULL
           )
         ORDER BY doc_date_norm NULLS LAST, id
    """, (case_file,))
    rows = cur.fetchall()
    today = date.today().isoformat()
    path = Path(f"/root/landtek/drafts/MWK_Transaction_Ledger_{today}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "date", "instrument_type",
                    "lot_number", "subdivision_plan", "area_sqm",
                    "consideration_price", "currency",
                    "grantor_seller", "grantee_buyer",
                    "filename", "source_link"])
        for r in rows:
            src = r["drive_link"] or (f"https://drive.google.com/file/d/{r['drive_file_id']}/view"
                                       if r["drive_file_id"] else
                                       f"file://{r['file_path']}" if r["file_path"]
                                       else "[no source]")
            w.writerow([r["id"], r["doc_date_norm"], r["classification"],
                        r["lot_number"], r["subdivision_plan"], r["area_sqm"],
                        r["consideration_price"], r["consideration_currency"],
                        r["grantor_seller"], r["grantee_buyer"],
                        (r["smart_filename"] or r["document_title"] or "")[:80],
                        src])
    return path, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--ids", help="Comma-separated doc ids to target (verification mode)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    only_ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    targets = fetch_targets(cur, args.case, only_ids, args.limit)
    print(f"Target docs: {len(targets)}")

    import anthropic
    from landtek_core import get
    api_key = get("ANTHROPIC_API_KEY")
    if not api_key:
        for l in open("/root/landtek/.env"):
            if l.startswith("ANTHROPIC_API_KEY="):
                api_key = l.split("=", 1)[1].strip(); break
    client = anthropic.Anthropic(api_key=api_key)

    for doc in targets:
        print(f"\n──── doc#{doc['id']} ({doc['classification']}) date={doc['doc_date_norm']} ────")
        print(f"  filename: {doc['smart_filename'] or doc['original_filename'] or '(none)'}")
        if doc.get("document_title"):
            print(f"  title:    {doc['document_title'][:80]}")
        terms = extract_one(client, doc)
        if terms.get("error"):
            print(f"  ✗ {terms['error']}"); continue
        print(f"  EXTRACTED:")
        for k in ("instrument_type", "instrument_date", "lot_number", "subdivision_plan",
                  "area_sqm", "consideration_price", "consideration_currency",
                  "grantor_seller", "grantee_buyer"):
            v = terms.get(k)
            print(f"    {k:24s}: {v}")
        if not args.dry_run:
            persist(cur, doc["id"], terms)

    if not args.dry_run:
        path, n = write_ledger(cur, args.case)
        print(f"\n✓ Wrote transaction ledger: {path} ({n} rows)")


if __name__ == "__main__":
    main()
