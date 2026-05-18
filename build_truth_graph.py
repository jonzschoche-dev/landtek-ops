#!/usr/bin/env python3
"""build_truth_graph — Sonnet 4.6 semantic-triple extraction (GraphRAG layer).

Per Jonathan 2026-05-18: move from flat lineage records to a relational
graph where every fact is (subject) -> [predicate] -> (object) + attributes.
Enables queries like "every triple where Roscoe Leaño appears" → pulls the
full structural web around a name instead of keyword-searching messy OCR.

Pipeline:
  1. Read canonical MWK-001 docs with substantive text.
  2. Sonnet 4.6 + strict tool-call extracts triples per a canonical
     predicate vocabulary. No prose.
  3. Each triple → one row in knowledge_graph_triples with attributes JSONB
     for flexible secondary facts (lot, area, date, notes, etc.).

Canonical predicate vocabulary (the schema enforces these):
  IS_MOTHER_OF / IS_DERIVATIVE_OF       — title parent-child
  SOLD_TO / SOLD_PORTION_TO             — conveyances
  DONATED_TO                            — donations
  AUTHORIZED_BY                         — SPA grant
  REVOKED_BY                            — SPA revocation
  DIED                                  — death
  ANNOTATED_ON                          — instrument recorded on title
  NOT_ANNOTATED_ON / ACQUIRED_UNANNOTATED — un-recorded acquisitions
  LOCATED_IN                            — geographical
  EXECUTED_BY                           — instrument-execution
  CANCELLED_BY                          — title cancellation
  REPRESENTED_BY                        — attorney-in-fact / counsel
  PART_OF_CHAIN_FROM                    — foundational trunk
  CONTESTED_IN                          — adverse claim
"""
import argparse
import json
import sys
import time
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

CANONICAL_PREDICATES = [
    "IS_MOTHER_OF", "IS_DERIVATIVE_OF",
    "SOLD_TO", "SOLD_PORTION_TO", "DONATED_TO",
    "AUTHORIZED_BY", "REVOKED_BY",
    "DIED",
    "ANNOTATED_ON", "NOT_ANNOTATED_ON", "ACQUIRED_UNANNOTATED",
    "LOCATED_IN", "EXECUTED_BY", "CANCELLED_BY",
    "REPRESENTED_BY", "PART_OF_CHAIN_FROM", "CONTESTED_IN",
    "FILED_COMPLAINT_AGAINST", "ISSUED_BY", "NOTARIZED_BY",
]

TRIPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "description": "Every explicit legal relationship found in the text as a directed triple.",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": ("The acting entity. Person names verbatim (e.g., "
                                        "'Cesar de la Fuente', 'Roscoe Leaño'). Titles canonical "
                                        "form 'TCT-XXXXX' or 'OCT T-XXX' (e.g., 'TCT-4497').")
                    },
                    "predicate": {
                        "type": "string",
                        "enum": CANONICAL_PREDICATES,
                        "description": ("Relationship verb. Must be one of the canonical "
                                        "predicates. If unsure, do not emit the triple.")
                    },
                    "object": {
                        "type": "string",
                        "description": "Receiving entity. Same naming rules as subject."
                    },
                    "attributes": {
                        "type": "object",
                        "description": ("Flexible JSON of secondary facts: lot, area_sqm, "
                                        "transaction_date (YYYY-MM-DD), consideration_price, "
                                        "instrument_type, subdivision_plan, notes."),
                        "additionalProperties": True
                    },
                    "source_excerpt": {
                        "type": "string",
                        "description": ("VERBATIM excerpt from the document text where this "
                                        "triple was found (50-200 chars). MUST be a literal "
                                        "substring of the input — do not paraphrase.")
                    }
                },
                "required": ["subject", "predicate", "object", "source_excerpt"]
            }
        }
    },
    "required": ["triples"]
}


SYSTEM_PROMPT = """You are a Knowledge-Graph Extractor for the Philippine Torrens land system.
Your job is to read legal-document text and emit every explicit relationship as
a directed triple (subject) -> [predicate] -> (object).

FOUNDATIONAL TRUNK AXIOM (load-bearing):
  OCT T-106 (1934) is the foundational original certificate.
  T-111 follows OCT T-106. T-4493 follows T-111.
  These three form the mother trunk of the MWK-001 estate.
  Composite/typo references ('1-106', 'F-106', 'OCT 106', '7-32917', etc.) normalize
  to their canonical form before being emitted as subject/object.

NAMING NORMALIZATION:
  - Titles: 'TCT-XXXXX' for transfer certificates, 'OCT T-XXX' for originals,
    'T-XXX-NNNNNNNNNN' for long-format 2021-era titles. NEVER 'T-2023' (year)
    or 'T-025-07' (tax PIN) — those are NOT real titles.
  - People: full verbatim names. Don't strip 'Jr.' / 'III' / middle initials.
  - Organizations: official names (e.g., 'Philippine National Police', not 'PNP'
    in the subject — but you may include the acronym in attributes).

PREDICATE DISCIPLINE:
  Use ONLY the canonical predicate enum. If the relationship doesn't fit one,
  skip the triple rather than inventing a new predicate.

EVIDENCE DISCIPLINE:
  Every triple MUST have a source_excerpt that is a VERBATIM substring of the
  input text. This is the audit trail — paraphrasing breaks the citation chain.

ASSERTION DISCIPLINE:
  Only emit triples that are EXPLICIT in the text. If the document says
  'Cesar de la Fuente sold to Roscoe Leaño', emit (Cesar de la Fuente,
  SOLD_TO, Roscoe Leaño). If the document only references a name without
  asserting a relationship, do NOT invent one.

You MUST use the tool 'submit_triples'. No conversational text."""


