#!/usr/bin/env python3
"""llm_title_extractor — Sonnet 4.6 forensic Torrens-title-history extraction.

Per Jonathan 2026-05-18: pure DB-string-pulling missed evidence buried inside
PDF text. Activate LLM extraction with a STRICT tool-call schema (no prose)
to surface every title-transaction reference across the corpus.

Pipeline:
  1. Iterate canonical MWK-001 docs with substantive text (≥500 chars).
     Skip docs already processed (one row in llm_extracted_lineage means
     we've tried that doc).
  2. For each, send first 12K chars of extracted_text to Sonnet 4.6 with
     a strict tool-call schema that ONLY accepts a JSON array of structured
     transactions. The LLM cannot output prose.
  3. Each transaction inserts one row to llm_extracted_lineage. Multi-
     transaction docs (annex tables, etc.) produce multiple rows.
  4. Hardcoded axiom in the system prompt: OCT T-106 → T-111 → T-4493 is
     the foundational trunk. Composite-form titles like '1-106' normalize
     to 'OCT T-106'.

provenance_level = 'llm_sonnet_4_6_extracted' — not 'verified' until human
review. The rows ARE evidence the LLM saw text matching a transaction pattern,
not legal confirmation that the transaction is real.
"""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "transactions": {
            "type": "array",
            "description": ("Array of EVERY title-transaction reference found in the document. "
                            "If the document is a deed or transfer, expect 1 transaction. "
                            "If it's an annex listing a chain or registry-request enumerating "
                            "multiple titles, expect many. If the document references no "
                            "title transactions at all, return an empty array."),
            "items": {
                "type": "object",
                "properties": {
                    "parent_title": {
                        "type": ["string", "null"],
                        "description": ("Mother title in canonical form: 'OCT T-NNN', "
                                        "'T-NNNN', or 'T-NNN-NNNNNNNNNN'. Apply the "
                                        "foundational-trunk axiom: '1-106', 'F-106', "
                                        "'OCT 106' → 'OCT T-106'. Null if unstated.")
                    },
                    "derivative_title": {
                        "type": ["string", "null"],
                        "description": "Resulting / derivative title in same canonical form."
                    },
                    "transaction_date": {
                        "type": ["string", "null"],
                        "description": "YYYY-MM-DD. The execution/registration date.",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                    },
                    "buyer_transferee": {
                        "type": ["string", "null"],
                        "description": "Verbatim name of the buyer / transferee / grantee."
                    },
                    "seller_transferor": {
                        "type": ["string", "null"],
                        "description": "Verbatim name of seller / transferor / grantor."
                    },
                    "lot_number_and_plan": {
                        "type": ["string", "null"],
                        "description": ("Lot designation + subdivision plan combined "
                                        "(e.g., 'Lot 2-X-6-H, Psd-256008').")
                    },
                    "area_sqm": {
                        "type": ["number", "null"],
                        "description": "Land area in square meters. Convert hectares (×10000)."
                    },
                    "consideration_price": {
                        "type": ["number", "null"],
                        "description": "Monetary consideration in PHP. Null for donations."
                    },
                    "instrument_type": {
                        "type": ["string", "null"],
                        "description": ("Canonical: 'Deed of Absolute Sale', 'Deed of Donation', "
                                        "'Special Power of Attorney', 'Title (TCT/OCT)', etc.")
                    },
                    "source_excerpt": {
                        "type": "string",
                        "description": ("Verbatim excerpt from the document text (50-200 chars) "
                                        "showing where this transaction was found. "
                                        "MUST be a literal substring; do not paraphrase.")
                    }
                },
                "required": ["source_excerpt"]
            }
        }
    },
    "required": ["transactions"]
}


SYSTEM_PROMPT = """You are a Torrens-Title Auditor for the Philippine Land Registration Authority.
Your job is to extract every title-transaction reference from the document text below.

FOUNDATIONAL TRUNK AXIOM (load-bearing — apply during normalization):
  OCT T-106 (1934) is the foundational original certificate.
  T-111 is the next link.
  T-4493 follows T-111.
  These three titles form the mother trunk of the MWK-001 estate chain.
  Composite-form references like '1-106', 'F-106', 'OCT 106' all refer to OCT T-106.
  Plain bare-number references like '4493' refer to T-4493.

EXTRACTION RULES (strict):
  - For each transaction reference found, fill the schema fields you can verify
    from the text. Set unknown fields to null.
  - The source_excerpt field is REQUIRED for every transaction — quote the
    literal text where you found the transaction. This is the audit trail.
  - DO NOT invent transactions. If the document is a tax declaration or
    receipt with no title-transfer content, return empty transactions array.
  - DO NOT include transactions that are only referenced abstractly (e.g.,
    'all transfers in the chain') — only concrete instances with at least
    a date OR a buyer OR a lot identifier.
  - Reject phantom title strings: T-YYYY (year-pattern), T-NNN-NN (tax PIN
    format like T-025-07). These are NEVER real titles.
  - DO NOT output any conversational text. Use the tool 'submit_lineage'.

You MUST use the tool 'submit_lineage' to return your answer."""


USER_TEMPLATE = """DOCUMENT METADATA:
  doc_id: {doc_id}
  filename: {filename}
  classification: {classification}
  date_norm: {doc_date}

DOCUMENT TEXT (truncated to first 8000 chars + last 4000 chars):

{text}

Extract every title-transaction reference per the schema."""


