#!/usr/bin/env python3
"""Deploy 260 — assign matter_code for 261 untagged MWK-001 docs.

Background: docs are tagged case_file='MWK-001' (so we know they're MWK
material) but matter_code IS NULL. The deploy_244 LLM batch + the
deploy_252/253 guards have classified most of them; they're sitting in
'proposed' or 'needs_manual_review' status. Time to actually apply.

Strategy (deterministic — routes by inspecting proposal text):

Bucket A — 49 'proposed assign_matter' at conf 0.75-0.85
  → apply the proposed matter_code directly. These docs are already in
    MWK-001 case_file (so we have prior evidence they belong); lowering
    the auto-apply threshold for case_file-confirmed docs is safe.

Bucket B — 76 'needs_manual_review flag_unrelated'
  → LLM said "not MWK chain" but the docs ARE in MWK-001 case_file
    (chain research material). Route by reasoning text:
    - mentions a transferee surname → MWK-CV26360
    - mentions Worrick/Keesey/Hoppe → MWK-ESTATE
    - else → MWK-TCT4497

Bucket C — 64 'proposed keep_unscoped'
  → LLM said "MWK-related but no specific matter" → MWK-ESTATE catch-all

Bucket D — ~72 docs with no proposal at all
  → leave for now; flagged for a follow-up LLM run.

All assignments go through doc_classification_proposals as 'applied' with
provenance reviewed_by='jonathan_deploy_260'. Audited via app.actor.
"""
import re
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

CASE_FILE = "MWK-001"

# Transferee surnames (lower-case) — match in proposal.reasoning
TRANSFEREE_SURNAMES = {
    "victa", "apor", "mabeza", "bernardo", "ramirez", "gaulit", "vela",
    "santiago", "iligan", "illigan", "tychingco", "pascual", "onrubio",
    "cereza", "mariquita", "valledor", "hansol", "leano", "ocan", "tenorio",
    "balane", "fuente", "macale", "pajarillo", "king",
}

# Worrick/Keesey/Hoppe surnames (family) → MWK-ESTATE
FAMILY_SURNAMES = {"worrick", "keesey", "kessey", "kiesse", "hoppe", "zschoche"}


