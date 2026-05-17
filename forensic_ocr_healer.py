#!/usr/bin/env python3
"""forensic_ocr_healer — tiered waterfall for healing POOR_OCR documents.

Per Jonathan 2026-05-17: "the forensic path must be clear and we must
understand the level of extraction awareness we will get with a more
complex model." So this script proceeds cheapest-first and reports per-tier
recovery so you can SEE exactly what each tier buys.

Tiers (cheapest → most expensive):
  T1 Filename heuristics (FREE, instant)
       Parse smart_filename for ISO date, type tokens, T-NNNN refs
  T2 Existing-text re-mine (FREE, instant)
       Re-run canonical-title + date-context regex on whatever extracted_text
       we already have, but using the tightened patterns from
       build_title_tree.py + reextract_tax_metadata.py
  T3 Haiku TEXT-mode JSON extraction (~$0.001/doc)
       Send the existing extracted_text to Haiku with a tool-call schema
       that enforces canonical title format and ISO date. No vision.
  T4 [GATE] — surface comparison sample to user before spending on vision

A document is RECOVERED when (date AND instrument_type) extracted, OR
(date AND at least one valid_title) extracted.

Status sets to provenance_level='vision_extracted' on recovery (not
'verified' — recovery is LLM-grade, not court-grade).

CLI:
  python3 forensic_ocr_healer.py --case MWK-001 --dry-run
  python3 forensic_ocr_healer.py --case MWK-001          # apply
  python3 forensic_ocr_healer.py --case MWK-001 --limit 3  # 3-doc smoke test
"""
import argparse
import re
import sys
from collections import Counter
from datetime import date
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# ── Canonical patterns reused from build_title_tree.py ──────────────────
RE_OCT          = re.compile(r'\bOCT\s*T-\d{1,5}\b', re.IGNORECASE)
RE_TCT_STD      = re.compile(r'\bT-(\d{1,6})\b')
RE_TCT_LONG     = re.compile(r'\bT-\d{2,3}-\d{7,}\b')

# Title-format gate: only these are accepted as titles in any tier
def is_canonical_title(t):
    if not t: return False
    t = t.strip()
    if RE_OCT.fullmatch(t): return True
    if RE_TCT_LONG.fullmatch(t): return True
    m = re.fullmatch(r'T-(\d{1,6})', t)
    if m:
        n = int(m.group(1))
        return not (1900 <= n <= 2030)
    return False


# Date patterns
RE_ISO_DATE = re.compile(r'\b(19\d\d|20[0-3]\d)-(\d{2})-(\d{2})\b')
RE_LONG_DATE = re.compile(
    r'\b(\d{1,2})(?:st|nd|rd|th)?\s+'
    r'(?:day\s+of\s+)?(January|February|March|April|May|June|July|August|'
    r'September|October|November|December)[\s,]+(\d{4})\b',
    re.IGNORECASE
)
MONTHS = {m.lower(): i+1 for i, m in enumerate([
    'january','february','march','april','may','june',
    'july','august','september','october','november','december'])}

# Instrument-type keywords → canonical form
INSTRUMENT_KEYWORDS = [
    (r'deed\s+of\s+absolute\s+sale',          'Deed of Absolute Sale'),
    (r'deed\s+of\s+confirmation',             'Deed of Confirmation'),
    (r'deed\s+of\s+donation',                 'Deed of Donation'),
    (r'deed\s+of\s+sale',                     'Deed of Sale'),
    (r'special\s+power\s+of\s+attorney',      'Special Power of Attorney'),
    (r'power\s+of\s+attorney',                'Power of Attorney'),
    (r'revocation\s+of\s+(?:special\s+)?power','Revocation of SPA'),
    (r'judicial\s+affidavit',                 'Judicial Affidavit'),
    (r'affidavit\s+of\s+adverse\s+claim',     'Affidavit of Adverse Claim'),
    (r'affidavit\s+of\s+confirmation',        'Affidavit of Confirmation'),
    (r'affidavit\s+of\s+loss',                'Affidavit of Loss'),
    (r'affidavit',                            'Affidavit'),
    (r'motion\s+for\s+summary\s+judgment',    'Motion for Summary Judgment'),
    (r'motion\s+to\s+\w+',                    'Motion'),
    (r'reply\s+to\s+|^reply\b',               'Reply'),
    (r'rejoinder',                            'Rejoinder'),
    (r'complaint[\s-]?affidavit',             'Complaint-Affidavit'),
    (r'\bcomplaint\b',                        'Complaint'),
    (r'demand\s+letter',                      'Demand Letter'),
    (r'petition\s+for\s+certiorari',          'Petition for Certiorari'),
    (r'\bpetition\b',                         'Petition'),
    (r'pre[\s-]?trial\s+order',               'Pre-Trial Order'),
    (r'\border\b',                            'Court Order'),
    (r'\bdecision\b',                         'Court Decision'),
    (r'\bnotice\b',                           'Notice'),
    (r'manifestation',                        'Manifestation'),
    (r'resolution',                           'Resolution'),
    (r'tax\s+declaration|declaration\s+of\s+real\s+property', 'Tax Declaration'),
    (r'real\s+property\s+tax|\bRPT\b',        'Real Property Tax'),
    (r'transfer\s+certificate\s+of\s+title|\bTCT\b', 'Title (TCT)'),
    (r'original\s+certificate\s+of\s+title|\bOCT\b', 'Title (OCT)'),
    (r'memorandum',                           'Memorandum'),
    (r'request\s+(?:for|to)',                 'Government Request/Submission'),
    (r'receipt',                              'Receipt'),
    (r'certificate',                          'Certificate'),
]


