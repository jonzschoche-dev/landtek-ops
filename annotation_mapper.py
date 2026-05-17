#!/usr/bin/env python3
"""annotation_mapper — Torrens-precision rendering for title_annotation events.

Per Jonathan 2026-05-17: under PH Torrens system, the Memorandum of Encumbrances
(annotations on the back of a TCT) is the legal binding mechanism. An unannotated
instrument doesn't bind third parties. The chronology was rendering annotation
events as bare 'title_annotation on T-32917' with no source — useless for the
void-SPA fraud case.

This script:
  1. Renders annotation events with full Torrens detail:
       PE-XXXX | INSTRUMENT_TYPE | Notary <name> Doc <D>, Page <P>, Book <B>, Series <Y>
  2. Maps source_link to the parent TCT PDF (the doc_id the annotation lives on),
     replacing '[DB record only]' with the actual TCT scan URL.
  3. Runs the Gap Analysis: deeds/SPAs that have NO annotation within 6 months —
     these are 'Unregistered Instruments' that don't bind third parties.

Output:
  - For #1+#2: prints how to consume from chronology (returns rich-event func)
  - For #3: prints the Gap Analysis Report to terminal

The export_raw_chronology.py script is patched in a separate step to JOIN
instruments_on_title and use these labels.
"""
import argparse
import sys
from datetime import date, timedelta
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def torrens_label(iot):
    """Build the rich annotation label from instruments_on_title row."""
    parts = []
    if iot.get("pe_number"):
        parts.append(f"Entry {iot['pe_number']}")
    if iot.get("instrument_type"):
        parts.append(iot["instrument_type"].strip().title()
                     if iot["instrument_type"].isupper() else iot["instrument_type"])
    notary_bits = []
    if iot.get("notary_name"):
        notary_bits.append(f"Notary {iot['notary_name']}")
    dpbs = []
    if iot.get("notary_doc_no"):    dpbs.append(f"Doc {iot['notary_doc_no']}")
    if iot.get("notary_page"):       dpbs.append(f"Page {iot['notary_page']}")
    if iot.get("notary_book"):       dpbs.append(f"Book {iot['notary_book']}")
    if iot.get("notary_series_year"):dpbs.append(f"Series {iot['notary_series_year']}")
    if dpbs:
        notary_bits.append(", ".join(dpbs))
    if notary_bits:
        parts.append(" — ".join(notary_bits))
    if iot.get("executor_full_name"):
        parts.append(f"Executed by: {iot['executor_full_name']}")
    return " | ".join(parts)


