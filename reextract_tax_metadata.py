#!/usr/bin/env python3
"""reextract_tax_metadata — populate tax_years/PIN/ARP columns + clean title_refs.

Per Jonathan 2026-05-17: 78 'phantom titles' in title_refs are real tax data
captured by the wrong extractor. This script:

  1. Re-parses every MWK document's filename + document_title + extracted_text
  2. Extracts PINs, ARPs, tax years using format-specific regexes
  3. Populates documents.{tax_years, property_index_numbers, arp_numbers}
  4. Removes the same phantoms from title_refs[] in BOTH documents and
     client_history (where the Layer B migration originally polluted them)
"""
import argparse
import re
import sys
from collections import Counter
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# ── Format-specific regexes ─────────────────────────────────────────────
# PINs: PH Property Index Numbers, multiple LGU formats.
#   Long form: NNN-NN-NNN-NN-NNN (5 segments, region-mun-brgy-section-parcel)
#   Mercedes short form: NNN-NNNNN (e.g., 001-00006, 001-00030)
RE_PIN_LONG  = re.compile(r'\b(\d{3}-\d{2}-\d{3}-\d{2}-\d{3})\b')
RE_PIN_SHORT = re.compile(r'\b(\d{3}-\d{5})\b')

# ARPs: Assessor Reference Numbers, typically GR-YYYY-XX-NN-NNN-NNNNN
RE_ARP = re.compile(r'\b(GR-\d{4}-[A-Z]{2}-\d{2}-\d{3}-\d{5})\b')

# Tax years: 4-digit years in tax-doc context
RE_YEAR_IN_CONTEXT = re.compile(
    r'(?:tax\s+year|RPT|FY|fiscal\s+year|year\s+ending|for\s+the\s+year|'
    r'taxation\s+for|declaration\s+of\s+real\s+property[^\n]{0,30})'
    r'[^\n]{0,40}?\b(19[5-9]\d|20[0-3]\d)\b',
    re.IGNORECASE
)
# Standalone year only when document classification clearly is a tax doc
RE_YEAR_STANDALONE = re.compile(r'\b(19[5-9]\d|20[0-3]\d)\b')


def extract_all(text):
    """Return dict of all extractable tax-metadata sets."""
    if not text:
        return {"pins": [], "arps": [], "years": []}
    t = text[:20000]  # cap to 20K to avoid huge memory on full text
    pins = set(RE_PIN_LONG.findall(t))
    pins.update(RE_PIN_SHORT.findall(t))
    arps = set(RE_ARP.findall(t))
    # Years: prefer context-based extraction; if doc is clearly tax-related
    # (heuristic: contains 'tax declaration' or 'real property tax'), accept
    # standalone years too.
    years = {int(y) for y in RE_YEAR_IN_CONTEXT.findall(t)}
    is_tax_context = bool(re.search(r'tax\s+declaration|real\s+property\s+tax|RPT|assessor',
                                     t, re.IGNORECASE))
    if is_tax_context:
        years.update(int(y) for y in RE_YEAR_STANDALONE.findall(t))
    # Filter year range
    years = {y for y in years if 1950 <= y <= 2030}
    return {"pins": sorted(pins), "arps": sorted(arps), "years": sorted(years)}


# Phantom-title patterns (same logic as build_title_tree.py is_real_title rejection)
RE_TITLE_YEAR_PHANTOM = re.compile(r'^T-(19|20)[0-9]{2}$')
RE_TITLE_TAX_PIN_PHANTOM = re.compile(r'^T-\d{3}-\d{1,4}(-\d+)?$')