def extract_titles(text):
    """Extract canonical titles from any text source. Handles common prefix
    variants (T-, TCT-, TCT_, T.C.T., OCT T-) and normalizes to canonical form."""
    if not text: return []
    out = set()
    # OCT T-NNN
    for m in re.finditer(r'\bOCT\s*T-?\s*(\d{1,5})\b', text, re.IGNORECASE):
        out.add(f"OCT T-{m.group(1)}")
    # T-NNN-NNNNNNNNNN long format (Balane-style)
    for m in RE_TCT_LONG.finditer(text):
        out.add(m.group(0))
    # TCT prefix variants: TCT-NNNN, TCT NNNN, TCT_NNNN, T.C.T. NNNN
    for m in re.finditer(r'\bT\.?C\.?T\.?[-_\s]?(\d{1,6})\b', text):
        candidate = f"T-{m.group(1)}"
        if is_canonical_title(candidate):
            out.add(candidate)
    # Plain T-NNNN
    for m in re.finditer(r'\bT[-_\s](\d{1,6})\b', text):
        candidate = f"T-{m.group(1)}"
        if is_canonical_title(candidate):
            out.add(candidate)
    return sorted(out)


def extract_date(text):
    """Best date extractor. Returns ISO string or None."""
    if not text: return None
    m = RE_ISO_DATE.search(text)
    if m:
        y, mo, d = m.groups()
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass
    m = RE_LONG_DATE.search(text)
    if m:
        d, mo, y = m.groups()
        mn = MONTHS.get(mo.lower())
        if mn:
            try:
                return date(int(y), mn, int(d)).isoformat()
            except ValueError:
                pass
    return None


def extract_instrument(text):
    """Match instrument-type keywords. Returns canonical type or None."""
    if not text: return None
    tlow = text.lower()
    for pat, canon in INSTRUMENT_KEYWORDS:
        if re.search(pat, tlow):
            return canon
    return None


# ── Tier 1: filename heuristics ─────────────────────────────────────────
def tier1_filename(doc):
    blob = " ".join(filter(None, [
        doc.get("smart_filename"), doc.get("original_filename"),
        doc.get("document_title"),
    ])).replace("_", " ")
    return {
        "tier": "T1-filename",
        "document_date": extract_date(blob),
        "instrument_type": extract_instrument(blob),
        "valid_titles": extract_titles(blob),
        "grantor_or_principal": None,
        "grantee_or_agent": None,
    }


# ── Tier 2: existing-text re-mine ───────────────────────────────────────
def tier2_text_remine(doc):
    text = doc.get("extracted_text") or ""
    if len(text) < 50:
        return None
    return {
        "tier": "T2-remine",
        "document_date": extract_date(text[:5000]),
        "instrument_type": extract_instrument(text[:3000]),
        "valid_titles": extract_titles(text[:10000]),
        "grantor_or_principal": None,
        "grantee_or_agent": None,
    }


