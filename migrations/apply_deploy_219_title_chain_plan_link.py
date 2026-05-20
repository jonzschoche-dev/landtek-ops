#!/usr/bin/env python3
"""Deploy 219 — Link subdivision_plans to title_chain edges.

Adds `subdivision_plan_id` FK column to title_chain. Backfills by matching
subdivision_plans.parent_title + (each child in child_titles) against existing
title_chain edges. Most rows from deploy_212's regex backfill don't have
parent/child populated, so initial coverage will be limited to:
  - The lineage-derived plan (T-32916 → T-37868 via PSD-05-017527)
  - Any plans that get parent/child structure filled in later

Idempotent. Adds nullable column → does not break existing queries.

After this deploy, title_chain_walker.render_chain_md surfaces the plan that
effected each edge (where known), and flags edges without plan provenance
as discovery priorities.
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


SCHEMA_SQL = """
ALTER TABLE title_chain
    ADD COLUMN IF NOT EXISTS subdivision_plan_id INTEGER
        REFERENCES subdivision_plans(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_title_chain_subdivision_plan
    ON title_chain(subdivision_plan_id);
"""


def backfill(cur):
    """For each subdivision_plan with parent + child_titles, link matching title_chain edges."""
    cur.execute("""
        SELECT id, plan_ref, normalized_ref, parent_title, child_titles
          FROM subdivision_plans
         WHERE parent_title IS NOT NULL
           AND array_length(child_titles, 1) > 0
    """)
    plans = cur.fetchall()
    print(f"\nFound {len(plans)} subdivision_plans with parent + child structure")

    total_linked = 0
    for p in plans:
        parent = p["parent_title"]
        children = p["child_titles"] or []
        for child in children:
            cur.execute("""
                UPDATE title_chain
                   SET subdivision_plan_id = %s
                 WHERE parent_title = %s
                   AND child_title = %s
                   AND subdivision_plan_id IS DISTINCT FROM %s
                RETURNING parent_title, child_title
            """, (p["id"], parent, child, p["id"]))
            linked = cur.fetchall()
            if linked:
                for row in linked:
                    print(f"  ✓ linked {row['parent_title']} → {row['child_title']} "
                          f"via plan {p['plan_ref']}")
                total_linked += len(linked)
    print(f"\n→ {total_linked} title_chain edges linked to a subdivision_plan")


def coverage_report(cur):
    """Show overall linkage coverage."""
    cur.execute("""
        SELECT
            COUNT(*) AS total_edges,
            COUNT(subdivision_plan_id) AS linked_edges,
            COUNT(*) FILTER (WHERE source_doc_id IS NULL) AS edges_no_source_doc,
            COUNT(*) FILTER (WHERE subdivision_plan_id IS NULL AND source_doc_id IS NULL)
                AS edges_no_plan_no_source
          FROM title_chain
         WHERE case_file = 'MWK-001' OR case_file IS NULL
    """)
    r = cur.fetchone()
    print(f"\nCoverage in title_chain (MWK-001):")
    print(f"  Total edges:                  {r['total_edges']}")
    print(f"  Linked to subdivision plan:   {r['linked_edges']}")
    print(f"  Edges without source_doc_id:  {r['edges_no_source_doc']}")
    print(f"  Edges without plan AND source: {r['edges_no_plan_no_source']}")


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Adding subdivision_plan_id column to title_chain…")
    cur.execute(SCHEMA_SQL)
    print("✓ schema ready")

    backfill(cur)
    coverage_report(cur)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
