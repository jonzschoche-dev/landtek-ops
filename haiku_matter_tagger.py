#!/usr/bin/env python3
"""haiku_matter_tagger — Haiku second-pass on MWK-ESTATE catch-all events (deploy_159).

After the rule-based retagger (deploy_158) routes 627 events to MWK-ESTATE
as a catch-all, this script asks Haiku to read the enriched event payload
and route each one to its TRUE matter(s) where DB signals support it.

Strict design (no hallucination):
  - Tool-call schema enforces output is a JSON list of matter codes drawn
    from a fixed enum (the 15 real MWK matters). Haiku cannot invent a code.
  - Default fallback is ['MWK-ESTATE'] — the prompt explicitly says
    "DO NOT GUESS — return ESTATE if no clear signal."
  - Multi-attribution allowed: a doc that pertains to CV-26360 AND TCT-4497
    chain verification can map to both.

Cost: ~$0.40-0.50 for the 627-event pass.
"""
import argparse
import json
import sys
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# All 15 valid MWK matters — used as the enum for the tool-call schema
MWK_MATTERS = [
    "MWK-ARTA-0690", "MWK-ARTA-0747", "MWK-ARTA-0792", "MWK-ARTA-1210",
    "MWK-ARTA-1319", "MWK-ARTA-1321", "MWK-ARTA-1378", "MWK-ARTA-1891",
    "MWK-ARTA-DILG",
    "MWK-CV26360", "MWK-CV6839",
    "MWK-ESTATE",
    "MWK-PARALLEL-CRIM9221", "MWK-PARALLEL-CV6922",
    "MWK-TCT4497",
]

MATTER_DEFINITIONS = """
The 15 MWK matters under the Heirs of Mary Worrick Keesey estate:

  MWK-ARTA-0690   — ARTA SL-2025-1008-0690 records-request complaint (RESOLVED)
  MWK-ARTA-0747   — ARTA SL-2025-1021-0747 vs Mayor Pajarillo (RA 11032)
  MWK-ARTA-0792   — ARTA SL-2025-1104-0792 (bundled with -0690, RESOLVED)
  MWK-ARTA-1210   — ARTA SL-2026-0128-1210 (OP Bagong Pilipinas)
  MWK-ARTA-1319   — ARTA SL-2026-0209-1319 (CART Southern Luzon, vs Nestor Franz)
  MWK-ARTA-1321   — ARTA SL-2026-0209-1321 (Heirs MWK RA 11032)
  MWK-ARTA-1378   — ARTA SL-2026-0218-1378 (Mun. Engineer Mercedes RA 11032)
  MWK-ARTA-1891   — ARTA SL-2026-0423-1891 (referred to CSC/DILG)
  MWK-ARTA-DILG   — ARTA referral to DILG
  MWK-CV26360     — Accion Reinvindicatoria, Zschoche v. Balane (RTC Br 64).
                    Subject: TCT T-079-2021002126 (Balane) descended from
                    void 2016 Deed of Sale by Cesar dela Fuente under
                    revoked SPA. Mother title T-4497 and its derivatives.
  MWK-CV6839      — Civil Case 6839 vs Landbank, just compensation,
                    HALTED pending substitution (rep. by Cesar dela Fuente
                    who died 2017).
  MWK-ESTATE      — General estate administration with no specific case
                    pending; tax declarations, RPT payments, general
                    registry maintenance.
  MWK-PARALLEL-CRIM9221 — Crim Case 9221, People vs Eduardo IBANA.
                    Parallel proceeding, relationship to MWK estate unclear.
  MWK-PARALLEL-CV6922   — Civil Case 6922, Heirs of Pajarillo vs DAR.
                    Parallel proceeding, relationship to MWK estate unclear.
  MWK-TCT4497     — TCT T-4497 chain-verification matter. Pure title
                    research / chain-of-title work. Often overlaps with
                    CV-26360 since that case turns on the T-4497 chain.
"""

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "matter_codes": {
            "type": "array",
            "items": {"type": "string", "enum": MWK_MATTERS},
            "description": ("Matter codes this event pertains to. MUST be drawn from the "
                            "provided enum. Return ['MWK-ESTATE'] if no clear DB signal "
                            "supports a more specific matter. DO NOT GUESS.")
        },
        "reasoning": {
            "type": "string",
            "description": "One short sentence citing the specific signal (docket, TCT, party, ARTA SL code) that drove the classification."
        }
    },
    "required": ["matter_codes", "reasoning"]
}


