#!/usr/bin/env python3
"""Deploy 258 — Arnis / martial-arts → Allan Inocalla / Paracale-001.

User correction (2026-05-21): "all arnis or martial arts related files
are related to our client allan inocalla".

The deploy_244 LLM batch flagged ~9 martial-arts docs as 'flag_unrelated'
at ≥0.95 confidence. They're actually Inocalla-family Paracale-client
material — Sport Arnis Canada, Camarines Norte Barangay Tanod training
programs, Datu Shishir Inocalla cultural exchange proposals, Kalisteniks
syllabi from "Master Shishir" + "GM Jesus Inocalla".

Three pieces:

A) Create new matter PAR-MARTIAL-ARTS — Allan Inocalla family martial-arts
   business / Arnis cultural advocacy. Distinct from PAR's legal matters
   (mining disputes, estate cases, title-chain work).

B) Reclassify 9 martial-arts docs:
     doc#481, 486, 487, 488, 489, 491, 492, 493, 536
     → case_file='Paracale-001', matter_code='PAR-MARTIAL-ARTS'

   Bonus: doc#514 → PAR-CV13-131220 (Jesus V. Inocalla et al. Civil Case
   13-131220 — RTC Branch 15 Manila). Was case_file='Unknown'.

C) Consolidate Inocalla family entities + populate PAR keystone_entities:
     Allan V. Inocalla     canonical #7983 (19 mentions)
       absorb: #8091 'Allan Inocalla', #8147 'Allan Villafria Inocalla',
               #8320 'Allan Inocalla y Villafria'
     Shishir Allan Inocalla canonical #8708
       absorb: #8062 'Shishir Inocalla', #8776 'Datu Shishir Inocalla'
       NOTE: Shishir may be Allan's Datu/martial-arts name; kept separate
       canonical entity for now pending user clarification.
     Jesus V. Inocalla     canonical #8120 (7 mentions)
       absorb: #8158 'Jesus Inocalla'

   Supersede the corresponding LLM flag_unrelated proposals.

Idempotent. Audited via app.actor='jonathan_deploy_258'.
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

MARTIAL_DOCS = [481, 486, 487, 488, 489, 491, 492, 493, 536]
BONUS_DOC_514 = 514  # Inocalla civil case 13-131220

CONSOLIDATIONS = [
    # (alias_id, canonical_id, alias_name → canonical_name)
    (8091, 7983, "Allan Inocalla → Allan V. Inocalla"),
    (8147, 7983, "Allan Villafria Inocalla → Allan V. Inocalla"),
    (8320, 7983, "Allan Inocalla y Villafria → Allan V. Inocalla"),
    (8062, 8708, "Shishir Inocalla → Shishir Allan Inocalla"),
    (8776, 8708, "Datu Shishir Inocalla → Shishir Allan Inocalla"),
    (8158, 8120, "Jesus Inocalla → Jesus V. Inocalla"),
]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_258'")

    print("Deploy 258 — Inocalla martial-arts → PAR")
    print("=" * 60)

    # A) Create PAR-MARTIAL-ARTS matter
    cur.execute("""
        INSERT INTO matters (matter_code, client_code, matter_type, title, description, status)
        VALUES ('PAR-MARTIAL-ARTS', 'PAR', 'business',
                'Inocalla family Arnis / Filipino martial arts business',
                'Sport Arnis Canada, Maharlika Filipino Martial Arts World Federation, '
                'Barangay Tanod training programs, Datu Shishir Inocalla cultural advocacy. '
                'Includes GM Shishir Inocalla + GM Jesus Inocalla materials.',
                'active')
        ON CONFLICT (matter_code) DO NOTHING
        RETURNING matter_code
    """)
    r = cur.fetchone()
    if r:
        print(f"  ✓ Created matter: {r['matter_code']}")
    else:
        print("  · PAR-MARTIAL-ARTS already exists (no-op)")

    # B) Reclassify martial-arts docs
    print(f"\n  Reclassify {len(MARTIAL_DOCS)} martial-arts docs → PAR-MARTIAL-ARTS:")
    for doc_id in MARTIAL_DOCS:
        cur.execute("""
            UPDATE documents
               SET case_file = 'Paracale-001', matter_code = 'PAR-MARTIAL-ARTS'
             WHERE id = %s
               AND (case_file IS DISTINCT FROM 'Paracale-001' OR matter_code IS DISTINCT FROM 'PAR-MARTIAL-ARTS')
             RETURNING id, case_file, matter_code
        """, (doc_id,))
        r = cur.fetchone()
        if r:
            print(f"    ✓ doc#{r['id']}: case_file={r['case_file']!r} matter_code={r['matter_code']!r}")

    # Bonus: doc#514 → PAR-CV13-131220
    cur.execute("""
        UPDATE documents
           SET case_file = 'Paracale-001', matter_code = 'PAR-CV13-131220'
         WHERE id = %s
           AND (case_file IS DISTINCT FROM 'Paracale-001' OR matter_code IS DISTINCT FROM 'PAR-CV13-131220')
         RETURNING id, case_file, matter_code
    """, (BONUS_DOC_514,))
    r = cur.fetchone()
    if r:
        print(f"\n  Bonus: doc#{r['id']} (Inocalla civil case): "
              f"case_file={r['case_file']!r} matter_code={r['matter_code']!r}")

    # Supersede the LLM flag_unrelated proposals for these docs
    all_docs = MARTIAL_DOCS + [BONUS_DOC_514]
    cur.execute("""
        UPDATE doc_classification_proposals
           SET status = 'superseded',
               reviewed_at = now(),
               reviewed_by = 'jonathan_deploy_258',
               review_notes = 'Misclassified by LLM as flag_unrelated. Per user correction 2026-05-21: '
                              'all arnis/martial-arts docs are Allan Inocalla / Paracale client material.'
         WHERE doc_id = ANY(%s)
           AND status IN ('proposed', 'needs_manual_review')
         RETURNING id, doc_id
    """, (all_docs,))
    supn = cur.fetchall()
    print(f"\n  Superseded {len(supn)} LLM proposals: {[(r['id'], r['doc_id']) for r in supn]}")

    # C) Entity consolidations
    print("\n  Inocalla family entity consolidations:")
    for alias_id, canonical_id, label in CONSOLIDATIONS:
        cur.execute("""
            UPDATE entities
               SET canonical_id = %s,
                   notes = COALESCE(notes || E'\n', '') ||
                           '[deploy_258] consolidated: ' || %s
             WHERE id = %s AND (canonical_id IS NULL OR canonical_id != %s)
             RETURNING id
        """, (canonical_id, label, alias_id, canonical_id))
        r = cur.fetchone()
        if r:
            print(f"    ✓ #{alias_id} → canonical=#{canonical_id}  [{label}]")
        else:
            print(f"    · #{alias_id} already consolidated to #{canonical_id} (no-op)")

    conn.commit()
    print("\n  ✓ COMMITTED")

    # Recap
    cur.execute("""
        SELECT id, case_file, matter_code, LEFT(extracted_text, 40) AS head
          FROM documents WHERE id = ANY(%s) ORDER BY id
    """, (MARTIAL_DOCS + [BONUS_DOC_514],))
    print("\n  Final doc state:")
    for r in cur.fetchall():
        print(f"    doc#{r['id']:>3d}  case_file={r['case_file']!r:<14} matter_code={r['matter_code']!r}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
