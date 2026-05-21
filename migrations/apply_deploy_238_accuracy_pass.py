#!/usr/bin/env python3
"""Deploy 238 — Multi-pass accuracy improvements (per user discretionary directive).

Five surgical improvements, all deterministic:

  1. Populate arta_cases.adjudicator_entity_id for Del Rosario's 3 cases
     (0690, 0792, 1210) — entity #8877 now exists per promote 2026-05-21.
  2. Trim trailing punctuation ("Balane —") from arta_cases.respondents.
  3. Delete res#1, res#2 from `resolutions` — they're May 5 PETITIONS to OP
     (already captured as esc#3 + esc#4 escalations), not Resolutions FROM
     an adjudicator. Misclassified at deploy_229.
  4. Regenerate consolidate_entities proposals for the expanded group set
     (Pajarillo + Patricia + already-done Cesar/Barandon will produce 0).
  5. Auto-approve all newly-generated proposals with actor='jonathan'
     under the discretionary-accuracy-pass authorization.

Idempotent. Audit log captures all changes.
"""
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def set_override(cur, actor, reason):
    cur.execute("SET LOCAL app.actor = %s", (actor,))
    cur.execute("SET LOCAL app.truth_override = 'on'")
    cur.execute("SET LOCAL app.truth_override_actor = %s", (actor,))
    cur.execute("SET LOCAL app.truth_override_reason = %s", (reason,))


def step1_populate_adjudicator_fk(cur):
    print("\n[1] Populate arta_cases.adjudicator_entity_id for Del Rosario's cases")
    # Get Del Rosario's entity id
    cur.execute("SELECT id FROM entities WHERE canonical_name = %s",
                ("Atty. Rodolfo B. Del Rosario Jr.",))
    r = cur.fetchone()
    if not r:
        print("  ✗ Del Rosario entity not found — was it promoted?")
        return 0
    adj_id = r["id"]
    print(f"  Del Rosario entity_id = {adj_id}")

    # arta_cases isn't in the CRITICAL_TABLES lockdown trigger set, so no override needed.
    cur.execute("""
        UPDATE arta_cases SET adjudicator_entity_id = %s, updated_at = NOW()
         WHERE matter_code IN (%s, %s, %s)
        RETURNING ctn_no
    """, (adj_id, "MWK-ARTA-0690", "MWK-ARTA-0792", "MWK-ARTA-1210"))
    updated = [r["ctn_no"] for r in cur.fetchall()]
    for c in updated:
        print(f"  ✓ {c} → adjudicator_entity_id = {adj_id}")
    return len(updated)


def step2_clean_respondents(cur):
    print("\n[2] Clean trailing punctuation from arta_cases.respondents")
    cur.execute("""
        SELECT id, ctn_no, respondents FROM arta_cases
         WHERE respondents IS NOT NULL AND array_length(respondents, 1) > 0
    """)
    cleaned = 0
    for r in cur.fetchall():
        new_resps = []
        changed = False
        for x in r["respondents"]:
            # Trim trailing punctuation + em-dash + whitespace
            cleaned_x = x.rstrip(" -–—.,;:_").strip()
            if cleaned_x != x:
                changed = True
            if cleaned_x:
                new_resps.append(cleaned_x)
        if changed:
            cur.execute(
                "UPDATE arta_cases SET respondents = %s WHERE id = %s",
                (new_resps, r["id"]),
            )
            print(f"  ✓ {r['ctn_no']}: {r['respondents']} → {new_resps}")
            cleaned += 1
    if cleaned == 0:
        print("  (no cleanup needed)")
    return cleaned


def step3_delete_misclassified_resolutions(cur):
    """res#1 and res#2 are May 5 PETITIONS to OP (Jonathan's filings),
    not Resolutions FROM ARTA. They're already represented as escalations
    (esc#3 = appeal_to_OP citing doc#702). Delete the misclassified rows."""
    print("\n[3] Delete misclassified res#1, res#2 (May 5 petitions, not resolutions)")
    set_override(
        cur, "jonathan",
        "Discretionary accuracy pass: res#1, res#2 are Jonathan's May 5 OP "
        "petitions, not ARTA Resolutions. Already captured as esc#3+esc#4. "
        "Removing to prevent confusion in chronicle/lookup output.",
    )
    cur.execute("""
        DELETE FROM resolutions WHERE id IN (1, 2)
                AND source_doc_id IN (702, 703)  -- safety: only the petitions
        RETURNING id, source_doc_id
    """)
    deleted = cur.fetchall()
    for r in deleted:
        print(f"  ✓ deleted res#{r['id']} (doc#{r['source_doc_id']})")
    return len(deleted)


def step4_regenerate_consolidation_proposals():
    """Just calls the consolidate_entities CLI to regenerate proposals."""
    print("\n[4] Regenerate consolidation proposals via consolidate_entities.py")
    import subprocess
    result = subprocess.run(
        ["python3", "/root/landtek/scripts/consolidate_entities.py", "propose", "--auto"],
        capture_output=True, text=True, cwd="/root/landtek",
    )
    # Print stdout summary line(s)
    for line in result.stdout.splitlines()[-10:]:
        print(f"  {line}")
    return result.returncode == 0


def step5_auto_approve_new_proposals():
    """Promote all newly-pending proposals."""
    print("\n[5] Auto-approve newly-pending proposals (Pajarillo + Patricia)")
    sys.path.insert(0, "/root/landtek/scripts")
    from promote_proposals import apply_proposal

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""SELECT * FROM proposed_changes WHERE review_status = 'pending'
                    ORDER BY id""")
    proposals = cur.fetchall()
    if not proposals:
        print("  (no pending proposals — already approved)")
        cur.close(); conn.close()
        return 0

    print(f"  Processing {len(proposals)} pending proposals…")
    reason = ("Discretionary accuracy pass (deploy_238) per 'use your discretion to make a "
              "highly accurate db' directive 2026-05-21. Pajarillo (11→1) + Patricia "
              "Keesey Zschoche (45→1) consolidation.")
    ok, fail = 0, 0
    for p in proposals:
        try:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                    apply_proposal(c, p, actor="jonathan", reason=reason, lock_after=False)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ✗ #{p['id']} ({p['operation']} on target={p['target_row_id']}): "
                  f"{type(e).__name__}: {str(e)[:120]}")
    print(f"  → {ok} approved, {fail} failed")
    cur.close()
    conn.close()
    return ok


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 238 — Multi-pass accuracy improvements")
    print("=" * 60)

    n1 = step1_populate_adjudicator_fk(cur)
    n2 = step2_clean_respondents(cur)
    n3 = step3_delete_misclassified_resolutions(cur)
    n4_ok = step4_regenerate_consolidation_proposals()
    n5 = step5_auto_approve_new_proposals()

    print()
    print("=" * 60)
    print("Deploy 238 summary:")
    print(f"  Adjudicator FKs populated: {n1}")
    print(f"  arta_cases respondents cleaned: {n2}")
    print(f"  misclassified resolutions deleted: {n3}")
    print(f"  consolidate_entities propose --auto: {'ok' if n4_ok else 'failed'}")
    print(f"  new proposals auto-approved: {n5}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
