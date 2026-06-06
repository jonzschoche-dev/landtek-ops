#!/usr/bin/env python3
"""retag_matter_codes — Layer B' refinement (deploy_158).

The Layer B backfill (deploy_155) populated client_history.matter_codes via
a non-deterministic case_file→matter JOIN; consequence: most MWK events show
[PAR-CRIM9221] regardless of true scope. This rule-based retagger uses
strong identifiers (docket numbers, ARTA SL codes, TCT scope, keywords)
to build multi-attribution per event.

No LLM cost — pure regex/keyword over a text blob combining what_summary,
doc filename, classification, text snippet, and instrument context.
"""
import argparse
import re
import sys
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Per-matter resolver patterns: list of (regex_pattern, case_insensitive)
# An event matches a matter if ANY of its patterns hit the event's text blob.
MATTER_PATTERNS = {
    "MWK-ARTA-0690":   [r"SL-2025-1008-0690", r"\b0690\b"],
    "MWK-ARTA-0747":   [r"SL-2025-1021-0747", r"\b0747\b"],
    "MWK-ARTA-0792":   [r"SL-2025-1104-0792", r"\b0792\b"],
    "MWK-ARTA-1210":   [r"SL-2026-0128-1210", r"\b1210\b.*OP\s+Bagong\s+Pilipinas",
                        r"Office of the President.*Bagong\s+Pilipinas"],
    "MWK-ARTA-1319":   [r"SL-2026-0209-1319", r"\b1319\b", r"Nestor\s+Franz", r"CART\s+Southern\s+Luzon"],
    "MWK-ARTA-1321":   [r"SL-2026-0209-1321", r"\b1321\b"],
    "MWK-ARTA-1378":   [r"SL-2026-0218-1378", r"\b1378\b", r"Mun\.?\s+Engineer\s+Mercedes"],
    "MWK-ARTA-1891":   [r"SL-2026-0423-1891", r"\b1891\b", r"NOR-CTN.*1891"],
    "MWK-ARTA-DILG":   [r"DILG.*referral", r"referral.*DILG", r"NOR-CTN"],
    "MWK-CV26360":     [r"CV-?\s*2026-?\s*360", r"\b26-?\s*360\b", r"Civil\s+Case\s+(No\.?\s+)?26-?360",
                        r"Accion\s+Reinvindicatoria", r"\bGloria\s+Balane\b",
                        r"Balane(?!\s+Heirs)", r"RTC\s+Branch\s+64"],
    "MWK-CV6839":      [r"Civil\s+Case\s+(No\.?\s+)?6839", r"CV-?\s*6839",
                        r"just\s+compensation", r"\bLand\s*[Bb]ank\b.*(MWK|Mary\s+Worrick|Keesey)",
                        r"DAR.*Land\s*[Bb]ank.*MWK", r"agrarian.*just\s+compensation"],
    "MWK-PARALLEL-CRIM9221": [r"Crim(\.|inal)?\s+Case\s+(No\.?\s+)?9221", r"\b9221\b",
                              r"People\s+vs\.?\s+(Eduardo\s+)?Ibana", r"Eduardo\s+Ibana"],
    "MWK-PARALLEL-CV6922":   [r"Civil\s+Case\s+(No\.?\s+)?6922", r"CV-?\s*6922",
                              r"Amado\s+V\.?\s+Pajarillo", r"Pajarillo\s+vs\.?\s+DAR"],
    "MWK-TCT4497":     [],  # populated dynamically: matches if T-4497 is the PRIMARY title
    "MWK-ESTATE":      [],  # catch-all
}

# Known TCT chain members of T-4497 (per CLAUDE.md). Events touching ONLY these
# titles (and not naming a court/agency) get tagged to TCT4497 + CV26360.
T4497_CHAIN = {
    "T-4497", "T-32916", "T-32917", "T-31298",
    "T-38838", "T-47655", "T-47656", "T-47657",
    "T-48335", "T-48336", "T-49037", "T-49060", "T-49061", "T-49062",
    "T-52354", "T-52536", "T-52537", "T-52538", "T-52539", "T-52540",
    "T-079-2021002126", "T-079-2021002127",
}