# ── Tier 3: Haiku TEXT-mode JSON extraction ─────────────────────────────
HAIKU_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "document_date": {
            "type": ["string", "null"],
            "description": "Primary date of the document in YYYY-MM-DD format, or null if no clear date.",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
        },
        "instrument_type": {
            "type": ["string", "null"],
            "description": "Canonical type, one of: Deed of Absolute Sale, Deed of Donation, Special Power of Attorney, Affidavit, Complaint, Motion, Petition, Notice, Court Order, Tax Declaration, Receipt, etc."
        },
        "valid_titles": {
            "type": "array",
            "items": {
                "type": "string",
                "description": "Canonical title format: 'OCT T-NNN', 'T-NNNNN' (NOT a year), or 'T-NNN-NNNNNNNNNN'. NEVER 'T-2023' or 'T-025-07'."
            },
            "description": "Real TCT/OCT titles only. Reject year-shaped values (T-1900..T-2030) and tax-PIN-shaped values (T-NNN-NN)."
        },
        "grantor_or_principal": {
            "type": ["string", "null"],
            "description": "Named transferor / principal / first party. Person or entity name. Null if unclear."
        },
        "grantee_or_agent": {
            "type": ["string", "null"],
            "description": "Named transferee / agent / second party. Null if unclear."
        }
    },
    "required": ["document_date", "instrument_type", "valid_titles",
                  "grantor_or_principal", "grantee_or_agent"]
}


def tier3_haiku_text(doc, client):
    text = (doc.get("extracted_text") or "").strip()
    if len(text) < 50:
        return None
    from llm_billing import anthropic_tool_call
    fname = doc.get("smart_filename") or doc.get("original_filename") or ""
    prompt = (
        f"You are extracting structured metadata from a Philippine property/legal "
        f"document. The OCR is noisy. Extract ONLY what you can confidently identify; "
        f"return null for uncertain fields. NEVER guess.\n\n"
        f"CRITICAL RULES:\n"
        f"  - For valid_titles: ONLY include canonical TCT/OCT formats. EXCLUDE any "
        f"value that looks like a year (T-2023, T-1992) or a Property Index Number "
        f"(T-025-07, T-001-00030, T-498-1258).\n"
        f"  - Real titles look like: OCT T-106, T-4497, T-32917, T-52540, "
        f"T-079-2021002126.\n"
        f"  - For document_date: return the PRIMARY date (the one the document was "
        f"executed or filed on), not a referenced date.\n"
        f"  - For parties: return verbatim names you can read. If OCR makes a name "
        f"illegible, return null. Do NOT invent.\n\n"
        f"FILENAME: {fname}\n\n"
        f"OCR TEXT (first 5000 chars):\n{text[:5000]}"
    )
    try:
        result = anthropic_tool_call(
            client,
            tool_name="extract_metadata",
            tool_description="Submit extracted document metadata.",
            input_schema=HAIKU_TOOL_SCHEMA,
            called_from="forensic_ocr_healer",
            purpose="tier3_text_extraction",
            case_file="MWK-001",
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system="You are a precise structured-data extractor. No guessing.",
            messages=[{"role": "user", "content": prompt}],
        )
        # Post-filter titles through our canonical-title gate
        result["valid_titles"] = [t for t in (result.get("valid_titles") or [])
                                   if is_canonical_title(t)]
        result["tier"] = "T3-haiku-text"
        return result
    except Exception as e:
        return {"tier": "T3-haiku-text", "error": str(e)[:200]}


# ── Recovery test ──────────────────────────────────────────────────────
def is_recovered(result):
    """A doc is recovered if it has AT LEAST 2 of the 3 core fields:
    document_date, instrument_type, valid_titles. Date alone is too thin;
    type+title with no date is still useful (the doc IS a TCT scan with
    a known title number, even if date is placeholder)."""
    if not result:
        return False
    has_date  = bool(result.get("document_date"))
    has_type  = bool(result.get("instrument_type"))
    has_title = bool(result.get("valid_titles"))
    return sum([has_date, has_type, has_title]) >= 2


