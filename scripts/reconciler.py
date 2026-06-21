#!/usr/bin/env python3
"""reconciler.py — resident agent: human-in-the-loop adjudication of proposed_facts. $0.

The verify_worker auto-verifies only facts whose quote is verbatim-grounded; anything it surfaced but
could not ground goes to `proposed_facts`. This is the operator's review desk for that queue: list
them, accept (promote to a verified matter_fact — the provenance gate still adjudicates, so a bad
quote is rejected at the door), or reject with a reason. Nothing is auto-promoted; the human decides.

  python3 scripts/reconciler.py --list [MATTER]      # pending proposals
  python3 scripts/reconciler.py --accept <id>         # promote to verified (gate-checked)
  python3 scripts/reconciler.py --reject <id> [why]   # dismiss
  python3 scripts/reconciler.py --stats
"""
import sys

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def _c():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c, c.cursor()


def main():
    a = sys.argv
    c, cur = _c()
    if "--list" in a:
        i = a.index("--list")
        mc = a[i + 1] if len(a) > i + 1 and not a[i + 1].startswith("-") else None
        q = "SELECT id, matter_code, left(statement,80), round(confidence,2) FROM proposed_facts WHERE status='pending'"
        cur.execute(q + (" AND matter_code=%s" if mc else "") + " ORDER BY matter_code, id", (mc,) if mc else None)
        rows = cur.fetchall()
        print(f"pending proposals: {len(rows)}")
        for rid, m, s, conf in rows:
            print(f"  [{rid}] {m} (c={conf}) {s}")
    elif "--accept" in a:
        rid = int(a[a.index("--accept") + 1])
        cur.execute("SELECT matter_code,statement,excerpt,source_doc_id,confidence FROM proposed_facts WHERE id=%s", (rid,))
        r = cur.fetchone()
        if not r:
            print("no such proposal"); return
        mc, stmt, exc, doc, conf = r
        try:
            cur.execute("""INSERT INTO matter_facts (matter_code,statement,fact_kind,source_kind,source_id,
                excerpt,provenance_level,confidence,created_by,created_at)
                VALUES (%s,%s,'reconciled','doc',%s,%s,'verified',%s,'reconciler',now())""",
                (mc, stmt, str(doc), exc, conf or 0.9))
            cur.execute("UPDATE proposed_facts SET status='accepted' WHERE id=%s", (rid,))
            print(f"✓ accepted → verified matter_fact for {mc}")
        except psycopg2.Error as e:
            print(f"✗ gate rejected (excerpt not grounded in doc:{doc}): {str(e).splitlines()[0][:80]}")
    elif "--reject" in a:
        rid = int(a[a.index("--reject") + 1])
        cur.execute("UPDATE proposed_facts SET status='rejected' WHERE id=%s", (rid,))
        print(f"✓ rejected proposal {rid}" if cur.rowcount else "no such proposal")
    else:
        cur.execute("SELECT status, count(*) FROM proposed_facts GROUP BY 1 ORDER BY 2 DESC")
        print("proposed_facts:", dict(cur.fetchall()) or "(empty)")


if __name__ == "__main__":
    main()
