#!/usr/bin/env python3
"""export_raw_chronology — strict-truth chronological ledger (deploy_168).

NO LLM synthesis. NO hallucination risk. Every row either:
  - CLEAN     — verified extracted metadata (date, matter, type, parties)
  - POOR_OCR  — source-doc link only, flagged for human review

Output: /root/landtek/drafts/raw_chronology_<case>_<date>.{csv,md}

Columns: DATE | MATTER | EVENT_TYPE | PARTIES/ENTITIES | DATA_STATUS | SOURCE_FILE_LINK

Per Jonathan 2026-05-17: "we cannot have LLMs hallucinating on the data we need
indisputable truths and all necessary documents that need to be taken a closer
look at flagged for a more in-depth research"
"""
import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Common short words (English + Filipino) — used to verify extracted_text is
# actually language, not OCR noise. A real legal document has dozens of these.
COMMON_WORDS = {
    # English function words
    'the', 'of', 'and', 'to', 'in', 'for', 'by', 'that', 'this', 'said',
    'with', 'as', 'is', 'be', 'on', 'at', 'or', 'are', 'a', 'an',
    'have', 'has', 'was', 'were', 'will', 'shall', 'all', 'any', 'one',
    # Philippine legal/property domain markers
    'philippines', 'republic', 'province', 'municipality', 'witness',
    'hereby', 'whereas', 'therefore', 'court', 'order', 'plaintiff',
    'defendant', 'title', 'land', 'property', 'deed', 'parcel',
    'registered', 'lot', 'estate',
    # Filipino function words
    'ng', 'sa', 'ang', 'na', 'mga', 'kay', 'ay',
}


