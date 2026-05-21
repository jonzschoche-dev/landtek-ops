#!/usr/bin/env python3
"""Deploy 255 — Donata King linkage + Paracale↔MWK case_file misclassifications.

User correction (2026-05-21): "the torralba is linked to 260360 Donata King etc"

Expanding on deploy_251/254. Found 4 more docs tagged case_file='Paracale-001'
that are actually Balane-family / MWK chain material:

  doc#406 — Philippine Consulate Toronto Acknowledgement for GLORIA HANSOL
            BALANE (her middle name 'Hansol' confirms Balane↔Hansol family
            intermarriage — Rosalina M. Hansol is a transferee). 2020-05-28.
  doc#411 — RPA Form 1A real-property declaration: Owner GLORIA H. BALANE,
            location Brgy. San Roque Mercedes, TCT 079-202100212 = the
            contested defendant title T-079-2021002127. Direct CV26360 evidence.
  doc#568 — Supreme Court Decision G.R. No. 8678 promulgated Dec 29, 1913 in
            'MARCIANA MORENO DE WORRICK u. Paulina, Valeriana, Lino, and
            Raymundo Gaco'. Worrick-family chain primary evidence; issued
            upon request of Jonathan Paul Zschoche Jan 5, 2026.
  doc#586 — Civil Case 8563 (Juntilla, Torralba, Cantor, Mendones, Escalante
            v. Donata M. King, Francia Delos Santos, Joel I. Mabeza, Daniel E.
            Teope, Christine M. Opena) — RTC Daet Branch 41, DAMAGES /
            Malicious Prosecution. Underlying RTC case of CA-G.R. SP 181607.

Three pieces:

A) Reassign case_file + matter_code on the 4 docs.

B) Consolidate Donata King aliases:
     #3155 'Donata Mabeza King' (most complete) — KEEP as canonical
     #8365 'Donata M. King'                     — point canonical_id → 3155

C) Memorialize new keystone facts in the registry (separate edit to _clients.py):
     - Donata Mabeza King   = #3155  (Balane-family defendant, Civil 8563)
     - Joel I. Mabeza        = #8367  (defendant, Civil 8563)

   Plus add a feedback note about the Hansol↔Balane family linkage that
   surfaced (Gloria HANSOL Balane: her middle name = transferee surname Hansol).

Idempotent. Audited via app.actor='jonathan_deploy_255'.
"""
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# (doc_id, new_case_file, new_matter_code, rationale)
ASSIGNMENTS = [
    (406, "MWK-001", "MWK-CV26360",
     "PH Consulate Toronto acknowledgement for GLORIA HANSOL BALANE (CV26360 defendant); Hansol-Balane family link"),
    (411, "MWK-001", "MWK-CV26360",
     "RPA Form 1A — Owner GLORIA H. BALANE, TCT 079-202100212 = contested T-079-2021002127 defendant title"),
    (568, "MWK-001", "MWK-TCT4497",
     "SC Decision G.R. 8678 (Dec 29 1913) Marciana Moreno De WORRICK v. Gaco — chain primary evidence (requested by Jonathan Jan 5 2026)"),
    (586, "MWK-001", "MWK-CV26360",
     "Civil Case 8563 — Juntilla/Torralba et al. v. Donata King/Joel Mabeza et al. (RTC Daet Br. 41); underlying RTC case of CA-181607"),
]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_255'")

    print("Deploy 255 — Donata King + Paracale↔MWK misclassifications")
    print("=" * 60)

    # A) Reassign case_file + matter_code
    print("\n  A) Reclassify 4 Paracale-tagged docs:")
    for doc_id, cf, mc, rationale in ASSIGNMENTS:
        cur.execute("""
            UPDATE documents
               SET case_file = %s, matter_code = %s
             WHERE id = %s
             RETURNING id, case_file, matter_code
        """, (cf, mc, doc_id))
        r = cur.fetchone()
        print(f"    ✓ doc#{r['id']}: case_file='{r['case_file']}' matter_code='{r['matter_code']}'")
        print(f"        [{rationale}]")

    # B) Consolidate Donata King aliases
    print("\n  B) Consolidate Donata King aliases:")
    # Make #8365 point to #3155 as canonical
    cur.execute("""
        UPDATE entities
           SET canonical_id = 3155,
               notes = COALESCE(notes || E'\n', '') ||
                       '[deploy_255] consolidated to #3155 Donata Mabeza King (most complete name); see deploy_251/254/255 Torralba-Donata-Balane lineage'
         WHERE id = 8365 AND (canonical_id IS NULL OR canonical_id != 3155)
         RETURNING id
    """)
    r = cur.fetchone()
    if r:
        print(f"    ✓ #8365 'Donata M. King' → canonical=#3155 'Donata Mabeza King'")
    else:
        print(f"    · #8365 already consolidated (no-op)")

    conn.commit()
    print("\n  ✓ COMMITTED")

    # Recap
    cur.execute("""
        SELECT id, case_file, matter_code
          FROM documents WHERE id = ANY(%s) ORDER BY id
    """, ([a[0] for a in ASSIGNMENTS],))
    print("\n  Final doc state:")
    for r in cur.fetchall():
        print(f"    doc#{r['id']}  case_file={r['case_file']!r}  matter_code={r['matter_code']!r}")

    cur.execute("""
        SELECT id, canonical_name, canonical_id
          FROM entities WHERE id IN (3155, 8365) ORDER BY id
    """)
    print("\n  Donata King consolidation:")
    for r in cur.fetchall():
        print(f"    #{r['id']}  {r['canonical_name']!r}  canonical_id={r['canonical_id']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
