#!/usr/bin/env python3
"""deploy_349 — Strip unverified 'Barandon review' blocker (hallucination purge).

Source trace:
  - landtek_obligations#2 seeded deploy_326 with 'blocked pending Atty Barandon review'
    — NEVER operator-verified.
  - chat_notes#1186 (Sim agent) parroted that seed into operator channel as fact.
  - Sim messages #305/#438/#627 (999000002 fake 'Atty Barandon') fed the narrative.

Jonathan 2026-06-06: system hallucinating Barandon review on ARTA-1210 manifestation.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db

OBLIGATION_2_CLEAN = (
    "File formal Manifestation re ARTA Resolution at OP docket (MWK-ARTA-1210). "
    "Open deliverable — no verified blocker on record."
)


def main():
    with db() as cur:
        cur.execute("""
            UPDATE landtek_obligations
               SET description = %s,
                   status = 'open',
                   notes = COALESCE(notes, '') ||
                     E'\n[deploy_349] Removed unverified Barandon-review blocker (deploy_326 seed hallucination).',
                   updated_at = NOW()
             WHERE id = 2
        """, (OBLIGATION_2_CLEAN,))

        cur.execute("""
            UPDATE chat_notes
               SET archived = true,
                   provenance_level = 'hallucinated',
                   summary = 'SUPERSEDED deploy_349 — parroted unverified obligation#2 Barandon-review blocker'
             WHERE id = 1186
        """)

        cur.execute("""
            UPDATE chat_notes
               SET archived = true,
                   provenance_level = 'hallucinated'
             WHERE id IN (305, 438, 627)
               AND sender_id LIKE '999000%'
               AND content ILIKE '%Atty. Barandon%Manifestation%'
        """)

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_349',
              'Purge Barandon-review hallucination: obligation#2 description stripped to verified-safe text; chat_notes#1186 + sim-Barandon notes archived. Leo pending-matters now shows obligation short_label only (not seeded descriptions).'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    print("✓ deploy_349: unverified Barandon-review blocker removed")


if __name__ == "__main__":
    main()