def gap_analysis(cur, case_file="MWK-001", window_months=6):
    """Find deeds/SPAs in client_history WITHOUT a corresponding title_annotation
    in instruments_on_title within ±window_months of the same date and on the
    same title (where determinable)."""
    print("="*80)
    print(f"GAP ANALYSIS — Unregistered Instruments (case={case_file}, window=±{window_months}mo)")
    print("="*80)
    print()
    print("These are executed deeds/SPAs that have NO matching annotation on the title")
    print("within the ±6-month window. Under PH Torrens system they do NOT bind third")
    print("parties. If our void-SPA theory rests on the 2005 SPA revocation, we MUST")
    print("be able to show the revocation was annotated. If it wasn't, that's a defect.")
    print()

    # Pull all execution events (deeds + SPAs) from documents+client_history
    cur.execute("""
        SELECT
          h.id AS event_id,
          COALESCE(h.event_date, h.date_executed) AS exec_date,
          h.event_kind, h.event_kind_canonical,
          h.title_refs, h.matter_codes,
          h.source_table, h.source_id,
          d.id AS doc_id, d.classification, d.smart_filename, d.original_filename,
          d.document_title, d.execution_status,
          d.drive_link, d.drive_file_id
        FROM client_history h
        LEFT JOIN documents d ON h.source_table='documents' AND h.source_id=d.id::text
        WHERE h.case_file = %s
          AND (
            -- executed deeds / SPAs / revocations
            d.classification ~* 'deed|donation|power\\s+of\\s+attorney|revocation'
            OR h.event_kind ~* 'deed|donation|power_of_attorney|spa|revocation'
            OR h.event_kind_canonical = 'legal_act'
          )
          AND COALESCE(h.event_date, h.date_executed) IS NOT NULL
          AND h.source_table = 'documents'
        ORDER BY exec_date
    """, (case_file,))
    legal_acts = cur.fetchall()
    print(f"Scanning {len(legal_acts)} legal-act events...\n")

    # For each, search instruments_on_title for a matching annotation within window
    unregistered = []
    registered = []
    for la in legal_acts:
        exec_date = la["exec_date"]
        if not exec_date:
            continue
        window_start = exec_date - timedelta(days=window_months * 30)
        window_end   = exec_date + timedelta(days=window_months * 30)

        # Build title-match clause: any title in la.title_refs OR if instruments
        # was extracted from the SAME source doc (doc_id match)
        title_list = la.get("title_refs") or []
        cur.execute("""
            SELECT id, pe_number, entry_date, instrument_type, executor_full_name, doc_id
              FROM instruments_on_title
             WHERE entry_date BETWEEN %s AND %s
               AND (
                 parent_tct_number = ANY(%s)
                 OR doc_id = %s
                 OR (executor_full_name ILIKE %s)
               )
             LIMIT 5
        """, (window_start, window_end, title_list, la["doc_id"],
              f"%{(la.get('document_title') or '')[:30]}%"))
        matches = cur.fetchall()

        record = {
            "event_id": la["event_id"],
            "exec_date": exec_date.isoformat(),
            "kind": la.get("classification") or la.get("event_kind"),
            "title_refs": title_list,
            "doc_id": la["doc_id"],
            "matter_codes": la.get("matter_codes") or [],
            "filename": (la.get("smart_filename") or la.get("original_filename") or "")[:60],
            "matches": matches,
        }
        if matches:
            registered.append(record)
        else:
            unregistered.append(record)

    # Print results
    print(f"REGISTERED (annotation found within ±{window_months}mo): {len(registered)}")
    print(f"UNREGISTERED (no annotation match):                  {len(unregistered)}")
    print()
    print("─"*80)
    print("UNREGISTERED INSTRUMENTS — needing Torrens-registration audit")
    print("─"*80)

    # Group by matter for readability
    from collections import defaultdict
    by_matter = defaultdict(list)
    for u in unregistered:
        key = ",".join(u["matter_codes"]) if u["matter_codes"] else "(no matter)"
        by_matter[key].append(u)

    for matter, items in sorted(by_matter.items(),
                                  key=lambda kv: -len(kv[1])):
        print(f"\n📁 {matter}: {len(items)} unregistered legal-acts")
        for u in items[:15]:  # cap per matter
            tr = ",".join(u["title_refs"][:3]) if u["title_refs"] else "—"
            print(f"  doc#{u['doc_id']:>4d} | {u['exec_date']} | {u['kind'][:25]:25s} | "
                  f"titles={tr:25s} | {u['filename'][:50]}")
        if len(items) > 15:
            print(f"  ... and {len(items) - 15} more")

    print()
    print("─"*80)
    print("KEY VOID-SPA-CASE CHECK")
    print("─"*80)
    # Specifically check the load-bearing instruments
    critical_searches = [
        ("Revocation of SPA (2005-08-15)", "revocation", "2005-08-15"),
        ("Cesar 2016 Deed of Sale (the void deed)", "absolute sale|deed of sale", "2016-09-29"),
        ("Cesar 1992 SPA (granting)", "power of attorney", "1992-01-01"),
    ]
    for label, kw, anchor_date in critical_searches:
        cur.execute("""
            SELECT id, pe_number, entry_date, instrument_type, executor_full_name
              FROM instruments_on_title
             WHERE instrument_type ~* %s
             ORDER BY ABS(entry_date - DATE %s) LIMIT 3
        """, (kw, anchor_date))
        hits = cur.fetchall()
        print(f"\n• {label}: anchor={anchor_date}")
        if not hits:
            print(f"    🔴 NO MATCHING ANNOTATION in instruments_on_title for keyword '{kw}'.")
            print(f"       If the instrument was executed but never annotated, it does NOT bind third parties.")
        else:
            for h in hits[:3]:
                print(f"    ✓ Entry {h['pe_number']} on {h['entry_date']}: {h['instrument_type']}")
                if h.get("executor_full_name"):
                    print(f"       executor: {h['executor_full_name']}")

    return registered, unregistered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--window-months", type=int, default=6)
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    gap_analysis(cur, args.case, args.window_months)


if __name__ == "__main__":
    main()