def score_ocr_quality(text, classification):
    """Return (status, reason). Windowed-sampling heuristic — ALL windows
    must pass; one bad 1K-char window is enough to flag the doc as POOR_OCR.
    Tightened (deploy_168b) after the first-pass heuristic let doc#78
    ('rtEstsoONO64460 SDIS VASIVm TVSTYL...') through as CLEAN."""
    # Empty / missing core metadata → POOR
    if not classification or classification.strip() == "":
        return "POOR_OCR", "classification_missing"
    if not text or len(text.strip()) < 100:
        return "POOR_OCR", "text_missing_or_too_short"

    # Sample up to 5 non-overlapping 1KB windows spread across the doc.
    n_windows = min(5, max(1, len(text) // 1000))
    stride = max(1000, len(text) // n_windows)
    windows = [text[i:i+1000] for i in range(0, n_windows * stride, stride)]

    for idx, t in enumerate(windows):
        t = t.strip()
        if len(t) < 100:
            continue  # tiny tail window — skip

        # 1. Non-alphanumeric (excluding whitespace) ratio
        non_alnum = sum(1 for c in t if not c.isalnum() and not c.isspace())
        ratio = non_alnum / len(t)
        if ratio > 0.30:
            return "POOR_OCR", f"window_{idx}_punct_noise={ratio:.2f}"

        # 2. Common-words DENSITY (not just count) — real legal text has
        #    function words on every line; OCR garbage has them sparsely.
        words = re.findall(r'[a-zA-Z]+', t.lower())
        if len(words) < 30:
            return "POOR_OCR", f"window_{idx}_too_few_words={len(words)}"
        common_found = sum(1 for w in words if w in COMMON_WORDS)
        density = common_found / len(words)
        if density < 0.04:  # at least 4% of words must be common-language
            return "POOR_OCR", f"window_{idx}_low_lang_density={common_found}/{len(words)}={density:.3f}"

        # 3. Consonant-cluster detection: real words rarely have 5+ consonants
        #    in a row. OCR garbage produces tokens like 'rtEstsoONO',
        #    'Squenejso', 'BuAQJdu' that fail this test.
        garbage_words = sum(1 for w in words
                            if re.search(r'[bcdfghjklmnpqrstvwxyz]{5,}', w.lower()))
        if garbage_words / len(words) > 0.08:
            return "POOR_OCR", f"window_{idx}_consonant_clusters={garbage_words}/{len(words)}"

        # 4. Vowel ratio (English ~38%, Filipino ~40%)
        letters = [c.lower() for c in t if c.isalpha()]
        if letters:
            vowels = sum(1 for c in letters if c in 'aeiou')
            vowel_ratio = vowels / len(letters)
            if vowel_ratio < 0.28 or vowel_ratio > 0.50:
                return "POOR_OCR", f"window_{idx}_vowel_ratio={vowel_ratio:.2f}"

        # 5. Non-ASCII rare-char check (OCR sometimes produces 'ɔ', 'ự', etc.)
        weird_chars = sum(1 for c in t if ord(c) > 127 and not c.isspace())
        if weird_chars / len(t) > 0.05:
            return "POOR_OCR", f"window_{idx}_rare_unicode={weird_chars}/{len(t)}"

    return "CLEAN", "passes_all_heuristics"


def build_source_link(source_table, source_id, drive_link=None, drive_file_id=None):
    """Best clickable link to the original document."""
    if drive_link:
        return drive_link
    if drive_file_id:
        return f"https://drive.google.com/file/d/{drive_file_id}/view"
    return f"{source_table}#{source_id}"


def extract_parties(event):
    """Pull verifiable parties from structured DB fields only.
    Never from extracted_text (that's where hallucination would happen)."""
    parts = []
    if event.get("tt_transferor") and event["tt_transferor"] not in ("—", "?", ""):
        parts.append(f"from: {event['tt_transferor']}")
    if event.get("tt_transferee_name") and event["tt_transferee_name"] not in ("—", "?", ""):
        parts.append(f"to: {event['tt_transferee_name']}")
    if event.get("tx_counterparty"):
        d = event.get("direction") or "?"
        verb = "to" if d == "out" else "from" if d == "in" else "cp"
        parts.append(f"{verb}: {event['tx_counterparty']}")
    if event.get("gmail_from_name") or event.get("from_addr"):
        sender = event.get("gmail_from_name") or event.get("from_addr")
        parts.append(f"sender: {sender}")
    if event.get("title_refs"):
        parts.append("titles: " + ", ".join(event["title_refs"][:5]))
    return " | ".join(parts) if parts else ""


def event_type_for(e, status):
    """Determine the EVENT_TYPE column value."""
    if status == "POOR_OCR":
        return "[MANUAL REVIEW REQUIRED - POOR OCR]"
    if e["source_table"] == "documents":
        return e["classification"] or "(unclassified)"
    if e["source_table"] == "transactions":
        amt = float(e.get("amount") or 0)
        d = e.get("direction") or "?"
        return f"Transaction — {d.upper()} P{amt:,.2f} ({e.get('category') or 'unknown'})"
    if e["source_table"] == "gmail_messages":
        return f"Email — {(e.get('gmail_subject') or '(no subject)')[:100]}"
    if e["source_table"] == "title_transfers":
        return f"{e.get('instrument_type') or 'Title transfer'} ({e.get('parent_title') or '?'}→{e.get('derivative_title') or '?'})"
    return e.get("event_kind_canonical") or e.get("event_kind") or "Event"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    limit_clause = f"LIMIT {int(args.limit)}" if args.limit else ""
    cur.execute(f"""
        SELECT
          h.id, h.matter_codes, h.title_refs,
          COALESCE(h.event_date, h.date_executed, h.date_filed, h.date_received) AS dt,
          h.event_kind, h.event_kind_canonical, h.what_summary,
          h.source_table, h.source_id,
          d.classification, d.smart_filename, d.original_filename,
          d.document_title, d.execution_status, d.extracted_text,
          d.drive_link, d.drive_file_id,
          t.amount, t.direction, t.category, t.counterparty AS tx_counterparty,
          g.subject AS gmail_subject, g.from_addr, g.from_name AS gmail_from_name,
          tt.instrument_type, tt.parent_title, tt.derivative_title,
          tt.transferor AS tt_transferor, tt.transferee_name AS tt_transferee_name
        FROM client_history h
        LEFT JOIN documents d ON h.source_table='documents' AND h.source_id=d.id::text
        LEFT JOIN transactions t ON h.source_table='transactions' AND h.source_id=t.id::text
        LEFT JOIN gmail_messages g ON h.source_table='gmail_messages' AND h.source_id=g.id::text
        LEFT JOIN title_transfers tt ON h.source_table='title_transfers' AND h.source_id=tt.id::text
        WHERE h.case_file = %s
        ORDER BY dt NULLS LAST, h.id
        {limit_clause}
    """, (args.case,))
    events = cur.fetchall()

    rows = []
    for e in events:
        date_str = e["dt"].isoformat() if e["dt"] else "(undated)"
        matter_codes = e.get("matter_codes") or []
        matter = ",".join(matter_codes) if matter_codes else "GENERAL"

        # OCR-quality gate — documents only need OCR check; structured-data
        # source tables (transactions, gmail, title_transfers) are always CLEAN.
        if e["source_table"] == "documents":
            status, reason = score_ocr_quality(e["extracted_text"], e["classification"])
        else:
            status, reason = "CLEAN", "structured_db_data"

        event_type = event_type_for(e, status)

        # POOR_OCR rows do NOT print parties (no hallucinated names from garbage)
        parties = extract_parties(e) if status == "CLEAN" else ""

        source_link = build_source_link(
            e["source_table"], e["source_id"],
            drive_link=e.get("drive_link"),
            drive_file_id=e.get("drive_file_id"),
        )

        rows.append({
            "date": date_str, "matter": matter, "event_type": event_type,
            "parties": parties, "data_status": status,
            "source_link": source_link, "ocr_reason": reason,
            "source_table": e["source_table"], "source_id": e["source_id"],
        })

    today = date.today().isoformat()
    out_dir = Path("/root/landtek/drafts"); out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"raw_chronology_{args.case}_{today}.csv"
    md_path  = out_dir / f"raw_chronology_{args.case}_{today}.md"

    # Write CSV
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "date", "matter", "event_type", "parties", "data_status",
            "source_link", "ocr_reason", "source_table", "source_id"
        ])
        w.writeheader()
        w.writerows(rows)

    # Counts
    clean_rows = [r for r in rows if r['data_status'] == 'CLEAN']
    poor_rows  = [r for r in rows if r['data_status'] == 'POOR_OCR']

    # Markdown ledger
    md = [
        f"# Raw Chronology — {args.case} ({today})",
        "",
        f"_Strict-truth ledger. NO LLM synthesis. {len(rows)} events: "
        f"**{len(clean_rows)} CLEAN** + **{len(poor_rows)} POOR_OCR** (manual review required)._",
        "",
        "| DATE | MATTER | EVENT TYPE | PARTIES/ENTITIES | STATUS | SOURCE |",
        "|------|--------|------------|------------------|--------|--------|",
    ]
    for r in rows:
        link = (f"[open]({r['source_link']})" if r['source_link'].startswith("http")
                else f"`{r['source_link']}`")
        # Escape pipe chars in cell content
        parties_cell = (r['parties'] or '—').replace("|", "\\|")[:120]
        et_cell      = r['event_type'].replace("|", "\\|")[:80]
        matter_cell  = r['matter'].replace("|", "\\|")[:35]
        md.append(f"| {r['date']} | {matter_cell} | {et_cell} | "
                  f"{parties_cell} | {r['data_status']} | {link} |")
    md_path.write_text("\n".join(md))

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    print(f"\nTotal: {len(rows)} events | CLEAN: {len(clean_rows)} ({100*len(clean_rows)//max(len(rows),1)}%) | "
          f"POOR_OCR: {len(poor_rows)} ({100*len(poor_rows)//max(len(rows),1)}%)")

    print("\n=== First 5 CLEAN rows ===")
    for r in clean_rows[:5]:
        print(f"  {r['date']:12s} | {r['matter'][:30]:30s} | "
              f"{r['event_type'][:35]:35s} | {(r['parties'] or '—')[:50]:50s} | "
              f"{r['source_link'][:50]}")
    print("\n=== First 5 POOR_OCR rows ===")
    for r in poor_rows[:5]:
        print(f"  {r['date']:12s} | {r['matter'][:30]:30s} | "
              f"{r['event_type'][:35]:35s} | (suppressed)                                       | "
              f"reason={r['ocr_reason'][:25]} | {r['source_link'][:50]}")


if __name__ == "__main__":
    main()
