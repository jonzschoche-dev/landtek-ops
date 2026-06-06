#!/usr/bin/env python3
"""deploy_346 — Link 2005 Cesar SPA revocation to Ida Buenaventura SPA (doc#91).

Jonathan correction: the revocation is IN the Ida Buenaventura SPA itself —
'Any Special Power of Attorney in favor of any person other than IDA BUENAVENTURA
is hereby disowned and should be deemed without force and effect.' (August 2005).

Closes evidence_trail gap on claim#3 (0 primary → doc#91 primary).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db

DISOWN_QUOTE = (
    "Any Special Power of Attorney in favor of any person other than "
    "IDA BUENAVENTURA is hereby disowned and should be deemed without force and effect."
)


def _insert_trail(cur, claim_id, doc_id, relation, weight, narrative, provenance="verified"):
    cur.execute("""
        INSERT INTO evidence_trail
          (claim_id, supporting_doc_id, relation_kind, weight, narrative,
           provenance_level, added_by)
        SELECT %s, %s, %s, %s, %s, %s, 'deploy_346_ida_spa_revocation'
         WHERE NOT EXISTS (
           SELECT 1 FROM evidence_trail
            WHERE claim_id = %s AND supporting_doc_id = %s AND relation_kind = %s
         )
    """, (claim_id, doc_id, relation, weight, narrative, provenance,
          claim_id, doc_id, relation))


def main():
    with db() as cur:
        # ── claim#3: Cesar SPA revoked 2005 ─────────────────────────────
        _insert_trail(
            cur, 3, 91, "proves", "primary",
            f"Ida Buenaventura SPA (doc#91, 2005-08-01): heirs disown all SPAs "
            f"not in favor of Ida Buenaventura — revokes Cesar de la Fuente's "
            f"1992 SPA. Source quote: \"{DISOWN_QUOTE}\"",
        )
        _insert_trail(
            cur, 3, 292, "corroborates", "strong",
            "Notarized Ida Buenaventura SPA copy (doc#292, 2005-08-15 LA consulate) "
            "contains identical disown clause revoking all non-Ida SPAs including Cesar's.",
        )
        _insert_trail(
            cur, 3, 430, "corroborates", "strong",
            "Exhibit F in CV-26360 complaint (doc#430) reproduces August 15 2005 "
            "Ida Buenaventura SPA with disown clause.",
        )
        _insert_trail(
            cur, 3, 441, "corroborates", "moderate",
            "Judicial Affidavit doc#441 testifies SPA to Cesar revoked 2005-08-15; "
            "now backed by primary Ida Buenaventura SPA instrument.",
        )

        # ── claim#2: void chain depends on SPA revocation ─────────────────
        _insert_trail(
            cur, 2, 91, "proves", "strong",
            "Ida Buenaventura SPA (doc#91) disowns Cesar's SPA — foundational "
            "basis for void-chain theory on T-52540 / T-079-2021002127.",
        )

        cur.execute("""
            UPDATE claims
               SET notes = 'Primary: Ida Buenaventura SPA doc#91 (disown clause revokes Cesar SPA). '
                           'Corroboration: doc#292, doc#430 (Aug 15 2005), doc#441 (testimonial).',
                   updated_at = NOW()
             WHERE id = 3
        """)

        cur.execute("""
            UPDATE fraud_indicators
               SET description = REPLACE(description,
                     'SPA revoked 2005',
                     'SPA revoked 2005 via Ida Buenaventura SPA doc#91 disown clause'),
                   notes = COALESCE(notes, '') ||
                     E'\n[deploy_346] SPA revocation primary = Ida Buenaventura SPA doc#91.'
             WHERE description ILIKE '%SPA revoked 2005%'
        """)

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_346',
              'SPA revocation keystone: evidence_trail links claim#3 to Ida Buenaventura SPA doc#91 (primary disown clause), doc#292/#430 corroboration, doc#441 testimonial. claim#2 void-chain also linked to doc#91. Closes missing_primary_instrument gap on Cesar_SPA_revoked_2005.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    print("✓ deploy_346: Ida Buenaventura SPA doc#91 linked as primary for Cesar SPA revocation")


if __name__ == "__main__":
    main()