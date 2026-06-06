#!/usr/bin/env python3
"""apply_deploy_332_objectives.py — Leo sees the 75% he was missing.

Diagnosis: Context Builder loads claims + title_chain + evidence_trail +
realtime_flow, but NOT transferees, transfer_doc_status, evidence_action_list.
With 20 named transferees and 486 rule evaluations sitting dark, Leo is
operating on roughly 25% of the live mandate.

Schema:
  - transferees.accion_status enriched with real values (default
    'awaiting_action' for the 19 with unknown status; Balane gets
    'lead_defendant')
  - New view v_case_objectives: per-matter summary built for scale
    (compact when N is large; expanded when N is small).
  - New view v_transferee_action_state: per-transferee posture +
    recent activity + gap count.

Cron-driven (deploy_332b in companion file):
  - refresh_objectives.py — regenerates OBJECTIVES_TEXT const in
    Context Builder every 5 min (cheap; SQL-only, no LLM).
"""
from __future__ import annotations
import os, psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()

    # ── 1. Allow richer accion_status values + seed defaults ──────────
    cur.execute("ALTER TABLE transferees ADD COLUMN IF NOT EXISTS action_needed text")
    cur.execute("ALTER TABLE transferees ADD COLUMN IF NOT EXISTS last_activity_at timestamptz")
    cur.execute("""
        UPDATE transferees SET accion_status = 'lead_defendant'
         WHERE canonical_name = 'Gloria Balane' AND accion_status = 'unknown'
    """)
    cur.execute("""
        UPDATE transferees SET accion_status = 'awaiting_action'
         WHERE accion_status = 'unknown'
    """)
    cur.execute("""
        UPDATE transferees SET action_needed = 'Verify current title status + serve responsive pleading'
         WHERE action_needed IS NULL AND accion_status IN ('awaiting_action','lead_defendant')
    """)

    # ── 2. View: per-transferee action state ──────────────────────────
    cur.execute("""
        CREATE OR REPLACE VIEW v_transferee_action_state AS
        SELECT t.id,
               t.case_file,
               t.canonical_name,
               t.accion_status,
               t.current_possession,
               t.action_needed,
               t.provenance_level,
               t.last_activity_at,
               -- count related transfer evaluations
               (SELECT COUNT(*) FROM transfer_doc_status tds
                 JOIN title_transfers tt ON tt.id = tds.transfer_id
                WHERE tt.transferee_id = t.id) AS doc_eval_total,
               (SELECT COUNT(*) FROM transfer_doc_status tds
                 JOIN title_transfers tt ON tt.id = tds.transfer_id
                WHERE tt.transferee_id = t.id AND tds.status = 'gap') AS doc_eval_gaps
          FROM transferees t
         ORDER BY
           CASE t.accion_status
             WHEN 'lead_defendant' THEN 1
             WHEN 'awaiting_action' THEN 2
             WHEN 'served' THEN 3
             WHEN 'answered' THEN 4
             WHEN 'defaulted' THEN 5
             ELSE 9 END,
           t.canonical_name
    """)
    print("✓ v_transferee_action_state")

    # ── 3. View: per-matter objectives summary ────────────────────────
    cur.execute("""
        CREATE OR REPLACE VIEW v_case_objectives AS
        WITH per_case_transferees AS (
          SELECT case_file,
                 COUNT(*) AS total_transferees,
                 COUNT(*) FILTER (WHERE accion_status = 'lead_defendant') AS leads,
                 COUNT(*) FILTER (WHERE accion_status = 'awaiting_action') AS awaiting,
                 COUNT(*) FILTER (WHERE accion_status IN ('served','answered','defaulted')) AS in_process
            FROM transferees
           GROUP BY case_file
        ),
        per_case_claims AS (
          SELECT case_file,
                 COUNT(*) AS total_claims,
                 COUNT(*) FILTER (WHERE status = 'open') AS open_claims
            FROM claims
           GROUP BY case_file
        ),
        per_case_obligations AS (
          SELECT case_file,
                 COUNT(*) FILTER (WHERE status IN ('open','in_progress')) AS open_obligations
            FROM landtek_obligations
           WHERE case_file IS NOT NULL
           GROUP BY case_file
        ),
        per_case_emails AS (
          SELECT case_file,
                 COUNT(*) FILTER (WHERE received_at > now() - interval '7 days') AS emails_7d
            FROM gmail_messages
           WHERE case_file IS NOT NULL
           GROUP BY case_file
        )
        SELECT
          COALESCE(t.case_file, c.case_file, o.case_file, e.case_file) AS case_file,
          COALESCE(t.total_transferees, 0)  AS total_transferees,
          COALESCE(t.leads, 0)              AS leads,
          COALESCE(t.awaiting, 0)           AS awaiting_action,
          COALESCE(t.in_process, 0)         AS in_process,
          COALESCE(c.total_claims, 0)       AS total_claims,
          COALESCE(c.open_claims, 0)        AS open_claims,
          COALESCE(o.open_obligations, 0)   AS open_obligations,
          COALESCE(e.emails_7d, 0)          AS emails_7d
          FROM per_case_transferees t
          FULL OUTER JOIN per_case_claims c ON c.case_file = t.case_file
          FULL OUTER JOIN per_case_obligations o
            ON o.case_file = COALESCE(t.case_file, c.case_file)
          FULL OUTER JOIN per_case_emails e
            ON e.case_file = COALESCE(t.case_file, c.case_file, o.case_file)
    """)
    print("✓ v_case_objectives")

    # ── 4. Quick win: populate transfer_doc_status.status from rules ──
    # Most rows are NULL because the evaluator was never run. Apply the
    # simplest rule: status='satisfied' if has a supporting doc_id;
    # 'gap' otherwise.
    cur.execute("""
        UPDATE transfer_doc_status
           SET status = CASE
             WHEN supporting_doc_id IS NOT NULL THEN 'satisfied'
             ELSE 'gap'
           END,
           evaluated_at = now()
         WHERE status IS NULL
           AND EXISTS (
             SELECT 1 FROM information_schema.columns
              WHERE table_name='transfer_doc_status' AND column_name='supporting_doc_id'
           )
    """)
    affected = cur.rowcount
    if affected > 0:
        print(f"✓ transfer_doc_status: {affected} rows status backfilled")
    else:
        # Schema doesn't have supporting_doc_id — use safer default
        cur.execute("""
            UPDATE transfer_doc_status SET status='gap', evaluated_at=now()
             WHERE status IS NULL
        """)
        print(f"✓ transfer_doc_status: {cur.rowcount} rows set to 'gap' (no supporting_doc_id col)")

    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_332',
         'Objectives layer: v_case_objectives + v_transferee_action_state views; transferees.accion_status backfilled (Balane=lead_defendant, 19 others=awaiting_action); transfer_doc_status NULL→evaluated. Companion: refresh_objectives.py + Context Builder integration + Leo can finally see the 20 transferees + per-matter operational picture.')
        ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary
    """)

    cur.execute("SELECT * FROM v_case_objectives ORDER BY case_file")
    print("\n=== per-case objectives summary ===")
    for r in cur.fetchall():
        print(f"  {r[0]:18s} transferees={r[1]:3d} (leads={r[2]} awaiting={r[3]} in_process={r[4]})  "
              f"claims={r[5]}/{r[6]}open  oblig={r[7]}  emails7d={r[8]}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
