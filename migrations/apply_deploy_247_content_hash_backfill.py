#!/usr/bin/env python3
"""Deploy 247 content_hash backfill — populates content_hash on hard-locked rows.

The lock ceremony flipped verification_lock='hard' on 20 rows but didn't
populate content_hash (the application-managed integrity field). Without it,
test_locked_data_integrity fails and the drift-detection on compound claims
can't anchor.

Approach: re-compute content_hash via the DB function compute_content_hash(jsonb)
for each hard-locked row and UPDATE the column. This is a one-time remediation;
future locks should set content_hash inline at lock time.

Idempotent. Uses app.truth_override='on' because the rows are already locked.
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

TABLES_PK = {
    "entities": "id",
    "titles": "tct_number",
    "instruments_on_title": "id",
    "subdivision_plans": "id",
    "title_transfers": "id",
    # title_chain is composite — handled separately
}


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 247 — content_hash backfill on hard-locked rows")
    print("=" * 60)

    cur.execute("SET LOCAL app.actor = 'jonathan'")
    cur.execute("SET LOCAL app.truth_override = 'on'")
    cur.execute("SET LOCAL app.truth_override_actor = 'jonathan'")
    cur.execute("SET LOCAL app.truth_override_reason = 'Deploy 247 content_hash backfill — remediation for missed inline computation at lock-flip time'")

    total = 0
    for table, pk in TABLES_PK.items():
        cur.execute(f"""
            SELECT {pk} AS pk_val, to_jsonb({table}) AS row_json
              FROM {table}
             WHERE verification_lock = 'hard' AND content_hash IS NULL
        """)
        rows = cur.fetchall()
        if not rows:
            continue
        print(f"\n  {table}: {len(rows)} rows need content_hash")
        for r in rows:
            cur.execute("SELECT compute_content_hash(%s::jsonb) AS h", (psycopg2.extras.Json(r["row_json"]),))
            h = cur.fetchone()["h"]
            cur.execute(f"UPDATE {table} SET content_hash = %s WHERE {pk} = %s", (h, r["pk_val"]))
            total += 1
        print(f"    ✓ {len(rows)} hashes written")

    # title_chain (composite PK)
    cur.execute("""
        SELECT parent_title, child_title, to_jsonb(title_chain) AS row_json
          FROM title_chain
         WHERE verification_lock = 'hard' AND content_hash IS NULL
    """)
    rows = cur.fetchall()
    if rows:
        print(f"\n  title_chain: {len(rows)} rows need content_hash")
        for r in rows:
            cur.execute("SELECT compute_content_hash(%s::jsonb) AS h", (psycopg2.extras.Json(r["row_json"]),))
            h = cur.fetchone()["h"]
            cur.execute("""UPDATE title_chain SET content_hash = %s
                             WHERE parent_title = %s AND child_title = %s""",
                        (h, r["parent_title"], r["child_title"]))
            total += 1
        print(f"    ✓ {len(rows)} hashes written")

    conn.commit()
    print(f"\n  ✓ {total} hashes backfilled, committed.")

    # Verify
    cur.execute("""
        SELECT 'entities' AS t, COUNT(*) FILTER (WHERE verification_lock='hard' AND content_hash IS NULL) AS missing FROM entities
        UNION ALL SELECT 'titles', COUNT(*) FILTER (WHERE verification_lock='hard' AND content_hash IS NULL) FROM titles
        UNION ALL SELECT 'title_chain', COUNT(*) FILTER (WHERE verification_lock='hard' AND content_hash IS NULL) FROM title_chain
    """)
    print("\n  Post-state (rows hard-locked with NULL content_hash — should be 0):")
    for r in cur.fetchall():
        print(f"    {r['t']:<25s} {r['missing']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
