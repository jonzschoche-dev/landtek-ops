#!/usr/bin/env python3
"""deploy_345 — Mediation capture + fraud-indicator reframe.

Fixes two field-test failures surfaced 2026-06-06:

1. Mediation HELD 2026-06-02 was backfilled to chat_notes#1208 but never reached
   client_history, case_deadlines, or matter spine. Telegram path should have
   logged it; closes the loop now.

2. fraud_indicators#14/#15 mislabeled T-52540 as posthumous *deed execution*.
   Jonathan correction: underlying deed executed pre-death (2016-09-29);
   subdivision + transfer *registration* at RD was post-death (2021-11-23).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db


MEDIATION_NOTE = """JUNE 2 MEDIATION (CV-26360, Heirs of MWK vs Balane et al.) — HELD.
Attendees: Jonathan Zschoche (AIF for Patricia Keesey Zschoche, plaintiff),
Atty. Bonifacio Jr. Barandon (plaintiff counsel), Efren M. Balane / Councilor Balane
(defendant), Engr. Erwin H. Balane (defendant).
NOTABLY ABSENT: Gloria H. Balane (primary defendant, TCT-079-2021002126 holder).
Outcome (settlement / impasse / continuance / next court date) still pending capture."""


def main():
    with db() as cur:
        # ── 1. Mediation held — close deadline, update matter ───────────
        cur.execute("""
            UPDATE case_deadlines
               SET status = 'completed',
                   notes = COALESCE(notes, '') || E'\n[deploy_345] Mediation HELD 2026-06-02 per chat_notes#1208. Attendees logged; outcome pending.',
                   updated_at = NOW()
             WHERE id = 3 AND case_file = 'MWK-001'
        """)

        cur.execute("""
            UPDATE matters
               SET current_stage = 'mediation_held_pending_outcome',
                   next_deadline = NULL,
                   next_event = 'Capture mediation outcome (settlement / impasse / continuance / next court date)',
                   stage_updated_at = '2026-06-02 13:30:00+00',
                   updated_at = NOW()
             WHERE matter_code = 'MWK-CV26360'
        """)

        # ── 2. client_history event from chat_notes#1208 ──────────────────
        cur.execute("""
            INSERT INTO client_history
              (client_code, case_file, matter_code, event_date, event_datetime,
               event_kind, event_kind_canonical, source_table, source_id,
               who_from, what_summary, citation_ref, provenance, matter_codes)
            VALUES (
              'MWK-001', 'MWK-001', 'MWK-CV26360',
              '2026-06-02', '2026-06-02 13:30:00+00',
              'chat_legal_strategy', 'court_event',
              'chat_notes', '1208',
              'Jonathan Zschoche', %s,
              'chat_notes#1208 (mediation held CV-26360)', 'verified',
              ARRAY['MWK-CV26360']::text[]
            )
            ON CONFLICT (source_table, source_id) DO UPDATE SET
              what_summary = EXCLUDED.what_summary,
              matter_code = EXCLUDED.matter_code,
              matter_codes = EXCLUDED.matter_codes,
              provenance = EXCLUDED.provenance
        """, (MEDIATION_NOTE[:500],))

        # ── 3. Assessment on mediation report ───────────────────────────
        cur.execute("""
            INSERT INTO assessments
              (client_code, subject_type, subject_id, hat, assessment_text,
               implication, confidence, provenance_level, assessed_by)
            VALUES (
              'MWK-001', 'chat_note', '1208', 'legal',
              'Court-annexed mediation for CV-26360 was HELD 2026-06-02 at RTC Daet Mediation Center. Plaintiff side: Jonathan Zschoche (AIF) + Atty. Barandon. Defendants present: Efren M. Balane, Engr. Erwin H. Balane. Gloria H. Balane (primary TCT-holder) absent.',
              'Pre-trial posture shifts from scheduling to outcome capture. Gloria''s absence may signal non-participation or separate counsel track. Void-chain settlement leverage unchanged; need recorded outcome before Aug 1 pre-trial.',
              'verified', 'verified', 'deploy_345_mediation_capture'
            )
            ON CONFLICT (subject_type, subject_id, hat) DO UPDATE SET
              assessment_text = EXCLUDED.assessment_text,
              implication = EXCLUDED.implication,
              confidence = EXCLUDED.confidence,
              provenance_level = EXCLUDED.provenance_level,
              assessed_by = EXCLUDED.assessed_by
        """)

        # ── 4. Reframe fraud indicators (deed pre-death; RD post-death) ─
        cur.execute("""
            UPDATE fraud_indicators
               SET indicator_type = 'post_death_registration',
                   description = 'IoT#43: RD Entry 2021003235 (registered 2021-11-23) presents DEED OF CONFIRMATION naming CESAR M. DELA FUENTE. Underlying sale deed executed 2016-09-29 (pre-death, IoT#56) under SPA revoked 2005. Registration at RD occurred 4+ years after Cesar died 2017-06-21. Fraud vector: post-death administrative completion of void chain — NOT posthumous deed execution.',
                   notes = 'Corrected deploy_345 per Jonathan: deed pre-death; subdivision/transfer registration post-death. matter: MWK-CV26360.',
                   severity = 'critical',
                   provenance_level = 'verified'
             WHERE id = 14
        """)
        cur.execute("""
            UPDATE fraud_indicators
               SET indicator_type = 'post_death_registration',
                   description = 'IoT#53: duplicate RD presentation of Entry 2021003235 DEED OF CONFIRMATION (2021-11-23). Same post-death registration cluster as IoT#43; underlying 2016 deed pre-death.',
                   notes = 'Corrected deploy_345 — duplicate entry irregularity + post-death registration framing.',
                   severity = 'high',
                   provenance_level = 'verified'
             WHERE id = 15
        """)

        cur.execute("""
            INSERT INTO fraud_indicators
              (doc_id, tct_number, indicator_type, description, source_quote,
               affected_entry, severity, confidence, provenance_level, notes)
            SELECT 48, 'T-52540', 'post_death_registration',
                   'IoT#46/#57: PARTITION-SUBDIVISION AGREEMENT (executed 2017-03-15) and transfer instruments presented at RD 2021-11-23 (Entry 2021003236) — after Cesar died 2017-06-21. Subdivision and transfer *registration* post-death completes Balane title derivation from pre-death void deed.',
                   'Entry No.: 2021003236 Date: November 23, 2021 — PARTITION SUBDIVISION AGREEMENT',
                   '2021003236', 'critical', 0.99, 'verified',
                   'deploy_345: Jonathan correction — subdivision/transfer registration post-death; deed execution pre-death. matter: MWK-CV26360.'
             WHERE NOT EXISTS (
               SELECT 1 FROM fraud_indicators
                WHERE tct_number = 'T-52540'
                  AND affected_entry = '2021003236'
                  AND indicator_type = 'post_death_registration'
             )
        """)

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_345',
              'Mediation capture: case_deadlines#3 completed, matter MWK-CV26360 stage retained (outcome pending), client_history+assessment from chat_notes#1208. Fraud reframe: #14/#15 posthumous_execution → post_death_registration (deed pre-death 2016, RD registration post-death 2021); new indicator on Entry 2021003236 subdivision/transfer cluster. client_history_scan now ingests high-importance chat_notes.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    print("✓ deploy_345: mediation logged to spine")
    print("✓ deploy_345: fraud indicators reframed (deed pre-death / registration post-death)")


if __name__ == "__main__":
    main()