#!/usr/bin/env python3
"""Deploy 275 — Singson investor meeting (May 26 2026) — classify + fix MMK conflation.

Jonathan met today with Chavit Singson, Michael Marcos Keon (MMK), and
Allan Inocalla re: investment in Allan's Paracale mining property. He
uploaded 3 docs via Telegram during the chat. Two landed as UNCLASSIFIED.

Leo subsequently conflated "MMK" (Michael Marcos Keon) with "MWK" (Mary
Worrick Keesey) and logged chat_note #156 claiming the docs were "executed
by Allan Inocalla AND MWK" — wrong. Jonathan corrected immediately: this
is Allan Inocalla / Paracale-001 territory, NOT MWK estate.

This deploy:

  A. Reclassify the 2 UNCLASSIFIED docs:
       doc#962 (Paracale Gold Partnership MoU to Chavit Singson) → Paracale-001 / PAR-CAPACUAN
       doc#963 (Letter of Endorsement to Singson re: Allan)       → Paracale-001 / PAR-CAPACUAN

  B. Create new entities surfacing in these docs:
       - Luis "Chavit" C. Singson  (investor counterparty)
       - LCS Group of Companies     (his corporate group)
       - Satrap Mining              (his mining-side vehicle)
       - Michael Marcos Keon (MMK)  (third party at the meeting)

  C. Correct the conflated chat_note #156: replace "MWK (Mary Worrick Keesey)"
     with "Michael Marcos Keon (MMK)".

  D. Memory rule (filed separately): MMK ≠ MWK invariant.

Idempotent. Audited via app.actor='jonathan_deploy_275'.
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

DOC_ASSIGNMENTS = [
    (962, "Paracale-001", "PAR-CAPACUAN",
     "Paracale Gold Partnership Memorandum of Proposed Terms — submitted 2026-05-26 to Luis 'Chavit' Singson / LCS Group / Satrap Mining re: ~250ha Paracale property"),
    (963, "Paracale-001", "PAR-CAPACUAN",
     "Letter of Endorsement to Mr. Luis 'Chavit' Singson dated 2026-05-26 endorsing Allan Inocalla and the Paracale Gold Partnership"),
]

NEW_ENTITIES = [
    # canonical_name, entity_type, provenance_level, role
    ("Luis Chavit C. Singson", "person", "verified",
     "Philippine politician / businessman; LCS Group of Companies & Satrap Mining; investor counterparty for Paracale Gold Partnership (introduced 2026-05-26)"),
    ("LCS Group of Companies", "organization", "verified",
     "Chavit Singson's corporate holding group (referenced doc#962, #963)"),
    ("Satrap Mining", "organization", "verified",
     "Mining-side vehicle of the LCS Group; counterparty in proposed Paracale Gold Partnership (doc#962)"),
    ("Michael Marcos Keon", "person", "verified",
     "MMK — third party at the Jonathan-Singson-Inocalla 2026-05-26 investor meeting. Not to be confused with MWK (Mary Worrick Keesey)."),
]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_275'")

    print("Deploy 275 — Singson investor meeting + MMK/MWK conflation fix")
    print("=" * 60)

    # A) Reclassify the 2 UNCLASSIFIED docs
    print("\n  A) Reclassify Singson meeting docs:")
    for doc_id, case_file, matter_code, rationale in DOC_ASSIGNMENTS:
        cur.execute("""
            UPDATE documents
               SET case_file = %s, matter_code = %s
             WHERE id = %s AND (case_file IS DISTINCT FROM %s OR matter_code IS DISTINCT FROM %s)
             RETURNING id, case_file, matter_code
        """, (case_file, matter_code, doc_id, case_file, matter_code))
        r = cur.fetchone()
        if r:
            print(f"    ✓ doc#{r['id']}: case_file={r['case_file']!r} matter_code={r['matter_code']!r}")
            print(f"        [{rationale}]")

    # B) Create new entities (insert if not exists)
    print("\n  B) Create entities for Singson, LCS, Satrap, MMK:")
    for canonical_name, entity_type, provenance, role in NEW_ENTITIES:
        cur.execute("SELECT id FROM entities WHERE canonical_name = %s LIMIT 1", (canonical_name,))
        existing = cur.fetchone()
        if existing:
            print(f"    · already exists #{existing['id']}  {canonical_name}")
            continue
        cur.execute("""
            INSERT INTO entities (canonical_name, entity_type, provenance_level, role, mentions_count, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 1, now(), now())
            RETURNING id
        """, (canonical_name, entity_type, provenance, role))
        new_id = cur.fetchone()["id"]
        print(f"    ✓ created #{new_id}  {canonical_name}")

    # C) Fix the conflated chat_note #156
    print("\n  C) Correct chat_note #156 (MWK → MMK conflation):")
    cur.execute("SELECT id, content FROM chat_notes WHERE id = 156")
    old = cur.fetchone()
    if old:
        new_content = old["content"].replace(
            "Allan Inocalla and MWK (Mary Worrick Keesey)",
            "Allan Inocalla and Michael Marcos Keon (MMK — NOT MWK; MWK is Mary Worrick Keesey, a different person in a separate matter)"
        )
        if new_content != old["content"]:
            cur.execute("""
                UPDATE chat_notes
                   SET content = %s,
                       updated_at = now()
                 WHERE id = 156
            """, (new_content,))
            print(f"    ✓ note#156 content corrected")
        else:
            print(f"    · note#156 already corrected (no-op)")
    else:
        print(f"    · note#156 not found")

    conn.commit()
    print("\n  ✓ COMMITTED")

    # Final recap
    cur.execute("SELECT id, case_file, matter_code FROM documents WHERE id IN (962, 963)")
    print("\n  Final doc state:")
    for r in cur.fetchall():
        print(f"    doc#{r['id']}  case_file={r['case_file']}  matter_code={r['matter_code']}")

    cur.execute("""
        SELECT id, canonical_name FROM entities
         WHERE canonical_name IN ('Luis Chavit C. Singson','LCS Group of Companies',
                                  'Satrap Mining','Michael Marcos Keon')
         ORDER BY id
    """)
    print("\n  New entities now in DB:")
    for r in cur.fetchall():
        print(f"    #{r['id']}  {r['canonical_name']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
