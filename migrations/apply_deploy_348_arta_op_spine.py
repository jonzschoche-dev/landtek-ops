#!/usr/bin/env python3
"""deploy_348 — ARTA + OP matter spine visible to Leo.

- Register MWK-OP-PETITION (Executive Secretary supervisory review, doc#702/#703)
- Link open obligations to matter_codes
- Tag OP petition docs on documents.matter_code
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db


def main():
    with db() as cur:
        cur.execute("""
            INSERT INTO matters (
              matter_code, client_code, case_file, matter_type, title, description,
              status, current_stage, court_or_agency, docket_number,
              next_event, lead_counsel, stage_updated_at
            ) VALUES (
              'MWK-OP-PETITION', 'MWK-001', 'MWK-001', 'administrative',
              'Petition for Supervisory Review — Executive Secretary (ARTA resolutions)',
              'Petition to the Office of the President / Executive Secretary regarding '
              'ARTA resolutions (filed 2026-05-05). Primary: doc#702, doc#703. '
              'Related ARTA dockets: -0690/-0792 (resolved), -1210 OP Bagong Pilipinas track.',
              'active', 'petition_filed_awaiting_op_action',
              'Office of the President / Executive Secretary',
              'OP-ARTA-SUPERVISORY-2026-05-05',
              'Track OP docket response; coordinate Manifestation re ARTA-1210 (obligation#2)',
              'Jonathan Zschoche',
              NOW()
            )
            ON CONFLICT (matter_code) DO UPDATE SET
              title = EXCLUDED.title,
              description = EXCLUDED.description,
              current_stage = EXCLUDED.current_stage,
              next_event = EXCLUDED.next_event,
              status = 'active',
              updated_at = NOW()
        """)

        cur.execute("""
            UPDATE landtek_obligations SET matter_code = 'MWK-ARTA-1210', updated_at = NOW()
             WHERE id = 2 AND case_file = 'MWK-001'
        """)
        cur.execute("""
            UPDATE landtek_obligations SET matter_code = 'MWK-CV26360', updated_at = NOW()
             WHERE id IN (1, 3, 4) AND case_file = 'MWK-001'
        """)
        for doc_id, mc in [(702, "MWK-OP-PETITION"), (703, "MWK-OP-PETITION"), (972, "MWK-ARTA-1210")]:
            cur.execute("""
                UPDATE documents SET matter_code = %s
                 WHERE id = %s AND (matter_code IS NULL OR matter_code = '')
            """, (mc, doc_id))

        cur.execute("""
            UPDATE matters
               SET court_or_agency = 'ARTA Southern Luzon → Office of the President (Bagong Pilipinas)',
                   next_event = COALESCE(next_event, '') ||
                     ' | OP supervisory track via MWK-OP-PETITION (doc#702/#703)',
                   updated_at = NOW()
             WHERE matter_code = 'MWK-ARTA-1210'
               AND next_event NOT ILIKE '%MWK-OP-PETITION%'
        """)

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_348',
              'ARTA/OP spine: MWK-OP-PETITION matter registered; obligations linked to matter_codes; doc#702/703/972 tagged. refresh_mwk_pending_matters.py → MWK_PENDING_MATTERS_TEXT in Leo Context Builder. Cron for pending_matters + mwk_priorities.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    print("✓ deploy_348: ARTA + OP matters on spine")


if __name__ == "__main__":
    main()