def truncate_text(text, head=8000, tail=4000):
    if not text:
        return ""
    if len(text) <= head + tail:
        return text
    return text[:head] + "\n\n... [middle truncated] ...\n\n" + text[-tail:]


def fetch_candidates(cur, case_file, limit=None, force_id=None):
    where_extra = "AND d.id = %s" if force_id else ""
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    params = [case_file]
    if force_id:
        params.append(force_id)
    cur.execute(f"""
        SELECT d.id, d.classification, d.smart_filename, d.original_filename,
               d.doc_date_norm, d.extracted_text
          FROM documents d
         WHERE d.case_file = %s
           AND d.related_to_doc_id IS NULL                         -- canonical only
           AND length(coalesce(d.extracted_text,'')) >= 500
           AND NOT EXISTS (
               SELECT 1 FROM llm_extracted_lineage l
                WHERE l.source_doc_id = d.id
           )
           AND (
             d.classification ~* 'deed|sale|title|transfer|annotation|certificate|donation|attorney|affidavit|petition|government|submission|complaint|notice|order|memorandum|contract'
             OR d.classification IS NULL
           )
           {where_extra}
         ORDER BY d.id
         {limit_clause}
    """, params)
    return cur.fetchall()


def extract_one(client, doc):
    """Call Sonnet 4.6 with tool-call. Returns list of transaction dicts."""
    from llm_billing import anthropic_tool_call
    text = truncate_text(doc.get("extracted_text") or "")
    user_msg = USER_TEMPLATE.format(
        doc_id=doc["id"],
        filename=(doc.get("smart_filename") or doc.get("original_filename") or "(no filename)"),
        classification=(doc.get("classification") or "(unclassified)"),
        doc_date=(doc.get("doc_date_norm") or "(unknown)"),
        text=text,
    )
    try:
        result = anthropic_tool_call(
            client,
            tool_name="submit_lineage",
            tool_description="Submit the array of title-transaction references found.",
            input_schema=TOOL_SCHEMA,
            called_from="llm_title_extractor",
            purpose="forensic_lineage_extraction",
            case_file="MWK-001",
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return result.get("transactions", [])
    except Exception as e:
        print(f"    ✗ doc#{doc['id']}: {str(e)[:120]}")
        return None


def persist(cur, doc, transactions):
    """Insert one row per transaction. If transactions is empty, insert a
    sentinel row (all-null fields) so the doc is marked as scanned."""
    fname = doc.get("smart_filename") or doc.get("original_filename") or ""
    if not transactions:
        cur.execute("""
            INSERT INTO llm_extracted_lineage
              (source_doc_id, source_doc_name, source_excerpt, provenance_level)
            VALUES (%s, %s, '(no transactions found)', 'llm_sonnet_4_6_extracted_empty')
        """, (doc["id"], fname))
        return 0
    for t in transactions:
        cur.execute("""
            INSERT INTO llm_extracted_lineage
              (parent_title, derivative_title, transaction_date,
               buyer_transferee, seller_transferor, lot_number_and_plan,
               area_sqm, consideration_price, instrument_type,
               source_doc_id, source_doc_name, source_excerpt)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (t.get("parent_title"), t.get("derivative_title"),
              t.get("transaction_date"), t.get("buyer_transferee"),
              t.get("seller_transferor"), t.get("lot_number_and_plan"),
              t.get("area_sqm"), t.get("consideration_price"),
              t.get("instrument_type"),
              doc["id"], fname, t.get("source_excerpt")))
    return len(transactions)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--doc", type=int, help="Process only this single doc ID (for pilot)")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    candidates = fetch_candidates(cur, args.case, args.limit, args.doc)
    print(f"Eligible docs: {len(candidates)}")

    import anthropic
    from landtek_core import get
    api_key = get("ANTHROPIC_API_KEY")
    if not api_key:
        for l in open("/root/landtek/.env"):
            if l.startswith("ANTHROPIC_API_KEY="):
                api_key = l.split("=", 1)[1].strip(); break
    client = anthropic.Anthropic(api_key=api_key)

    total_extracted = 0
    docs_with_transactions = 0
    docs_empty = 0
    start = time.time()
    for i, doc in enumerate(candidates, 1):
        transactions = extract_one(client, doc)
        if transactions is None:
            continue
        n = persist(cur, doc, transactions)
        total_extracted += n
        if n > 0:
            docs_with_transactions += 1
        else:
            docs_empty += 1
        if i % 10 == 0 or i == len(candidates):
            elapsed = time.time() - start
            rate = i / elapsed * 60 if elapsed else 0
            print(f"  [{i}/{len(candidates)}] {total_extracted} txns extracted, "
                  f"{docs_with_transactions} docs hit, {docs_empty} empty · "
                  f"{rate:.0f} docs/min")

    print(f"\n=== Extraction complete ===")
    print(f"  Docs processed:           {len(candidates)}")
    print(f"  Docs with transactions:   {docs_with_transactions}")
    print(f"  Docs with no txns found:  {docs_empty}")
    print(f"  Total transactions saved: {total_extracted}")


if __name__ == "__main__":
    main()