def is_phantom_title(t):
    """Return True if this title-ref should be removed (it's actually a year/PIN)."""
    if not t: return False
    t = t.strip()
    if RE_TITLE_YEAR_PHANTOM.match(t):
        return True
    if RE_TITLE_TAX_PIN_PHANTOM.match(t):
        return True
    # Also catch the longer ARP-style misparsings
    if re.match(r'^T-\d{4}-[A-Z]{2}', t):
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── Step 1: re-extract tax metadata from every doc ───────────────────
    cur.execute("""
        SELECT id, classification, smart_filename, original_filename, document_title,
               extracted_text
          FROM documents WHERE case_file = %s
    """, (args.case,))
    docs = cur.fetchall()
    print(f"[1/3] Re-extracting tax metadata from {len(docs)} docs...")

    update_count = 0
    totals = Counter()
    for d in docs:
        blob = " ".join(filter(None, [
            d.get("smart_filename"), d.get("original_filename"),
            d.get("document_title"), d.get("extracted_text"),
        ]))
        ex = extract_all(blob)
        if ex["pins"] or ex["arps"] or ex["years"]:
            totals["docs_with_pin"]  += 1 if ex["pins"]  else 0
            totals["docs_with_arp"]  += 1 if ex["arps"]  else 0
            totals["docs_with_year"] += 1 if ex["years"] else 0
            totals["total_pins"]   += len(ex["pins"])
            totals["total_arps"]   += len(ex["arps"])
            totals["total_years"]  += len(ex["years"])
            if not args.dry_run:
                cur.execute("""
                    UPDATE documents
                       SET property_index_numbers = %s,
                           arp_numbers            = %s,
                           tax_years              = %s,
                           updated_at             = NOW()
                     WHERE id = %s
                """, (ex["pins"], ex["arps"], ex["years"], d["id"]))
                update_count += 1
    print(f"   → docs with PIN: {totals['docs_with_pin']:>4d} ({totals['total_pins']} total)")
    print(f"   → docs with ARP: {totals['docs_with_arp']:>4d} ({totals['total_arps']} total)")
    print(f"   → docs with tax_year: {totals['docs_with_year']:>4d} ({totals['total_years']} total)")
    print(f"   → {update_count} doc rows updated\n")

    # ── Step 2: propagate to client_history (via JOIN backfill) ──────────
    print("[2/3] Propagating to client_history.{pins,arps,tax_years} via doc JOIN...")
    if not args.dry_run:
        cur.execute("""
            UPDATE client_history h
               SET property_index_numbers = d.property_index_numbers,
                   arp_numbers            = d.arp_numbers,
                   tax_years              = d.tax_years
              FROM documents d
             WHERE h.source_table = 'documents'
               AND h.source_id = d.id::text
               AND (d.property_index_numbers <> '{}'::text[]
                    OR d.arp_numbers <> '{}'::text[]
                    OR d.tax_years <> '{}'::int[])
        """)
        print(f"   → {cur.rowcount} client_history rows updated\n")

    # ── Step 3: clean phantoms out of title_refs ─────────────────────────
    print("[3/3] Cleaning phantom titles out of title_refs[] in client_history...")
    cur.execute("""
        SELECT id, title_refs FROM client_history
         WHERE case_file = %s AND title_refs <> '{}'::text[]
    """, (args.case,))
    rows = cur.fetchall()
    removed_total = 0
    phantom_examples = Counter()
    for r in rows:
        clean = [t for t in r["title_refs"] if not is_phantom_title(t)]
        removed = [t for t in r["title_refs"] if is_phantom_title(t)]
        if removed:
            removed_total += len(removed)
            for t in removed:
                phantom_examples[t] += 1
            if not args.dry_run:
                cur.execute("UPDATE client_history SET title_refs = %s WHERE id = %s",
                            (clean, r["id"]))
    print(f"   → removed {removed_total} phantom title-refs across {len([r for r in rows if any(is_phantom_title(t) for t in r['title_refs'])])} events")
    print(f"   → top phantoms removed:")
    for t, n in phantom_examples.most_common(10):
        print(f"       {t!r}: ×{n}")

    # Also clean documents.title_refs if that column exists (some pipelines populate it)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name='documents' AND column_name='title_refs'
    """)
    if cur.fetchone():
        cur.execute("""
            SELECT id, title_refs FROM documents
             WHERE case_file = %s AND title_refs IS NOT NULL AND title_refs <> '{}'::text[]
        """, (args.case,))
        doc_rows = cur.fetchall()
        d_removed = 0
        for r in doc_rows:
            clean = [t for t in r["title_refs"] if not is_phantom_title(t)]
            if len(clean) < len(r["title_refs"]):
                d_removed += len(r["title_refs"]) - len(clean)
                if not args.dry_run:
                    cur.execute("UPDATE documents SET title_refs = %s WHERE id = %s",
                                (clean, r["id"]))
        print(f"   → also cleaned {d_removed} phantoms from documents.title_refs")

    print("\nDone." + (" (dry-run — no DB writes)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
