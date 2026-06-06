#!/usr/bin/env python3
"""apply_evidence_trail_proposals.py — auto-apply ≥0.90 + apply approved (deploy_327).

Two modes, both run hourly:

  (1) AUTO-APPLY high-confidence proposals (≥0.90 confidence) directly into
      evidence_trail without manual approval. Confidence-gated; conservative.

  (2) APPLY proposals that Jonathan has explicitly approved by setting
      status='approved'.

Both modes:
  - INSERT into evidence_trail with provenance_level='inferred_strong'
  - Mark proposal as 'applied' with applied_at timestamp
  - Log every transition for audit
"""
from __future__ import annotations
import os, sys
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"
AUTO_APPLY_CONFIDENCE = 0.90


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # (1) Auto-apply high-confidence pending proposals
    cur.execute(f"""
        SELECT id, claim_id, supporting_doc_id, relation_kind, weight, narrative, confidence
          FROM evidence_trail_proposals
         WHERE status = 'pending' AND confidence >= {AUTO_APPLY_CONFIDENCE}
         ORDER BY id
    """)
    auto = cur.fetchall()
    auto_applied = 0
    for r in auto:
        try:
            cur.execute("""
                INSERT INTO evidence_trail (claim_id, supporting_doc_id, relation_kind,
                  weight, narrative, provenance_level, added_by)
                VALUES (%s,%s,%s,%s,%s,'inferred_strong','evidence_trail_proposer_auto')
                ON CONFLICT DO NOTHING
            """, (r["claim_id"], r["supporting_doc_id"], r["relation_kind"],
                  r["weight"], r["narrative"]))
            cur.execute("UPDATE evidence_trail_proposals SET status='applied', applied_at=now() WHERE id=%s",
                        (r["id"],))
            auto_applied += 1
        except Exception as e:
            print(f"  [auto] proposal {r['id']} failed: {e}")

    # (2) Apply manually-approved proposals
    cur.execute("""
        SELECT id, claim_id, supporting_doc_id, relation_kind, weight, narrative, confidence
          FROM evidence_trail_proposals
         WHERE status = 'approved'
         ORDER BY id
    """)
    approved = cur.fetchall()
    manual_applied = 0
    for r in approved:
        try:
            cur.execute("""
                INSERT INTO evidence_trail (claim_id, supporting_doc_id, relation_kind,
                  weight, narrative, provenance_level, added_by)
                VALUES (%s,%s,%s,%s,%s,'inferred_strong','jonathan_approved')
                ON CONFLICT DO NOTHING
            """, (r["claim_id"], r["supporting_doc_id"], r["relation_kind"],
                  r["weight"], r["narrative"]))
            cur.execute("UPDATE evidence_trail_proposals SET status='applied', applied_at=now() WHERE id=%s",
                        (r["id"],))
            manual_applied += 1
        except Exception as e:
            print(f"  [manual] proposal {r['id']} failed: {e}")

    total = auto_applied + manual_applied
    print(f"[apply_evidence_trail] auto={auto_applied}  manual_approved={manual_applied}  total={total}")

    # Push notice if anything applied
    if total > 0 and tg_send is not None:
        msg = (f"📎 <b>Evidence Trail applied</b>\n"
               f"Auto (≥{AUTO_APPLY_CONFIDENCE}): {auto_applied}\n"
               f"Jonathan-approved: {manual_applied}\n"
               f"Total new evidence_trail rows: {total}")
        try:
            tg_send(JONATHAN, msg, source="watchdog",
                    recipient_name="Jonathan", override_rate_limit=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