def matter_for_reasoning(reasoning):
    """Return (matter_code, why) given the LLM reasoning text."""
    if not reasoning:
        return ("MWK-TCT4497", "default chain-research")
    rl = reasoning.lower()

    family_hits = [s for s in FAMILY_SURNAMES if re.search(rf"\b{s}\b", rl)]
    transferee_hits = [s for s in TRANSFEREE_SURNAMES if re.search(rf"\b{s}\b", rl)]

    if transferee_hits:
        return ("MWK-CV26360", f"transferee surname hit: {transferee_hits[:3]}")
    if family_hits:
        return ("MWK-ESTATE", f"family surname hit: {family_hits[:3]}")
    return ("MWK-TCT4497", "default chain-research")


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_260'")

    print(f"Deploy 260 — MWK matter-code assignment ({CASE_FILE})")
    print("=" * 60)

    # Bucket A — apply existing assign_matter proposals
    cur.execute("""
        SELECT p.id AS pid, p.doc_id, p.proposed_matter_code, p.confidence
          FROM doc_classification_proposals p
          JOIN documents d ON d.id = p.doc_id
         WHERE d.case_file = %s AND d.matter_code IS NULL
           AND p.status = 'proposed' AND p.proposed_action = 'assign_matter'
         ORDER BY p.id
    """, (CASE_FILE,))
    bucket_a = cur.fetchall()
    print(f"\n  Bucket A — apply 'assign_matter' proposals: {len(bucket_a)}")
    counts_a = {}
    for p in bucket_a:
        mc = p["proposed_matter_code"]
        cur.execute("UPDATE documents SET matter_code = %s WHERE id = %s", (mc, p["doc_id"]))
        cur.execute("""UPDATE doc_classification_proposals
                          SET status='applied', reviewed_at=now(), reviewed_by='jonathan_deploy_260',
                              review_notes='[deploy_260] applied — case_file already MWK-001 confirms MWK material'
                        WHERE id = %s""", (p["pid"],))
        counts_a[mc] = counts_a.get(mc, 0) + 1
    for mc, n in sorted(counts_a.items(), key=lambda x: -x[1]):
        print(f"    → {mc:<22s} {n}")

    # Bucket B — route needs_manual_review via reasoning
    cur.execute("""
        SELECT p.id AS pid, p.doc_id, p.reasoning
          FROM doc_classification_proposals p
          JOIN documents d ON d.id = p.doc_id
         WHERE d.case_file = %s AND d.matter_code IS NULL
           AND p.status = 'needs_manual_review'
         ORDER BY p.id
    """, (CASE_FILE,))
    bucket_b = cur.fetchall()
    print(f"\n  Bucket B — route 'needs_manual_review' by reasoning: {len(bucket_b)}")
    counts_b = {}
    for p in bucket_b:
        mc, why = matter_for_reasoning(p["reasoning"])
        cur.execute("UPDATE documents SET matter_code = %s WHERE id = %s", (mc, p["doc_id"]))
        cur.execute("""UPDATE doc_classification_proposals
                          SET status='applied', reviewed_at=now(), reviewed_by='jonathan_deploy_260',
                              review_notes=%s
                        WHERE id = %s""",
                    (f"[deploy_260] routed → {mc} ({why})", p["pid"]))
        counts_b[mc] = counts_b.get(mc, 0) + 1
    for mc, n in sorted(counts_b.items(), key=lambda x: -x[1]):
        print(f"    → {mc:<22s} {n}")

    # Bucket C — keep_unscoped → MWK-ESTATE catch-all
    cur.execute("""
        SELECT p.id AS pid, p.doc_id
          FROM doc_classification_proposals p
          JOIN documents d ON d.id = p.doc_id
         WHERE d.case_file = %s AND d.matter_code IS NULL
           AND p.status = 'proposed' AND p.proposed_action = 'keep_unscoped'
         ORDER BY p.id
    """, (CASE_FILE,))
    bucket_c = cur.fetchall()
    print(f"\n  Bucket C — keep_unscoped → MWK-ESTATE: {len(bucket_c)}")
    for p in bucket_c:
        cur.execute("UPDATE documents SET matter_code = 'MWK-ESTATE' WHERE id = %s", (p["doc_id"],))
        cur.execute("""UPDATE doc_classification_proposals
                          SET status='applied', reviewed_at=now(), reviewed_by='jonathan_deploy_260',
                              review_notes='[deploy_260] LLM keep_unscoped → MWK-ESTATE catch-all'
                        WHERE id = %s""", (p["pid"],))

    # Bucket D — count docs still unhandled
    cur.execute("""
        SELECT COUNT(*) AS n
          FROM documents d
         WHERE d.case_file = %s AND d.matter_code IS NULL
           AND NOT EXISTS (SELECT 1 FROM doc_classification_proposals p WHERE p.doc_id = d.id)
    """, (CASE_FILE,))
    bucket_d = cur.fetchone()["n"]
    print(f"\n  Bucket D — docs with no proposal yet (LLM follow-up): {bucket_d}")

    conn.commit()
    print("\n  ✓ COMMITTED")

    # Final inventory
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE matter_code IS NULL) AS untagged,
               COUNT(*) FILTER (WHERE matter_code IS NOT NULL) AS tagged,
               COUNT(*) AS total
          FROM documents WHERE case_file = %s
    """, (CASE_FILE,))
    final = cur.fetchone()
    pct = 100.0 * final["tagged"] / max(1, final["total"])
    print(f"\n  Final MWK-001 doc tagging: {final['tagged']}/{final['total']} ({pct:.0f}%)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
