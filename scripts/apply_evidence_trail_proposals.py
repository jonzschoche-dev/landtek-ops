#!/usr/bin/env python3
"""apply_evidence_trail_proposals.py — move approved proposals into canonical trail.

Reads evidence_trail_proposals WHERE status='approved'; for each, inserts
into evidence_trail and marks the proposal status='applied'.

Cron every hour, OR run on-demand after approving via SQL UPDATE.
Logs every transition for audit.
"""
from __future__ import annotations
import os
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, claim_id, supporting_doc_id, relation_kind, weight, narrative, confidence
          FROM evidence_trail_proposals
         WHERE status = 'approved'
         ORDER BY id
    """)
    rows = cur.fetchall()
    applied = 0
    for r in rows:
        try:
            cur.execute("""
                INSERT INTO evidence_trail
                  (claim_id, supporting_doc_id, relation_kind, weight, narrative,
                   provenance_level, added_by)
                VALUES (%s, %s, %s, %s, %s, 'inferred_strong', 'opus_evidence_proposer')
                ON CONFLICT DO NOTHING
            """, (r["claim_id"], r["supporting_doc_id"], r["relation_kind"],
                  r["weight"], r["narrative"]))
            cur.execute("UPDATE evidence_trail_proposals SET status='applied', applied_at=now() WHERE id=%s",
                        (r["id"],))
            applied += 1
            print(f"  applied proposal {r['id']}: claim {r['claim_id']} ← doc {r['supporting_doc_id']} ({r['weight']})")
        except Exception as e:
            print(f"  proposal {r['id']} failed: {e}")
    print(f"\n[apply_evidence_trail] {applied} of {len(rows)} approved proposals applied")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
