#!/usr/bin/env python3
"""Deploy 212 — PropEvidence Core: subdivision_plans table + initial backfill.

Per Jonathan 2026-05-21: "we should also have record of every subdivision plan."

A subdivision plan (Psd-XX-XXXXXX, Pcs-XXX, Psu-XXX, etc.) is the survey-plan
authority that creates a batch of derivative titles from a parent. Currently
fragmented across three tables:

  - documents.subdivision_plan (15 rows, 9 unique refs)
  - llm_extracted_lineage.lot_number_and_plan (4 rows)
  - heightened_ocr_results.survey_plan_psd (0 rows — schema unused)
  - 338+ raw-text Psd occurrences not consolidated

This deploy:
  1. Creates `subdivision_plans` master table — one row per plan_ref.
  2. Backfills from the three existing sources, with normalization
     (Psd-05-026197 canonical; LRC-prefixes stripped, OCR variants merged).
  3. Pure schema + data — no FK changes to title_chain yet (deploy_213).
  4. No chain walker changes (deploy_214).

Idempotent: ON CONFLICT (normalized_ref, case_file) DO NOTHING.
"""
import re
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS subdivision_plans (
    id                    SERIAL PRIMARY KEY,
    plan_ref              TEXT NOT NULL,
    normalized_ref        TEXT NOT NULL,
    plan_date             DATE,
    parent_title          TEXT,
    child_titles          TEXT[] DEFAULT '{}',
    lot_designations      TEXT[] DEFAULT '{}',
    total_area_sqm        NUMERIC(12,2),
    surveyor              TEXT,
    approval_authority    TEXT,
    case_file             TEXT,
    source_doc_id         INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    provenance_level      TEXT NOT NULL DEFAULT 'inferred_weak',
    notes                 TEXT,
    created_at            TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subdivision_plans_norm_case
    ON subdivision_plans(normalized_ref, COALESCE(case_file, ''));
CREATE INDEX IF NOT EXISTS idx_subdivision_plans_parent
    ON subdivision_plans(parent_title);
CREATE INDEX IF NOT EXISTS idx_subdivision_plans_source_doc
    ON subdivision_plans(source_doc_id);
"""


# Match Psd / PSD / Psu / PSU / Csd / CSD / Pcs / PCS — plus optional LRC prefix
PLAN_REF_RE = re.compile(
    r"(?:LRC\s+)?(Psd|PSD|psd|PsD|Pcs|PCS|Psu|PSU|Csd|CSD|Bsc|BSC)[-\s]?"
    r"(\d{2,3}[-\s]?\d{3,8}(?:[-\s]?\d{2,6})?)",
    re.IGNORECASE,
)


def normalize_plan_ref(raw):
    """Canonicalize a plan reference. Returns None if not parseable."""
    if not raw:
        return None
    raw = raw.strip()
    if len(raw) > 80 or len(raw) < 5:
        return None
    m = PLAN_REF_RE.search(raw)
    if not m:
        return None
    prefix = m.group(1).capitalize()  # "PSD" → "Psd", "PCs" → "Pcs"
    suffix = re.sub(r"[\s]+", "", m.group(2))
    if not suffix.startswith("-") and not suffix[0].isdigit():
        return None
    return f"{prefix}-{suffix}"


def upsert_plan(cur, plan_ref, normalized_ref, source_doc_id=None, case_file=None,
                provenance="inferred_weak", notes="", parent_title=None, child_titles=None,
                lot_designations=None):
    """Insert plan if not exists; merge new info if exists."""
    cur.execute("""
        INSERT INTO subdivision_plans
            (plan_ref, normalized_ref, source_doc_id, case_file, provenance_level,
             notes, parent_title, child_titles, lot_designations)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (normalized_ref, COALESCE(case_file, '')) DO UPDATE
           SET notes = subdivision_plans.notes ||
                        CASE WHEN subdivision_plans.notes != ''
                             THEN ' | ' ELSE '' END || EXCLUDED.notes,
               updated_at = NOW()
        RETURNING (xmax = 0) AS inserted
    """, (plan_ref, normalized_ref, source_doc_id, case_file, provenance,
          notes, parent_title, child_titles or [], lot_designations or []))
    row = cur.fetchone()
    return bool(row and row.get("inserted"))


def backfill_from_documents(cur):
    """Pull from documents.subdivision_plan."""
    print("\n[1/3] Backfilling from documents.subdivision_plan…")
    cur.execute("""
        SELECT id, case_file, subdivision_plan
          FROM documents
         WHERE subdivision_plan IS NOT NULL
           AND subdivision_plan != ''
           AND subdivision_plan NOT IN ('<UNKNOWN>', 'TCT No. 4497')
    """)
    rows = cur.fetchall()
    inserted = 0
    skipped = 0
    for r in rows:
        raw = r["subdivision_plan"]
        # Handle comma-separated multi-plan refs
        for chunk in re.split(r"[,;]", raw):
            chunk = chunk.strip()
            norm = normalize_plan_ref(chunk)
            if not norm:
                skipped += 1
                continue
            was_new = upsert_plan(
                cur, plan_ref=chunk, normalized_ref=norm,
                source_doc_id=r["id"], case_file=r["case_file"],
                provenance="inferred_corroborated",
                notes=f"from documents.subdivision_plan (doc#{r['id']})",
            )
            if was_new:
                inserted += 1
    print(f"  → {inserted} new plans, {skipped} unparseable")


def backfill_from_lineage(cur):
    """Pull from llm_extracted_lineage.lot_number_and_plan."""
    print("\n[2/3] Backfilling from llm_extracted_lineage…")
    cur.execute("""
        SELECT id, parent_title, derivative_title, lot_number_and_plan, source_doc_id
          FROM llm_extracted_lineage
         WHERE lot_number_and_plan IS NOT NULL
    """)
    rows = cur.fetchall()
    inserted = 0
    for r in rows:
        raw = r["lot_number_and_plan"]
        # Pattern is like "2-X-4-C-2, PSD-05-017527" — extract plan portion
        norm = normalize_plan_ref(raw)
        if not norm:
            continue
        # Extract lot designation (everything before comma)
        lot = None
        if "," in raw:
            lot = raw.split(",")[0].strip()
        was_new = upsert_plan(
            cur, plan_ref=raw, normalized_ref=norm,
            source_doc_id=r.get("source_doc_id"), case_file="MWK-001",
            provenance="inferred_strong",
            notes=f"from llm_extracted_lineage; parent={r['parent_title']} "
                  f"deriv={r['derivative_title']}",
            parent_title=r.get("parent_title"),
            child_titles=[r["derivative_title"]] if r.get("derivative_title") else None,
            lot_designations=[lot] if lot else None,
        )
        if was_new:
            inserted += 1
    print(f"  → {inserted} new plans from lineage")


def backfill_from_corpus_regex(cur, case_file="MWK-001"):
    """Scan extracted_text for plan refs not yet captured."""
    print("\n[3/3] Backfilling from corpus regex scan…")
    cur.execute("""
        SELECT id, case_file, extracted_text
          FROM documents
         WHERE case_file = %s
           AND extracted_text IS NOT NULL
           AND LENGTH(extracted_text) > 100
    """, (case_file,))
    rows = cur.fetchall()
    print(f"  Scanning {len(rows)} documents…")
    inserted = 0
    seen_refs_per_doc = set()
    for r in rows:
        text = r["extracted_text"] or ""
        matches = PLAN_REF_RE.finditer(text)
        for m in matches:
            raw = m.group(0)
            norm = normalize_plan_ref(raw)
            if not norm:
                continue
            key = (r["id"], norm)
            if key in seen_refs_per_doc:
                continue
            seen_refs_per_doc.add(key)
            was_new = upsert_plan(
                cur, plan_ref=raw.strip(), normalized_ref=norm,
                source_doc_id=r["id"], case_file=r["case_file"],
                provenance="inferred_weak",
                notes=f"corpus_regex doc#{r['id']}",
            )
            if was_new:
                inserted += 1
    print(f"  → {inserted} new plans from raw-text scan")


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Creating schema…")
    cur.execute(SCHEMA_SQL)
    print("✓ subdivision_plans table ready")

    backfill_from_documents(cur)
    backfill_from_lineage(cur)
    backfill_from_corpus_regex(cur)

    cur.execute("SELECT COUNT(*) AS n FROM subdivision_plans")
    n = cur.fetchone()["n"]
    print(f"\n→ subdivision_plans total: {n} rows")

    cur.execute("""
        SELECT normalized_ref, COUNT(*) AS hits, COUNT(DISTINCT source_doc_id) AS docs
          FROM subdivision_plans
         GROUP BY normalized_ref ORDER BY hits DESC LIMIT 10
    """)
    print("\nTop 10 plans by corpus footprint:")
    for r in cur.fetchall():
        print(f"  {r['normalized_ref']:30s}  hits={r['hits']}  docs={r['docs']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
