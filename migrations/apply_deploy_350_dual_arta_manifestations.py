#!/usr/bin/env python3
"""deploy_350 — Two OP manifestations: ARTA-1210 + ARTA-0747.

Jonathan 2026-06-06 (operator-verified): there are two manifestations —
ARTA-1210 and ARTA-0747 — not a single ARTA manifestation obligation.

- obligation#2 → ARTA-1210 only (MWK-ARTA-1210)
- new obligation → ARTA-0747 (MWK-ARTA-0747)
- OP-PETITION + ARTA matter rows updated to reference both
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db

OBLIGATION_2 = (
    "File formal Manifestation re ARTA Resolution at OP docket "
    "(MWK-ARTA-1210, CTN SL-2026-0128-1210). "
    "Open deliverable — no verified blocker on record."
)

OBLIGATION_0747 = (
    "File formal Manifestation re ARTA OSCA/resolution at OP docket "
    "(MWK-ARTA-0747, CTN SL-2025-1021-0747). "
    "Open deliverable — no verified blocker on record."
)

VERIFIED_FACT = (
    "Operator-verified (2026-06-06): two separate OP manifestations pending — "
    "ARTA-1210 (obligation#2) and ARTA-0747 (new obligation). "
    "Do not collapse into one filing task."
)


def main():
    with db() as cur:
        cur.execute("""
            UPDATE landtek_obligations
               SET short_label = 'Manifestation re ARTA-1210 at OP docket',
                   description = %s,
                   matter_code = 'MWK-ARTA-1210',
                   status = 'open',
                   notes = COALESCE(notes, '') ||
                     E'\n[deploy_350] Scoped to ARTA-1210 only; ARTA-0747 split to separate obligation.',
                   updated_at = NOW()
             WHERE id = 2
        """, (OBLIGATION_2,))

        cur.execute("""
            SELECT id FROM landtek_obligations
             WHERE case_file = 'MWK-001'
               AND matter_code = 'MWK-ARTA-0747'
               AND short_label ILIKE '%manifestation%'
        """)
        existing = cur.fetchone()
        if existing:
            obl_0747_id = existing["id"]
            cur.execute("""
                UPDATE landtek_obligations
                   SET description = %s,
                       status = 'open',
                       priority = 4,
                       updated_at = NOW()
                 WHERE id = %s
            """, (OBLIGATION_0747, obl_0747_id))
        else:
            cur.execute("""
                INSERT INTO landtek_obligations (
                  client_code, case_file, matter_code, obligation_kind,
                  short_label, description, status, priority, source_kind
                ) VALUES (
                  'MWK-CV26360', 'MWK-001', 'MWK-ARTA-0747', 'deliverable',
                  'Manifestation re ARTA-0747 at OP docket',
                  %s, 'open', 4, 'court_filing'
                )
                RETURNING id
            """, (OBLIGATION_0747,))
            obl_0747_id = cur.fetchone()["id"]

        cur.execute("""
            UPDATE matters
               SET next_event = 'OP manifestation track (obligation#2 ARTA-1210 + obligation#' || %s || ' ARTA-0747)',
                   updated_at = NOW()
             WHERE matter_code = 'MWK-OP-PETITION'
        """, (str(obl_0747_id),))

        obl_tag = f"obligation#{obl_0747_id}"
        cur.execute("""
            UPDATE matters
               SET next_event = COALESCE(NULLIF(next_event, ''), '') ||
                     CASE WHEN next_event IS NULL OR next_event = '' THEN '' ELSE ' | ' END ||
                     %s,
                   updated_at = NOW()
             WHERE matter_code = 'MWK-ARTA-0747'
               AND (next_event IS NULL OR next_event NOT ILIKE %s)
        """, (f"OP manifestation ({obl_tag})", f"%{obl_tag}%"))

        for doc_id, mc in [(828, "MWK-ARTA-0747"), (624, "MWK-ARTA-1210")]:
            cur.execute("""
                UPDATE documents SET matter_code = %s
                 WHERE id = %s AND (matter_code IS NULL OR matter_code = '')
            """, (mc, doc_id))

        cur.execute("""
            INSERT INTO client_history
              (client_code, case_file, matter_code, event_date, event_datetime,
               event_kind, event_kind_canonical, source_table, source_id,
               who_from, what_summary, citation_ref, provenance, matter_codes)
            VALUES (
              'MWK-001', 'MWK-001', NULL,
              '2026-06-06', NOW(),
              'operator_correction', 'admin_instruction',
              'deploy_log', 'deploy_350',
              'Jonathan Zschoche (operator)', %s,
              'deploy_350 operator-verified', 'verified',
              ARRAY['MWK-ARTA-1210', 'MWK-ARTA-0747', 'MWK-OP-PETITION']::text[]
            )
            ON CONFLICT (source_table, source_id) DO UPDATE SET
              what_summary = EXCLUDED.what_summary,
              provenance = EXCLUDED.provenance,
              matter_codes = EXCLUDED.matter_codes
        """, (VERIFIED_FACT,))

        assessment_text = (
            f"Two separate OP manifestations are pending: ARTA-1210 (obligation#2) "
            f"and ARTA-0747 (obligation#{obl_0747_id})."
        )
        cur.execute("""
            INSERT INTO assessments
              (client_code, subject_type, subject_id, hat, assessment_text,
               implication, confidence, provenance_level, assessed_by)
            VALUES (
              'MWK-001', 'deploy_log', 'deploy_350', 'legal',
              %s,
              'Leo must track and report each manifestation by docket. '
              'Do not merge into one task or invent blockers.',
              'verified', 'verified', 'deploy_350_dual_manifestations'
            )
            ON CONFLICT (subject_type, subject_id, hat) DO UPDATE SET
              assessment_text = EXCLUDED.assessment_text,
              implication = EXCLUDED.implication,
              confidence = EXCLUDED.confidence,
              provenance_level = EXCLUDED.provenance_level,
              assessed_by = EXCLUDED.assessed_by
        """, (assessment_text,))

        deploy_summary = (
            f"Dual OP manifestations: obligation#2 scoped to ARTA-1210; "
            f"obligation#{obl_0747_id} for ARTA-0747. MWK-OP-PETITION + matters updated. "
            "refresh_mwk_pending_matters shows both manifestation obligations."
        )
        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_350', %s)
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """, (deploy_summary,))

    print(f"✓ deploy_350: dual manifestations — ARTA-1210 (#2) + ARTA-0747 (#{obl_0747_id})")


if __name__ == "__main__":
    main()