#!/usr/bin/env python3
"""Deploy 257 — cross-link Owner-bucket docs to MWK matters.

The 5 docs in case_file='Owner' that the case_file audit (deploy_255) flagged
all contain real MWK keystone evidence — they're Jonathan's personal copies
of family/chain material. case_file stays = 'Owner' (provenance: they ARE
Jonathan's docs), but matter_code is set so they surface in MWK chronicle
+ lookup.

Pairs with the chronicle_mwk.py edit in this same deploy: the timeline query
now matches docs by (case_file = client.case_file OR matter_code LIKE prefix%),
so cross-linked Owner docs appear in the MWK chronicle.

  doc#326 → MWK-TCT4497   — TCT T-57816 (Macaso family), Lot 2-X-6 chain (T-32917 derivative)
  doc#602 → MWK-ESTATE    — U.S. Constitution preamble — Patricia passport ID page
  doc#603 → MWK-ESTATE    — duplicate / second page of Patricia passport material
  doc#692 → MWK-ESTATE    — Affidavit for Delayed Registration of Birth (Keesey family record)
  doc#693 → MWK-TCT4497   — National Archives certification (Marciana Moreno De Worrick research)
  doc#694 → MWK-TCT4497   — National Archives certification (Worrick chain research, pair of 693)

Idempotent. Audited via app.actor='jonathan_deploy_257'.
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

CROSSLINKS = [
    (326, "MWK-TCT4497", "TCT T-57816 (Macaso family) — Lot 2-X-6 sub-subdivision in T-32917 chain"),
    (602, "MWK-ESTATE",  "Patricia Keesey Zschoche passport ID page (U.S. Constitution preamble)"),
    (603, "MWK-ESTATE",  "Patricia passport material (page 2 of 602)"),
    (692, "MWK-ESTATE",  "Affidavit for Delayed Registration of Birth — Keesey family record"),
    (693, "MWK-TCT4497", "National Archives certification — Marciana Moreno De Worrick research"),
    (694, "MWK-TCT4497", "National Archives certification — Worrick chain research (paired with 693)"),
]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_257'")

    print("Deploy 257 — cross-link Owner-bucket docs to MWK matters")
    print("=" * 60)

    for doc_id, matter_code, rationale in CROSSLINKS:
        cur.execute("""
            UPDATE documents
               SET matter_code = %s
             WHERE id = %s
               AND (matter_code IS NULL OR matter_code != %s)
             RETURNING id, case_file, matter_code
        """, (matter_code, doc_id, matter_code))
        r = cur.fetchone()
        if r:
            print(f"  ✓ doc#{r['id']}: case_file='{r['case_file']}' matter_code='{r['matter_code']}'")
            print(f"        [{rationale}]")
        else:
            print(f"  · doc#{doc_id} already at {matter_code} (no-op)")

    conn.commit()
    print("\n  ✓ COMMITTED")

    # Verify cross-link works: count Owner docs that will now appear in MWK queries
    cur.execute("""
        SELECT id, case_file, matter_code, smart_filename
          FROM documents
         WHERE matter_code LIKE 'MWK-%' AND case_file = 'Owner'
         ORDER BY id
    """)
    print("\n  Owner docs now cross-linked into MWK matters:")
    for r in cur.fetchall():
        print(f"    doc#{r['id']}  matter_code={r['matter_code']!r}  fn={(r['smart_filename'] or '')[:40]!r}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