def build_event_blob(e):
    """Build the substantive blob Haiku will read."""
    bits = []
    if e.get("primary_date"): bits.append(f"Date: {e['primary_date']}")
    if e.get("event_kind"): bits.append(f"Kind: {e['event_kind']}")
    if e.get("title_refs"): bits.append(f"TCT refs: {', '.join(e['title_refs'])}")
    if e.get("what_summary"): bits.append(f"Summary: {e['what_summary'][:200]}")
    if e.get("doc_classification"): bits.append(f"Classification: {e['doc_classification']}")
    if e.get("doc_smart_filename"): bits.append(f"Filename: {e['doc_smart_filename'][:120]}")
    if e.get("doc_title"): bits.append(f"Title: {e['doc_title'][:120]}")
    if e.get("doc_text_snippet"):
        t = e["doc_text_snippet"].strip()[:600].replace("\n", " ")
        if sum(c.isalpha() for c in t)/max(len(t),1) > 0.4:
            bits.append(f"Text: {t}")
    if e.get("tx_amount") is not None:
        bits.append(f"Transaction: P{float(e['tx_amount']):,.0f} {e.get('tx_direction','?')} "
                     f"{e.get('tx_category','')} cp={e.get('tx_counterparty','?')}")
    if e.get("gmail_subject"):
        bits.append(f"Email subject: {e['gmail_subject'][:200]}")
    if e.get("gmail_from"):
        bits.append(f"From: {e.get('gmail_from_name') or e['gmail_from']}")
    if e.get("tt_instrument_type"):
        bits.append(f"Transfer: {e['tt_instrument_type']} {e.get('tt_parent_title','?')}"
                     f"→{e.get('tt_derivative_title','?')} "
                     f"({e.get('tt_transferor','?')}→{e.get('tt_transferee_name','?')})")
    return "\n".join(bits)


