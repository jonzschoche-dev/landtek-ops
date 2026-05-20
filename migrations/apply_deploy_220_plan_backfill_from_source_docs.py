#!/usr/bin/env python3
"""Deploy 220-A — Backfill title_chain ↔ subdivision_plans linkage by extracting
plan refs from each edge's source document.

After deploy_219, schema is in place but only 1 subdivision_plan row had the
parent_title + child_titles structure needed to link edges. This script walks
every title_chain edge that HAS a source_doc_id, scans the source doc's
extracted_text for a plan reference appearing near the parent/child title
mention, and populates the linkage.

For each match:
  1. Look up or create subdivision_plans row by normalized_ref
  2. Populate parent_title + append child_title to child_titles
  3. Set title_chain.subdivision_plan_id

Idempotent. Plan refs are normalized via the deploy_212 regex.
"""
import re
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Same regex as deploy_212 (inlined to avoid cross-migration imports).
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
    prefix = m.group(1).capitalize()
    suffix = re.sub(r"[\s]+", "", m.group(2))
    if not suffix or not suffix[0].isdigit():
        return None
    return f"{prefix}-{suffix}"


def find_plan_near_titles(text, parent_title, child_title, window=500):
    """Look for a plan ref within `window` chars of either title's mention in text."""
    if not text:
        return None
    positions = []
    for t in (parent_title, child_title):
        if not t:
            continue
        # Find all occurrences of the title text
        for m in re.finditer(re.escape(t), text):
            positions.append(m.start())
    if not positions:
        # Fall back: scan whole document
        m = PLAN_REF_RE.search(text)
        return m.group(0) if m else None
    # Prefer plan refs near a title mention
    for pos in positions:
        chunk = text[max(0, pos - window):pos + window]
        m = PLAN_REF_RE.search(chunk)
        if m:
            return m.group(0)
    return None


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Scan edges with source_doc_id but no plan link
    cur.execute("""
        SELECT tc.parent_title, tc.child_title, tc.source_doc_id,
               d.extracted_text, d.case_file
          FROM title_chain tc
          JOIN documents d ON d.id = tc.source_doc_id
         WHERE tc.subdivision_plan_id IS NULL
           AND tc.source_doc_id IS NOT NULL
           AND d.extracted_text IS NOT NULL
           AND LENGTH(d.extracted_text) > 100
    """)
    edges = cur.fetchall()
    print(f"Scanning {len(edges)} title_chain edges with source docs but no plan link…")

    linked = 0
    plans_touched = 0
    no_match = 0

    for e in edges:
        raw_plan = find_plan_near_titles(
            e["extracted_text"],
            e["parent_title"],
            e["child_title"],
        )
        if not raw_plan:
            no_match += 1
            continue
        norm = normalize_plan_ref(raw_plan)
        if not norm:
            no_match += 1
            continue

        # Find or insert the plan row
        cur.execute("""
            SELECT id, parent_title, child_titles FROM subdivision_plans
             WHERE normalized_ref = %s AND (case_file = %s OR case_file IS NULL)
             LIMIT 1
        """, (norm, e["case_file"]))
        plan = cur.fetchone()
        if not plan:
            cur.execute("""
                INSERT INTO subdivision_plans
                    (plan_ref, normalized_ref, parent_title, child_titles,
                     case_file, source_doc_id, provenance_level, notes)
                VALUES (%s, %s, %s, ARRAY[%s], %s, %s, %s, %s)
                RETURNING id
            """, (raw_plan.strip(), norm, e["parent_title"], e["child_title"],
                  e["case_file"], e["source_doc_id"], "inferred_strong",
                  f"backfilled via deploy_220 from title_chain edge "
                  f"{e['parent_title']} → {e['child_title']} (doc#{e['source_doc_id']})"))
            plan_id = cur.fetchone()["id"]
            plans_touched += 1
        else:
            plan_id = plan["id"]
            existing_children = plan["child_titles"] or []
            updates = []
            params = []
            if not plan["parent_title"]:
                updates.append("parent_title = %s")
                params.append(e["parent_title"])
            if e["child_title"] not in existing_children:
                updates.append("child_titles = array_append(child_titles, %s)")
                params.append(e["child_title"])
            if updates:
                updates.append("provenance_level = CASE WHEN provenance_level = 'inferred_weak' "
                               "THEN 'inferred_strong' ELSE provenance_level END")
                updates.append("updated_at = NOW()")
                params.append(plan_id)
                cur.execute(
                    f"UPDATE subdivision_plans SET {', '.join(updates)} WHERE id = %s",
                    params,
                )
                plans_touched += 1

        # Link the edge
        cur.execute("""
            UPDATE title_chain SET subdivision_plan_id = %s
             WHERE parent_title = %s AND child_title = %s AND subdivision_plan_id IS NULL
        """, (plan_id, e["parent_title"], e["child_title"]))
        if cur.rowcount > 0:
            linked += 1
            print(f"  ✓ {e['parent_title']:>20s} → {e['child_title']:<22s} ↔ {norm}  (doc#{e['source_doc_id']})")

    print(f"\n→ {linked} edges linked, {plans_touched} subdivision_plans rows created/updated, "
          f"{no_match} edges with source doc but no plan ref found")

    cur.execute("""
        SELECT COUNT(*) AS total, COUNT(subdivision_plan_id) AS linked
          FROM title_chain WHERE case_file = 'MWK-001' OR case_file IS NULL
    """)
    r = cur.fetchone()
    print(f"\nFinal coverage: {r['linked']}/{r['total']} edges linked to a subdivision plan")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