USER_TEMPLATE = """DOCUMENT:
  doc_id: {doc_id}
  filename: {filename}
  classification: {classification}
  date_norm: {doc_date}

TEXT (first 8000 + last 4000 chars):

{text}

Extract every explicit legal/transactional relationship as a directed triple."""


def truncate_text(text, head=8000, tail=4000):
    if not text: return ""
    if len(text) <= head + tail: return text
    return text[:head] + "\n\n... [middle truncated] ...\n\n" + text[-tail:]


def fetch_candidates(cur, case_file, limit=None, force_id=None):
    where_extra = "AND d.id = %s" if force_id else ""
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    params = [case_file]
    if force_id: params.append(force_id)
    cur.execute(f"""
        SELECT d.id, d.classification, d.smart_filename, d.original_filename,
               d.doc_date_norm, d.extracted_text
          FROM documents d
         WHERE d.case_file = %s
           AND d.related_to_doc_id IS NULL
           AND length(coalesce(d.extracted_text,'')) >= 500
           AND NOT EXISTS (
               SELECT 1 FROM knowledge_graph_triples k
                WHERE k.source_doc_id = d.id
           )
           AND (
             d.classification ~* 'deed|sale|title|transfer|annotation|certificate|donation|attorney|affidavit|petition|government|submission|complaint|notice|order|memorandum|contract|judicial'
             OR d.classification IS NULL
           )
           {where_extra}
         ORDER BY d.id
         {limit_clause}
    """, params)
    return cur.fetchall()


def extract_triples(client, doc):
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
            tool_name="submit_triples",
            tool_description="Submit array of extracted directed-triple relationships.",
            input_schema=TRIPLE_SCHEMA,
            called_from="build_truth_graph",
            purpose="graph_triple_extraction",
            case_file="MWK-001",
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return result.get("triples", [])
    except Exception as e:
        print(f"    ✗ doc#{doc['id']}: {str(e)[:150]}")
        return None


def persist(cur, doc, triples):
    fname = doc.get("smart_filename") or doc.get("original_filename") or ""
    if not triples:
        cur.execute("""
            INSERT INTO knowledge_graph_triples
              (source_doc_id, source_doc_name, subject_entity, relationship_type,
               object_entity, source_excerpt, provenance_level)
            VALUES (%s, %s, '_NONE_', '_NONE_', '_NONE_', '(no triples found)',
                    'llm_sonnet_4_6_triple_empty')
        """, (doc["id"], fname))
        return 0
    n = 0
    for t in triples:
        if not (t.get("subject") and t.get("predicate") and t.get("object")):
            continue
        cur.execute("""
            INSERT INTO knowledge_graph_triples
              (source_doc_id, source_doc_name, subject_entity, relationship_type,
               object_entity, attributes_json, source_excerpt)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (doc["id"], fname, t["subject"], t["predicate"], t["object"],
              psycopg2.extras.Json(t.get("attributes") or {}),
              t.get("source_excerpt")))
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--doc", type=int)
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

    total = 0; docs_hit = 0; docs_empty = 0
    start = time.time()
    for i, doc in enumerate(candidates, 1):
        triples = extract_triples(client, doc)
        if triples is None: continue
        n = persist(cur, doc, triples)
        total += n
        docs_hit += (1 if n > 0 else 0)
        docs_empty += (1 if n == 0 else 0)
        if i % 5 == 0 or i == len(candidates):
            elapsed = time.time() - start
            rate = i / elapsed * 60 if elapsed else 0
            print(f"  [{i}/{len(candidates)}] {total} triples extracted, "
                  f"{docs_hit} docs hit, {docs_empty} empty · {rate:.0f} docs/min")

    print(f"\n=== Graph build complete ===")
    print(f"  Docs processed:           {len(candidates)}")
    print(f"  Docs with triples:        {docs_hit}")
    print(f"  Docs with no triples:     {docs_empty}")
    print(f"  Total triples saved:      {total}")


if __name__ == "__main__":
    main()