def tag_event(client, e):
    """Call Haiku for one event, return (matter_codes, reasoning)."""
    from llm_billing import anthropic_tool_call
    blob = build_event_blob(e)
    user_msg = (
        f"You are tagging a single event in the Master Case Bible for the Heirs of Mary "
        f"Worrick Keesey (MWK-001).\n\n"
        f"{MATTER_DEFINITIONS}\n\n"
        f"CRITICAL RULES:\n"
        f"  - You MUST use the tool 'tag_matter' to return your answer.\n"
        f"  - matter_codes MUST be a non-empty array drawn from the enum.\n"
        f"  - If the event has no clear textual or relational signal pointing to a specific "
        f"matter, return ['MWK-ESTATE']. DO NOT GUESS.\n"
        f"  - Multi-attribution is allowed when an event genuinely spans multiple matters.\n"
        f"  - Common patterns:\n"
        f"      * Pure tax declarations / RPT receipts with no case context → ['MWK-ESTATE']\n"
        f"      * Documents referencing T-4497 chain titles → likely ['MWK-CV26360','MWK-TCT4497']\n"
        f"      * Documents referencing 'Landbank' + 'just compensation' or 'DAR' → ['MWK-CV6839']\n"
        f"      * Documents naming Gloria Balane or Accion Reinvindicatoria → ['MWK-CV26360']\n"
        f"      * Documents naming Ibana or Crim 9221 → ['MWK-PARALLEL-CRIM9221']\n"
        f"      * Documents naming Pajarillo or CV 6922 → ['MWK-PARALLEL-CV6922']\n\n"
        f"EVENT TO TAG:\n{blob}\n"
    )
    return anthropic_tool_call(
        client,
        tool_name="tag_matter",
        tool_description="Submit the matter codes this event pertains to.",
        input_schema=TOOL_SCHEMA,
        called_from="haiku_matter_tagger",
        purpose="event_matter_classification",
        case_file="MWK-001",
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system="You are a senior paralegal. Tag events to matters strictly by DB signal. No guessing.",
        messages=[{"role": "user", "content": user_msg}],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import anthropic
    from landtek_core import get
    api_key = get("ANTHROPIC_API_KEY")
    if not api_key:
        for l in open("/root/landtek/.env"):
            if l.startswith("ANTHROPIC_API_KEY="):
                api_key = l.split("=", 1)[1].strip(); break
    client = anthropic.Anthropic(api_key=api_key)

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Pull only events currently routed to MWK-ESTATE as the SOLE matter
    # (don't touch events that already have specific assignments)
    limit_clause = f"LIMIT {int(args.limit)}" if args.limit else ""
    cur.execute(f"""
        SELECT
          h.id, h.matter_codes, h.title_refs,
          COALESCE(h.event_date, h.date_executed, h.date_filed, h.date_received) AS primary_date,
          h.event_kind, h.what_summary, h.citation_ref,
          h.source_table, h.source_id,
          d.classification AS doc_classification, d.smart_filename AS doc_smart_filename,
          d.original_filename AS doc_original_filename, d.document_title AS doc_title,
          LEFT(d.extracted_text, 800) AS doc_text_snippet,
          t.amount AS tx_amount, t.direction AS tx_direction,
          t.category AS tx_category, t.counterparty AS tx_counterparty,
          g.subject AS gmail_subject, g.from_addr AS gmail_from, g.from_name AS gmail_from_name,
          tt.instrument_type AS tt_instrument_type, tt.parent_title AS tt_parent_title,
          tt.derivative_title AS tt_derivative_title, tt.transferor AS tt_transferor,
          tt.transferee_name AS tt_transferee_name
        FROM client_history h
        LEFT JOIN documents d ON h.source_table='documents' AND h.source_id=d.id::text
        LEFT JOIN transactions t ON h.source_table='transactions' AND h.source_id=t.id::text
        LEFT JOIN gmail_messages g ON h.source_table='gmail_messages' AND h.source_id=g.id::text
        LEFT JOIN title_transfers tt ON h.source_table='title_transfers' AND h.source_id=tt.id::text
        WHERE h.case_file = 'MWK-001'
          AND h.matter_codes = ARRAY['MWK-ESTATE']::text[]
        ORDER BY h.id
        {limit_clause}
    """)
    events = cur.fetchall()
    print(f"Tagging {len(events)} MWK-ESTATE catch-all events with Haiku")

    promoted = kept = 0
    promotion_dist = {}
    for i, e in enumerate(events, 1):
        try:
            result = tag_event(client, e)
            new_codes = result.get("matter_codes", ["MWK-ESTATE"])
            reasoning = result.get("reasoning", "")
            if set(new_codes) != {"MWK-ESTATE"}:
                promoted += 1
                for c in new_codes:
                    promotion_dist[c] = promotion_dist.get(c, 0) + 1
                if not args.dry_run:
                    cur.execute("UPDATE client_history SET matter_codes = %s WHERE id = %s",
                                 (new_codes, e["id"]))
            else:
                kept += 1
            if i % 25 == 0:
                print(f"  {i}/{len(events)}: promoted={promoted}, kept_estate={kept}")
        except Exception as err:
            print(f"  event#{e['id']}: error {str(err)[:120]}")
            kept += 1

    print(f"\n=== Haiku tagger complete ===")
    print(f"  Total processed: {len(events)}")
    print(f"  Promoted (more specific matter assigned): {promoted}")
    print(f"  Kept as MWK-ESTATE (no clear signal): {kept}")
    if promotion_dist:
        print(f"\n  Promotion distribution:")
        for mc, n in sorted(promotion_dist.items(), key=lambda x: -x[1]):
            print(f"    {mc:25s}: +{n}")


if __name__ == "__main__":
    main()
