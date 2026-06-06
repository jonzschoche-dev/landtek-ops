#!/usr/bin/env python3
"""deploy_347 — Hard-facts discipline for CV-26360 + mediation impasse capture.

Jonathan correction (2026-06-06): too much inference. Agent must act on hard facts.

1. chat_notes#1209 (Telegram) = verified mediation outcome: impasse, Princess+Erwin
   only, proceeds to trial.
2. chat_notes#1208 archived — superseded inference (wrong attendees, no outcome).
3. Matter stage → mediation_impasse_trial_pending.
4. client_history + assessment rewritten from #1209 only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db

IMPASSE_NOTE = (
    "Mediation Civil Case 26-360 HELD — IMPASSE. "
    "Attended: Princess Balane Torralba and Engr. Erwin H. Balane only "
    "(Jonathan not present). Parties agreed to disagree. Case proceeds to trial. "
    "Source: chat_notes#1209 telegram_msg=3866 (operator-verified)."
)


def main():
    with db() as cur:
        # ── Supersede inferred mediation note ─────────────────────────────
        cur.execute("""
            UPDATE chat_notes
               SET archived = true,
                   provenance_level = 'hallucinated',
                   summary = 'SUPERSEDED by chat_notes#1209 — inferred attendees/outcome wrong'
             WHERE id = 1208
        """)

        cur.execute("""
            UPDATE chat_notes
               SET provenance_level = 'verified',
                   related_case = 'MWK-001',
                   topic = 'legal_strategy',
                   importance = 5,
                   sender_name = COALESCE(NULLIF(sender_name, ''), 'Jonathan Zschoche')
             WHERE id = 1209
        """)

        # ── Matter spine — hard facts only ────────────────────────────────
        cur.execute("""
            UPDATE matters
               SET current_stage = 'mediation_impasse_trial_pending',
                   next_event = 'Trial — mediation impasse; await schedule / pretrial (Aug 1)',
                   next_deadline = '2026-08-01',
                   stage_updated_at = NOW(),
                   stage_notes = %s,
                   updated_at = NOW()
             WHERE matter_code = 'MWK-CV26360'
        """, (IMPASSE_NOTE,))

        # ── client_history: replace 1208 with 1209 ────────────────────────
        cur.execute("""
            DELETE FROM client_history
             WHERE source_table = 'chat_notes' AND source_id = '1208'
        """)
        cur.execute("""
            INSERT INTO client_history
              (client_code, case_file, matter_code, event_date, event_datetime,
               event_kind, event_kind_canonical, source_table, source_id,
               who_from, what_summary, citation_ref, provenance, matter_codes)
            VALUES (
              'MWK-001', 'MWK-001', 'MWK-CV26360',
              '2026-06-02', '2026-06-06 13:04:24+00',
              'chat_legal_strategy', 'court_event',
              'chat_notes', '1209',
              'Jonathan Zschoche (via Telegram)', %s,
              'chat_notes#1209 tg_msg=3866', 'verified',
              ARRAY['MWK-CV26360']::text[]
            )
            ON CONFLICT (source_table, source_id) DO UPDATE SET
              what_summary = EXCLUDED.what_summary,
              provenance = EXCLUDED.provenance,
              matter_code = EXCLUDED.matter_code
        """, (IMPASSE_NOTE,))

        cur.execute("""
            INSERT INTO assessments
              (client_code, subject_type, subject_id, hat, assessment_text,
               implication, confidence, provenance_level, assessed_by)
            VALUES (
              'MWK-001', 'chat_note', '1209', 'legal',
              'CV-26360 mediation resulted in IMPASSE (agreed to disagree). '
              'Defendant side present: Princess Balane Torralba and Engr. Erwin H. Balane. '
              'Jonathan was not in attendance. Case proceeds to trial.',
              'Pre-trial/trial prep is now the operative track. '
              'Do not narrate settlement path. Gloria attendance status not in this report — do not infer.',
              'verified', 'verified', 'deploy_347_hard_facts'
            )
            ON CONFLICT (subject_type, subject_id, hat) DO UPDATE SET
              assessment_text = EXCLUDED.assessment_text,
              implication = EXCLUDED.implication,
              confidence = EXCLUDED.confidence,
              provenance_level = EXCLUDED.provenance_level,
              assessed_by = EXCLUDED.assessed_by
        """)

        cur.execute("""
            DELETE FROM assessments
             WHERE subject_type = 'chat_note' AND subject_id = '1208'
        """)

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_347',
              'Hard-facts discipline: mediation impasse from verified chat_notes#1209; #1208 archived as hallucinated inference. Matter MWK-CV26360 → mediation_impasse_trial_pending. Leo context gets MWK_CV26360_HARD_FACTS_TEXT (verified-only). Operator Telegram → provenance verified. Evidence facts refresh shows verified exhibits only.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    print("✓ deploy_347: CV-26360 on hard facts — mediation impasse logged, inference archived")


if __name__ == "__main__":
    main()