# ── Eligibility: which docs need forensic? ─────────────────────────────
def fetch_eligible(cur, case_file, limit=None):
    """POOR_OCR criteria (matches export_raw_chronology score_ocr_quality logic):
    no classification OR no doc_date_norm OR garbled extracted_text."""
    sql = """
        SELECT id, classification, smart_filename, original_filename,
               document_title, doc_date_norm, extracted_text,
               drive_link, drive_file_id, file_path
          FROM documents
         WHERE case_file = %s
           AND (classification IS NULL OR classification = ''
                OR doc_date_norm IS NULL
                OR length(coalesce(extracted_text, '')) < 100)
         ORDER BY (classification IS NOT NULL) DESC,  -- prefer ones with at least classification
                  id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql, (case_file,))
    return cur.fetchall()


def render_compare(doc, before, after):
    """Side-by-side before/after for one doc, terminal-friendly."""
    out = [f"\ndoc#{doc['id']}  ({doc.get('smart_filename') or '(no filename)'})"]
    out.append(f"{'  BEFORE':40s}  {'AFTER (' + after.get('tier','?') + ')':40s}")
    out.append("  " + "-"*78)
    rows = [
        ("classification",  doc.get("classification") or "(NULL)",  after.get("instrument_type") or "(none)"),
        ("doc_date_norm",   str(doc.get("doc_date_norm") or "(NULL)"), after.get("document_date") or "(none)"),
        ("titles (raw)",    str(before)[:40], ", ".join(after.get("valid_titles") or []) or "(none)"),
        ("parties",          "(not extracted)", f"{after.get('grantor_or_principal') or '?'} → {after.get('grantee_or_agent') or '?'}"),
    ]
    for label, b, a in rows:
        out.append(f"  {label:20s} {b[:40]:40s}  {str(a)[:40]:40s}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--limit", type=int, help="Cap candidates (for pilot/test)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-haiku", action="store_true", help="Skip tier 3 (free tiers only)")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    docs = fetch_eligible(cur, args.case, args.limit)
    print(f"Found {len(docs)} POOR_OCR candidates for case={args.case}")

    client = None
    if not args.skip_haiku:
        import anthropic
        from landtek_core import get
        api_key = get("ANTHROPIC_API_KEY")
        if not api_key:
            for l in open("/root/landtek/.env"):
                if l.startswith("ANTHROPIC_API_KEY="):
                    api_key = l.split("=", 1)[1].strip(); break
        client = anthropic.Anthropic(api_key=api_key)

    # Per-tier counters
    counts = {"T1-filename": 0, "T2-remine": 0, "T3-haiku-text": 0,
              "residual": 0, "total": len(docs)}
    pilot_comparisons = []

    for doc in docs:
        result = None
        # T1
        r1 = tier1_filename(doc)
        if is_recovered(r1):
            result = r1
        if not result:
            # T2
            r2 = tier2_text_remine(doc)
            if is_recovered(r2):
                result = r2
        if not result and not args.skip_haiku:
            # T3 (Haiku text-mode)
            r3 = tier3_haiku_text(doc, client)
            if is_recovered(r3):
                result = r3

        if result:
            counts[result["tier"]] += 1
            if args.dry_run or args.limit:
                pilot_comparisons.append((doc, result))
            if not args.dry_run:
                # Update documents with recovered fields
                cur.execute("""
                    UPDATE documents
                       SET classification    = COALESCE(NULLIF(classification, ''), %s),
                           doc_date_norm     = COALESCE(doc_date_norm, %s),
                           updated_at        = NOW()
                     WHERE id = %s
                """, (result.get("instrument_type"), result.get("document_date"), doc["id"]))
                # Append parties + titles to a forensic_metadata JSON if column exists,
                # else stash as notes
                cur.execute("""
                    INSERT INTO extraction_chunks
                      (doc_id, chunk_type, field_name, field_status, structured_value, provenance_level)
                    VALUES (%s, 'forensic_healer', %s, 'extracted', %s::jsonb, 'vision_extracted')
                    ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
                      SET structured_value = EXCLUDED.structured_value,
                          provenance_level = EXCLUDED.provenance_level
                """, (doc["id"], result["tier"],
                      psycopg2.extras.Json(result)))
        else:
            counts["residual"] += 1
            if args.dry_run or args.limit:
                pilot_comparisons.append((doc, {"tier": "RESIDUAL", "document_date": None,
                                                  "instrument_type": None, "valid_titles": [],
                                                  "grantor_or_principal": None, "grantee_or_agent": None}))

    print("\n" + "═"*70)
    print("WATERFALL RESULTS")
    print("═"*70)
    print(f"  Total POOR_OCR candidates:   {counts['total']}")
    print(f"  Recovered by T1 (filename):  {counts['T1-filename']:>4d}  (free)")
    print(f"  Recovered by T2 (text-remine):{counts['T2-remine']:>4d}  (free)")
    print(f"  Recovered by T3 (Haiku text):{counts['T3-haiku-text']:>4d}  (~$0.001/doc)")
    cumulative = counts['T1-filename'] + counts['T2-remine'] + counts['T3-haiku-text']
    print(f"  ─────────────────────────────────")
    print(f"  TOTAL RECOVERED:             {cumulative}/{counts['total']} = {100*cumulative//max(counts['total'],1)}%")
    print(f"  RESIDUAL (needs vision T4+): {counts['residual']}")

    if pilot_comparisons:
        print("\n" + "═"*70)
        print("PER-DOC BEFORE → AFTER")
        print("═"*70)
        for doc, result in pilot_comparisons[:10]:
            print(render_compare(doc,
                                  doc.get("classification") or "(no class)",
                                  result))


if __name__ == "__main__":
    main()
