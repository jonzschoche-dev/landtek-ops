#!/usr/bin/env python3
"""deploy_351 — Email-derived clues for dual ARTA OP manifestations.

Hard facts from gmail corpus (operator-ingested, provenance verified):
  - gmail#38220 (2026-05-26): ARTA-0747 Resolution NOC; resolution dated 2026-04-29;
    15-day OP appeal → due 2026-06-10 from notice.
  - doc#967 = attached resolution (tag MWK-ARTA-0747).

1210 thread already in client_history (#42, #7919, #20132); Del Rosario doc#972
points complainant to supervisory authority (OP) for substantive RPT relief.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db

DEADLINE_0747 = (
    "OP Notice of Appeal / Manifestation — ARTA-0747 (CTN SL-2025-1021-0747). "
    "Resolution dated 2026-04-29; NOC received gmail#38220 on 2026-05-26. "
    "15 days from notice per 2023 ARTA Rules."
)

ASSESSMENT = (
    "Email clues (May 15–26): ARTA-1210 NOC gmail#42 (resolution 2026-05-13); "
    "Jonathan ARTA-side clarification gmail#7919 (2026-05-18, not MR); "
    "Del Rosario response gmail#20132/doc#972 (2026-05-21) maintains closure but "
    "directs substantive RPT relief to supervisory authority (OP). "
    "ARTA-0747 NOC gmail#38220 (2026-05-26, resolution 2026-04-29) — separate "
    "15-day OP clock; no reply in thread yet. doc#967 = 0747 resolution PDF."
)


def main():
    with db() as cur:
        cur.execute("""
            UPDATE documents
               SET matter_code = 'MWK-ARTA-0747',
                   case_file = COALESCE(case_file, 'MWK-001'),
                   doc_role = COALESCE(doc_role, 'order_resolution'),
                   execution_status = COALESCE(NULLIF(execution_status, ''), 'government_issued')
             WHERE id = 967
        """)

        cur.execute("""
            UPDATE gmail_messages
               SET matter_codes = ARRAY['MWK-ARTA-0747']::text[],
                   client_code = COALESCE(client_code, 'MWK-001'),
                   relevance_status = 'matter_linked'
             WHERE id = 38220
               AND NOT (matter_codes @> ARRAY['MWK-ARTA-0747']::text[])
        """)

        cur.execute("""
            SELECT id FROM case_deadlines
             WHERE case_file = 'MWK-001'
               AND title = 'ARTA-0747 OP appeal/manifestation (15 days from NOC)'
               AND due_date = '2026-06-10'
               AND status <> 'cancelled'
        """)
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO case_deadlines (
                  case_file, title, description, due_date, deadline_type,
                  source_doc_id, status, confidence, created_by, notes
                ) VALUES (
                  'MWK-001',
                  'ARTA-0747 OP appeal/manifestation (15 days from NOC)',
                  %s,
                  '2026-06-10',
                  'court_filing',
                  967,
                  'pending',
                  1.0,
                  'deploy_351_email_clues',
                  'Source: gmail#38220 received 2026-05-26; resolution dated 2026-04-29.'
                )
            """, (DEADLINE_0747,))

        cur.execute("""
            UPDATE matters
               SET next_deadline = '2026-06-10',
                   next_event = 'OP appeal/manifestation re Resolution 2026-04-29 (gmail#38220 NOC 2026-05-26; doc#967)',
                   current_stage = 'resolution_noc_op_appeal_window',
                   stage_updated_at = NOW(),
                   updated_at = NOW()
             WHERE matter_code = 'MWK-ARTA-0747'
        """)

        cur.execute("""
            INSERT INTO assessments
              (client_code, subject_type, subject_id, hat, assessment_text,
               implication, confidence, provenance_level, assessed_by)
            VALUES (
              'MWK-001', 'assertion', 'arta_manifestation_email_clues', 'legal',
              %s,
              'Track 1210 and 0747 on separate clocks. 0747 OP window closes 2026-06-10. '
              '1210: ARTA record closed per doc#972; OP track may already be in flight '
              '(doc#974/#975 photos 2026-05-27 — confirm filing status with operator).',
              'verified', 'verified', 'deploy_351_email_clues'
            )
            ON CONFLICT (subject_type, subject_id, hat) DO UPDATE SET
              assessment_text = EXCLUDED.assessment_text,
              implication = EXCLUDED.implication,
              provenance_level = EXCLUDED.provenance_level,
              assessed_by = EXCLUDED.assessed_by
        """, (ASSESSMENT,))

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_351',
              'Email clues ingested: gmail#38220 → ARTA-0747 OP deadline 2026-06-10; doc#967 tagged; '
              'assessment summarizes May 15–26 1210/0747 email thread for Leo.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    print("✓ deploy_351: ARTA manifestation email clues on spine (0747 deadline 2026-06-10)")


if __name__ == "__main__":
    main()