def build_event_blob(event):
    """Combine every text field that could carry a matter signal."""
    parts = []
    for k in ("what_summary", "citation_ref", "event_kind",
              "doc_classification", "doc_smart_filename", "doc_original_filename",
              "doc_title", "doc_text_snippet",
              "tx_category", "tx_counterparty", "tx_description",
              "gmail_subject", "gmail_from", "gmail_from_name", "gmail_body_snippet",
              "cal_title", "cal_description",
              "tt_instrument_type", "tt_parent_title", "tt_derivative_title",
              "tt_transferor", "tt_transferee_name"):
        v = event.get(k)
        if v:
            parts.append(str(v))
    return " | ".join(parts)


def resolve_event(event_blob, title_refs):
    """Return sorted list of matter_codes this event pertains to."""
    matched = set()

    # 1. Pattern-match against all matters with explicit regexes
    for mc, patterns in MATTER_PATTERNS.items():
        if not patterns:
            continue
        for p in patterns:
            if re.search(p, event_blob, re.IGNORECASE):
                matched.add(mc)
                break

    # 2. TCT chain → CV26360 + TCT4497 (these matters overlap by design)
    if title_refs:
        if any(t in T4497_CHAIN for t in title_refs):
            matched.add("MWK-CV26360")
            matched.add("MWK-TCT4497")

    # 3. If still no match, fall back to MWK-ESTATE (estate admin / unclassifiable)
    if not matched:
        matched.add("MWK-ESTATE")

    return sorted(matched)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Pull all events for this case_file with the enriched fields needed for resolution
    cur.execute("""
        SELECT
          h.id, h.matter_codes AS old_matter_codes, h.title_refs,
          h.what_summary, h.citation_ref, h.event_kind,
          h.source_table, h.source_id,
          d.classification AS doc_classification, d.smart_filename AS doc_smart_filename,
          d.original_filename AS doc_original_filename, d.document_title AS doc_title,
          LEFT(d.extracted_text, 800) AS doc_text_snippet,
          t.category AS tx_category, t.counterparty AS tx_counterparty, t.description AS tx_description,
          g.subject AS gmail_subject, g.from_addr AS gmail_from, g.from_name AS gmail_from_name,
          LEFT(g.body_plain, 400) AS gmail_body_snippet,
          ce.title AS cal_title, ce.description AS cal_description,
          tt.instrument_type AS tt_instrument_type, tt.parent_title AS tt_parent_title,
          tt.derivative_title AS tt_derivative_title, tt.transferor AS tt_transferor,
          tt.transferee_name AS tt_transferee_name
        FROM client_history h
        LEFT JOIN documents d ON h.source_table='documents' AND h.source_id=d.id::text
        LEFT JOIN transactions t ON h.source_table='transactions' AND h.source_id=t.id::text
        LEFT JOIN gmail_messages g ON h.source_table='gmail_messages' AND h.source_id=g.id::text
        LEFT JOIN calendar_events ce ON h.source_table='calendar_events' AND h.source_id=ce.id::text
        LEFT JOIN title_transfers tt ON h.source_table='title_transfers' AND h.source_id=tt.id::text
        WHERE h.case_file = %s
    """, (args.case,))
    events = cur.fetchall()
    print(f"Retagging {len(events)} events for case_file={args.case}")

    distribution = {}
    changes = []
    for e in events:
        blob = build_event_blob(e)
        new_codes = resolve_event(blob, e["title_refs"] or [])
        old_codes = e["old_matter_codes"] or []
        # Detect changes (set comparison)
        if set(new_codes) != set(old_codes):
            changes.append((e["id"], old_codes, new_codes))
        for c in new_codes:
            distribution[c] = distribution.get(c, 0) + 1

    print(f"\nMatter distribution after retag:")
    for mc, n in sorted(distribution.items(), key=lambda x: -x[1]):
        print(f"  {mc:25s}: {n} events")
    print(f"\nChanges: {len(changes)} events would be retagged")

    # Show a few examples
    print("\nSample changes:")
    for eid, old, new in changes[:8]:
        print(f"  event#{eid}: {old} → {new}")

    if args.dry_run:
        print("\n(dry-run — no DB writes)")
        return

    # Apply updates
    print("\nApplying...")
    for e in events:
        blob = build_event_blob(e)
        new_codes = resolve_event(blob, e["title_refs"] or [])
        cur.execute("""
            UPDATE client_history SET matter_codes = %s WHERE id = %s
        """, (new_codes, e["id"]))
    print(f"✅ Retagged {len(events)} events.")


if __name__ == "__main__":
    main()
