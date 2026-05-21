#!/usr/bin/env python3
"""Deploy 229 — `resolutions` master table + backfill.

Promotes every Resolution event into a first-class record. Currently those
events live only as PDFs with extracted_text — no structured (date, adjudicator,
disposition, matter, source_doc) tuple.

Schema:
  - One row per resolution event
  - Multi-matter Resolutions (e.g., the April 7 one covering 0690 + 0792) use
    an `affected_matter_codes TEXT[]` column — same pattern as
    gmail_messages.matter_codes from deploy_226.

Backfill (deterministic regex over `documents`):
  - Candidate docs: classification='Resolution' OR smart_filename ILIKE '%resolution%'
    OR extracted_text matching '/[Rr]esolution\\b.*\\b(dated|granting|denying|dismissing)/'.
  - For each, extract:
      * Resolution date (doc_date if set, else date regex on text)
      * CTN(s) referenced
      * Adjudicator name (regex: "Atty. <CamelCase>" + "ARTA"/"CSC" context)
      * Disposition keywords (granted / denied / dismissed / remanded / partial)
      * Forum (ARTA / CSC / OP / RTC / other)
  - Provenance: inferred_weak — LLM-grade interpretation belongs in proposed_changes,
    not here. Promotion to verified via the lockdown ceremony.

NOT in this deploy: triggers / lockdown on resolutions. Add later once backfill
quality is reviewed (Phase 222 or 225).

Idempotent: ON CONFLICT (source_doc_id) DO NOTHING.
"""
import re
from datetime import datetime

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS resolutions (
    id SERIAL PRIMARY KEY,
    resolution_date DATE,
    forum TEXT,
    adjudicator_name_raw TEXT,
    adjudicator_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    affected_matter_codes TEXT[] DEFAULT '{}'::text[],
    affected_ctn_nos TEXT[] DEFAULT '{}'::text[],
    disposition TEXT,                  -- granted / denied / dismissed / remanded / partial / unknown
    disposition_summary TEXT,
    source_doc_id INTEGER UNIQUE REFERENCES documents(id) ON DELETE SET NULL,
    next_action_required TEXT,
    next_deadline DATE,
    provenance_level TEXT NOT NULL DEFAULT 'inferred_weak',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resolutions_matters
    ON resolutions USING GIN(affected_matter_codes);
CREATE INDEX IF NOT EXISTS idx_resolutions_date
    ON resolutions(resolution_date DESC);
CREATE INDEX IF NOT EXISTS idx_resolutions_adjudicator
    ON resolutions(adjudicator_entity_id);
CREATE INDEX IF NOT EXISTS idx_resolutions_forum
    ON resolutions(forum);

GRANT INSERT, SELECT, UPDATE ON resolutions TO n8n;
GRANT USAGE, SELECT ON SEQUENCE resolutions_id_seq TO n8n;
"""

# Regex patterns
CTN_RE = re.compile(
    r"\bCTN\s*[-:]?\s*SL\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{3,4})\b",
    re.IGNORECASE,
)
DATE_RES = [
    re.compile(r"\b(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})\b"),                # 07 April 2026
    re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})\b"),               # April 7, 2026
    re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"),                  # 2026-04-07
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b"),                        # 04/07/2026
]
MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Jun": 6, "Jul": 7,
    "Aug": 8, "Sep": 9, "Sept": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

ATTY_RES = [
    re.compile(r"Atty\.?\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+Jr\.?)?)"),
    re.compile(r"\b((?:Rodolfo|Daisy|Genes)\s+[A-Z]\.?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+Jr\.?)?)"),
]

DISP_PATTERNS = [
    (re.compile(r"\b(hereby\s+)?GRANTED\b", re.IGNORECASE), "granted"),
    (re.compile(r"\b(hereby\s+)?DENIED\b", re.IGNORECASE), "denied"),
    (re.compile(r"\b(hereby\s+)?DISMISSED\b", re.IGNORECASE), "dismissed"),
    (re.compile(r"\b(hereby\s+)?REMANDED\b", re.IGNORECASE), "remanded"),
    (re.compile(r"\bPARTIAL(LY)?\s+GRANTED\b", re.IGNORECASE), "partial_granted"),
    (re.compile(r"\bNOTICE\s+OF\s+COMPLIANCE\b", re.IGNORECASE), "compliance_notice"),
]

FORUMS = [
    (re.compile(r"\bAnti-Red\s+Tape\s+Authority\b", re.IGNORECASE), "ARTA"),
    (re.compile(r"\bCivil\s+Service\s+Commission\b", re.IGNORECASE), "CSC"),
    (re.compile(r"\bOffice\s+of\s+the\s+President\b", re.IGNORECASE), "OP"),
    (re.compile(r"\bRegional\s+Trial\s+Court\b", re.IGNORECASE), "RTC"),
    (re.compile(r"\bSupreme\s+Court\b", re.IGNORECASE), "SC"),
    (re.compile(r"\bDILG\b", re.IGNORECASE), "DILG"),
    (re.compile(r"\bPENRO\b", re.IGNORECASE), "PENRO"),
]


def parse_date(text, head_chars=5000):
    """Best-effort date extraction from doc head."""
    head = text[:head_chars] if text else ""
    for pat in DATE_RES:
        for m in pat.finditer(head):
            g = m.groups()
            try:
                if pat.pattern.startswith(r"\b(\d{1,2})\s+([A-Z]"):
                    d, mon_name, y = int(g[0]), g[1], int(g[2])
                    mon = MONTHS.get(mon_name) or MONTHS.get(mon_name.capitalize())
                    if mon and 1 <= d <= 31 and 1900 <= y <= 2100:
                        return f"{y:04d}-{mon:02d}-{d:02d}"
                elif pat.pattern.startswith(r"\b([A-Z][a-z]+)\s+"):
                    mon_name, d, y = g[0], int(g[1]), int(g[2])
                    mon = MONTHS.get(mon_name)
                    if mon and 1 <= d <= 31 and 1900 <= y <= 2100:
                        return f"{y:04d}-{mon:02d}-{d:02d}"
                elif pat.pattern.startswith(r"\b(20\d{2})"):
                    y, mon, d = int(g[0]), int(g[1]), int(g[2])
                    if 1 <= mon <= 12 and 1 <= d <= 31:
                        return f"{y:04d}-{mon:02d}-{d:02d}"
                else:
                    mon, d, y = int(g[0]), int(g[1]), int(g[2])
                    if 1 <= mon <= 12 and 1 <= d <= 31:
                        return f"{y:04d}-{mon:02d}-{d:02d}"
            except (ValueError, KeyError):
                continue
    return None


def extract_ctns(text, valid_matters):
    """Return (ctn_nos_list, matter_codes_set) for all CTNs in text."""
    ctn_nos = []
    matter_codes = set()
    for m in CTN_RE.finditer(text or ""):
        y1, y2, suffix = m.group(1), m.group(2), m.group(3)
        ctn_no = f"CTN SL-{y1}-{y2}-{suffix.zfill(4) if len(suffix) == 3 else suffix}"
        if ctn_no not in ctn_nos:
            ctn_nos.append(ctn_no)
        suffix_4 = suffix if len(suffix) == 4 else "0" + suffix
        candidate = f"MWK-ARTA-{suffix_4}"
        if candidate in valid_matters:
            matter_codes.add(candidate)
    return ctn_nos, matter_codes


def extract_adjudicator(text, head_chars=3000):
    """Find an attorney/judge name in the doc head. Returns name or None."""
    head = text[:head_chars] if text else ""
    for pat in ATTY_RES:
        m = pat.search(head)
        if m:
            return m.group(1).strip()
    return None


def extract_forum(text, head_chars=3000):
    head = text[:head_chars] if text else ""
    for pat, label in FORUMS:
        if pat.search(head):
            return label
    return None


def extract_disposition(text):
    """Look for disposition keywords in the full text. Returns label or 'unknown'."""
    if not text:
        return "unknown"
    for pat, label in DISP_PATTERNS:
        if pat.search(text):
            return label
    return "unknown"


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 229 — resolutions master table + backfill")
    print("=" * 70)

    print("\n[1/3] Schema: CREATE TABLE resolutions")
    cur.execute(SCHEMA_SQL)
    print("  ✓ resolutions + 4 indexes ready")

    print("\n[2/3] Loading valid matter_codes")
    cur.execute("SELECT matter_code FROM matters")
    valid_matters = set(r["matter_code"] for r in cur.fetchall())
    print(f"  ✓ {len(valid_matters)} matter_codes")

    print("\n[3/3] Backfilling resolutions from documents")
    cur.execute("""
        SELECT id, smart_filename, classification, doc_date,
               COALESCE(extracted_text, '') AS extracted_text
          FROM documents
         WHERE classification = 'Resolution'
            OR smart_filename ILIKE %s
            OR smart_filename ILIKE %s
            OR (extracted_text ILIKE %s AND extracted_text ILIKE %s)
    """, ("%resolution%", "%RESOLUTION%", "%RESOLUTION%", "%dispositive%"))
    candidates = cur.fetchall()
    print(f"  Scanning {len(candidates)} candidate documents…")

    inserted = 0
    skipped_already = 0
    per_disposition = {}
    per_forum = {}

    for d in candidates:
        # Skip if already have a resolution row for this doc
        cur.execute("SELECT 1 FROM resolutions WHERE source_doc_id = %s LIMIT 1",
                    (d["id"],))
        if cur.fetchone():
            skipped_already += 1
            continue

        text = d["extracted_text"] or ""
        if len(text) < 100:
            continue

        ctn_nos, matter_codes = extract_ctns(text, valid_matters)
        date = d["doc_date"].isoformat() if d["doc_date"] else parse_date(text)
        adj_name = extract_adjudicator(text)
        forum = extract_forum(text)
        disposition = extract_disposition(text)

        # Build a short disposition_summary from the smart_filename
        summary = (d["smart_filename"] or "")[:200] or None

        cur.execute("""
            INSERT INTO resolutions
                (resolution_date, forum, adjudicator_name_raw,
                 affected_matter_codes, affected_ctn_nos,
                 disposition, disposition_summary,
                 source_doc_id, provenance_level, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_doc_id) DO NOTHING
        """, (
            date,
            forum,
            adj_name,
            sorted(matter_codes),
            ctn_nos,
            disposition,
            summary,
            d["id"],
            "inferred_weak",
            f"backfilled via deploy_229 regex extraction from doc#{d['id']}",
        ))
        if cur.rowcount > 0:
            inserted += 1
            per_disposition[disposition] = per_disposition.get(disposition, 0) + 1
            per_forum[forum] = per_forum.get(forum, 0) + 1

    print(f"\n  ✓ {inserted} resolutions inserted, {skipped_already} skipped (already present)")
    print()
    print("  By disposition:")
    for k, v in sorted(per_disposition.items(), key=lambda x: -x[1]):
        print(f"    {k or 'unknown':<22s} {v}")
    print()
    print("  By forum:")
    for k, v in sorted(per_forum.items(), key=lambda x: -(x[1] if x[1] else 0)):
        print(f"    {k or '(none)':<22s} {v}")

    # Final snapshot — recent resolutions
    print()
    print("  Most recent 10 resolutions:")
    cur.execute("""
        SELECT id, resolution_date, forum, disposition,
               array_to_string(affected_matter_codes, ',') AS matters,
               LEFT(COALESCE(disposition_summary, ''), 60) AS summary
          FROM resolutions
         ORDER BY resolution_date DESC NULLS LAST, id DESC
         LIMIT 10
    """)
    for r in cur.fetchall():
        print(f"    #{r['id']}  {r['resolution_date'] or '?':10s}  "
              f"{(r['forum'] or '?'):<6s}  {(r['disposition'] or '?'):<18s}  "
              f"{r['matters'] or '-':<22s}  {r['summary'] or '-'}")

    print()
    print("=" * 70)
    print("✓ Deploy 229 complete.")
    print()
    print("Try: SELECT id, resolution_date, forum, disposition, affected_matter_codes")
    print("       FROM resolutions WHERE 'MWK-ARTA-1210' = ANY(affected_matter_codes)")
    print("       ORDER BY resolution_date DESC;")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
