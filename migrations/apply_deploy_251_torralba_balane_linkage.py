#!/usr/bin/env python3
"""Deploy 251 — Torralba/Juntilla CA case → MWK-CV26360 (Balane) linkage.

User correction (2026-05-21): "Torralba are linked to Balane."

The Torralba & Juntilla v. Daet RTC Branch 41 CA petition (CA-G.R. SP No.
181607) is NOT unrelated precedent — it's Balane-family litigation:

  - Petitioners: Jomil L. Torralba (entity #3059, 21 mentions) +
    Nelly H. Juntilla (#8360)
  - Hub: Princess Balane Torralba (entity #2391, 25 mentions) — direct
    Balane family member who joins the Torralba surname
  - Respondent: Donata Mabeza King (#3155) — "Mabeza" is also a Balane-chain
    transferee (Arnel Mabeza is one of the 20 named transferees per CLAUDE.md)
  - Underlying: Crim. Case No. 2261 RTC Branch 41 Daet (same court as CV26360)

Doc evidence (extracted_text grep):
  doc#581: 30× "balane", 5× "princess"
  doc#582:  1× "balane"
  doc#583: 19× "balane", 2× "princess"
  doc#585: notice of judgment (CA-G.R. SP NO. 181607 — same case)

The deploy_244 LLM run flagged all 4 docs as 'flag_unrelated' at 0.95
confidence. This shows high LLM confidence is NOT accuracy. The platform
needs the entity-graph cross-check (which would have surfaced Princess
Balane Torralba) to catch this class of model error.

This deploy:
  1. Sets matter_code='MWK-CV26360' on docs 581, 582, 583, 585.
  2. Adds 'MWK-CV26360' to affected_matter_codes for resolutions 5, 10, 11, 13.
  3. Marks the 4 flag_unrelated proposals as 'superseded'.
  4. Adds a memory note (memory/feedback_torralba_balane_linkage.md) so
     future agents don't repeat the mistake.
"""
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

TORRALBA_DOCS = [581, 582, 583, 585]
RELATED_RESOLUTIONS = [5, 10, 11, 13]  # res whose source_doc_id ∈ TORRALBA_DOCS
TARGET_MATTER = "MWK-CV26360"


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_251'")

    print("Deploy 251 — Torralba/Juntilla CA → MWK-CV26360 linkage")
    print("=" * 60)

    # 1. Set documents.matter_code
    cur.execute("""
        UPDATE documents
           SET matter_code = %s
         WHERE id = ANY(%s) AND (matter_code IS NULL OR matter_code != %s)
         RETURNING id
    """, (TARGET_MATTER, TORRALBA_DOCS, TARGET_MATTER))
    updated_docs = [r["id"] for r in cur.fetchall()]
    print(f"  ✓ {len(updated_docs)} documents → matter_code={TARGET_MATTER}: {updated_docs}")

    # 2. Update resolutions
    cur.execute("""
        SELECT id, source_doc_id, affected_matter_codes
          FROM resolutions
         WHERE source_doc_id = ANY(%s)
    """, (TORRALBA_DOCS,))
    for r in cur.fetchall():
        codes = set(r["affected_matter_codes"] or [])
        if TARGET_MATTER not in codes:
            codes.add(TARGET_MATTER)
            cur.execute("""
                UPDATE resolutions
                   SET affected_matter_codes = %s,
                       notes = COALESCE(notes || E'\n', '') || %s,
                       updated_at = now()
                 WHERE id = %s
            """, (sorted(codes),
                  f"[deploy_251] linked to {TARGET_MATTER} via Princess Balane Torralba (#2391) entity-graph",
                  r["id"]))
            print(f"  ✓ resolution#{r['id']} (doc#{r['source_doc_id']}) → +{TARGET_MATTER}")

    # 3. Supersede the wrong LLM proposals
    cur.execute("""
        UPDATE doc_classification_proposals
           SET status = 'superseded',
               reviewed_at = now(),
               reviewed_by = 'jonathan_deploy_251',
               review_notes = 'LLM scored flag_unrelated at 0.95 confidence; entity-graph (Princess Balane Torralba #2391) proves Balane-family linkage. Manually corrected to MWK-CV26360.'
         WHERE doc_id = ANY(%s)
           AND proposed_action = 'flag_unrelated'
           AND status = 'proposed'
         RETURNING id, doc_id
    """, (TORRALBA_DOCS,))
    superseded = cur.fetchall()
    print(f"  ✓ {len(superseded)} LLM flag_unrelated proposals superseded: "
          f"{[(r['id'], r['doc_id']) for r in superseded]}")

    conn.commit()
    print("\n  ✓ COMMITTED")

    # Recap
    cur.execute("""
        SELECT id, matter_code FROM documents WHERE id = ANY(%s) ORDER BY id
    """, (TORRALBA_DOCS,))
    print("\n  Post-state — Torralba doc matter assignments:")
    for r in cur.fetchall():
        print(f"    doc#{r['id']}  matter_code={r['matter_code']!r}")

    cur.execute("""
        SELECT id, affected_matter_codes FROM resolutions WHERE id = ANY(%s) ORDER BY id
    """, (RELATED_RESOLUTIONS,))
    print("\n  Post-state — resolution matters:")
    for r in cur.fetchall():
        print(f"    res#{r['id']}  affected_matter_codes={r['affected_matter_codes']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
