#!/usr/bin/env python3
"""recategorize_probes.py — task #3 of action plan.

Expands the probe category enum + recategorizes the 58 "other" probes by
name pattern + rail. New categories beyond deploy_314's set:

  infrastructure — conn.*, health.*, hygiene.* (system health probes)
  business       — business.* (business-health rail)
  evidence_trail — opus.sim.* probes about specific T-numbers, chains,
                   provenance, encumbrances, fraud (the case-fact probes
                   that will become filing_discipline once deploy_315 lands)

Recategorization rules:
  rail = 'business_health'   → business
  rail = 'truth'             → infrastructure (truth probes are system health)
  rail = 'mandate'           → mandate (already correct)
  name LIKE 'conn.%'         → infrastructure
  name LIKE 'health.%'       → infrastructure
  name LIKE 'hygiene.%'      → infrastructure
  name LIKE 'business.%'     → business
  name LIKE 'opus.sim.jonathan_asks_%' + contains T-number patterns
                             → evidence_trail (case-fact probes)
  remaining 'other' stays 'other' (truly uncategorizable)
"""
from __future__ import annotations
import os, re
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def categorize(probe: dict) -> str | None:
    name = (probe["name"] or "").lower()
    rail = probe.get("rail")

    # Direct rail mapping for non-sim rails
    if rail == "business_health":
        return "business"
    if rail == "truth":
        return "infrastructure"

    # Name-based for sim rail
    if name.startswith("conn."):
        return "infrastructure"
    if name.startswith("health."):
        return "infrastructure"
    if name.startswith("hygiene."):
        return "infrastructure"
    if name.startswith("business."):
        return "business"

    # Case-fact / evidence_trail probes — opus probes about specific titles, chains, instruments
    if re.search(r"opus\.sim\.jonathan_asks_", name) and re.search(
            r"(t-?\d{3,5}|chain|provenance|encumbrance|fraud|inferred|verified|"
            r"manguisoc|cabanbanan|barandon|mandate|transfer|instrument|sap|spa)",
            name):
        return "evidence_trail"

    if re.search(r"(transferees|named_clients|active_clients|active_matters|"
                 r"client_count|filing_workflow|attachment_fetch|gmail_thread|"
                 r"deadline|pretrial)", name):
        return "evidence_trail"

    return None  # leave as is


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Expand the CHECK constraint to include new categories
    cur.execute("""
        ALTER TABLE leo_qa_probes DROP CONSTRAINT IF EXISTS leo_qa_probes_category_check
    """)
    cur.execute("""
        ALTER TABLE leo_qa_probes ADD CONSTRAINT leo_qa_probes_category_check
        CHECK (category IN ('security','mandate','capability','phrasing',
                            'onboarding','infrastructure','business',
                            'evidence_trail','filing_discipline','other'))
    """)

    # Recategorize all probes (idempotent — only updates when classification changes)
    cur.execute("SELECT id, name, rail, definition, category FROM leo_qa_probes")
    rows = cur.fetchall()
    moved = {"from→to": {}}
    for r in rows:
        new_cat = categorize(r)
        if not new_cat or new_cat == r.get("category"):
            continue
        key = f"{r.get('category')} → {new_cat}"
        moved["from→to"].setdefault(key, 0)
        moved["from→to"][key] += 1
        cur.execute("UPDATE leo_qa_probes SET category=%s WHERE id=%s", (new_cat, r["id"]))

    print("Recategorization moves:")
    for transition, n in sorted(moved["from→to"].items(), key=lambda kv: -kv[1]):
        print(f"  {transition:40s}  {n}")

    cur.execute("""
        SELECT category, COUNT(*) AS n
          FROM leo_qa_probes WHERE active
         GROUP BY category ORDER BY COUNT(*) DESC
    """)
    print("\nActive probes by category (final):")
    for r in cur.fetchall():
        print(f"  {r['category']:18s}  {r['n']}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
