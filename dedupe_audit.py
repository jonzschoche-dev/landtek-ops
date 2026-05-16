#!/usr/bin/env python3
"""Dedup audit (deploy 118-D).

Three duplicate tiers detected:

  TIER 1 — EXACT: same content_hash (bytes-identical)
  TIER 2 — NEAR: same (smart_filename, case_file) but different content_hash
  TIER 3 — CONTENT-SIMILAR: same canonical_filename pattern but different documents.id

Writes duplicate_groups + duplicate_group_members. Logs to audit_events.
Sends Telegram digest.
"""
import argparse
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def find_exact_dupes(cur):
    cur.execute("""
        SELECT content_hash, count(*) AS n, array_agg(id ORDER BY id) AS ids
          FROM documents
         WHERE content_hash IS NOT NULL
         GROUP BY content_hash HAVING count(*) > 1
         ORDER BY n DESC
    """)
    return cur.fetchall()


def find_near_dupes(cur):
    cur.execute("""
        SELECT smart_filename, case_file,
               count(*) AS n, array_agg(id ORDER BY id) AS ids,
               array_agg(DISTINCT COALESCE(content_hash,'')) AS hashes
          FROM documents
         WHERE smart_filename IS NOT NULL AND smart_filename <> ''
         GROUP BY smart_filename, case_file
        HAVING count(*) > 1 AND array_length(array_agg(DISTINCT COALESCE(content_hash,'')),1) > 1
    """)
    return cur.fetchall()


def find_content_similar(cur):
    cur.execute("""
        SELECT canonical_filename, count(*) AS n, array_agg(id ORDER BY id) AS ids
          FROM documents
         WHERE canonical_filename IS NOT NULL
         GROUP BY canonical_filename HAVING count(*) > 1
         ORDER BY n DESC
    """)
    return cur.fetchall()


def pick_keeper(cur, ids):
    """Among a group of dupe ids, pick the one with best metadata."""
    cur.execute("""
        SELECT id, length(extracted_text) AS textlen,
               (case_file IS NOT NULL AND case_file <> '')::int +
               (execution_status IS NOT NULL AND execution_status <> 'unknown')::int +
               (drive_file_id IS NOT NULL)::int +
               (canonical_filename IS NOT NULL)::int AS meta_score,
               updated_at
          FROM documents WHERE id = ANY(%s)
         ORDER BY meta_score DESC, textlen DESC NULLS LAST, updated_at DESC
         LIMIT 1
    """, (ids,))
    return cur.fetchone()["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="clear existing duplicate_groups before recomputing")
    ap.add_argument("--send-tg", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.reset:
        cur.execute("DELETE FROM duplicate_group_members")
        cur.execute("DELETE FROM duplicate_groups")
        print("  ↺ cleared existing duplicate_groups")

    exact = find_exact_dupes(cur)
    print(f"  TIER 1 (exact-hash): {len(exact)} groups")
    g1_dupes = 0
    for g in exact:
        ids = list(g["ids"])
        keeper = pick_keeper(cur, ids)
        cur.execute("""
            INSERT INTO duplicate_groups (group_kind, hash_or_key, canonical_id, duplicate_count, notes)
            VALUES ('exact_hash', %s, %s, %s, %s) RETURNING id
        """, (g["content_hash"], keeper, len(ids)-1,
              f"sha256 match across {len(ids)} docs"))
        gid = cur.fetchone()["id"]
        for d in ids:
            cur.execute("""
                INSERT INTO duplicate_group_members (group_id, doc_id, is_keeper, reason)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (group_id, doc_id) DO NOTHING
            """, (gid, d, d == keeper, "exact content_hash match"))
            cur.execute("""
                INSERT INTO audit_events (event_type, target_kind, target_id, payload)
                VALUES ('dedup_exact', 'document', %s,
                        jsonb_build_object('group_id', %s, 'keeper_id', %s, 'group_size', %s))
            """, (d, gid, keeper, len(ids)))
        g1_dupes += len(ids) - 1

    near = find_near_dupes(cur)
    print(f"  TIER 2 (same-name same-case different-hash): {len(near)} groups")
    g2_dupes = 0
    for g in near:
        ids = list(g["ids"])
        keeper = pick_keeper(cur, ids)
        cur.execute("""
            INSERT INTO duplicate_groups (group_kind, hash_or_key, canonical_id, duplicate_count, notes)
            VALUES ('near_name_size', %s, %s, %s, %s) RETURNING id
        """, (f"{g['smart_filename']}|{g['case_file']}", keeper, len(ids)-1,
              f"same filename + case across {len(ids)} docs"))
        gid = cur.fetchone()["id"]
        for d in ids:
            cur.execute("""
                INSERT INTO duplicate_group_members (group_id, doc_id, is_keeper, reason)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (gid, d, d == keeper, "same filename + case"))
        g2_dupes += len(ids) - 1

    similar = find_content_similar(cur)
    print(f"  TIER 3 (same canonical name): {len(similar)} groups")
    g3_dupes = 0
    for g in similar:
        ids = list(g["ids"])
        keeper = pick_keeper(cur, ids)
        cur.execute("""
            INSERT INTO duplicate_groups (group_kind, hash_or_key, canonical_id, duplicate_count, notes)
            VALUES ('content_similar', %s, %s, %s, %s) RETURNING id
        """, (g["canonical_filename"], keeper, len(ids)-1,
              f"identical canonical name across {len(ids)} docs"))
        gid = cur.fetchone()["id"]
        for d in ids:
            cur.execute("""
                INSERT INTO duplicate_group_members (group_id, doc_id, is_keeper, reason)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (gid, d, d == keeper, "same canonical_filename"))
        g3_dupes += len(ids) - 1

    print(f"\n  Summary:")
    print(f"    Tier 1 (exact-hash):      {len(exact)} groups · {g1_dupes} duplicate docs")
    print(f"    Tier 2 (same-name+case):  {len(near)} groups · {g2_dupes} duplicate docs")
    print(f"    Tier 3 (same canonical):  {len(similar)} groups · {g3_dupes} duplicate docs")
    print(f"    TOTAL duplicate docs flagged (not deleted): {g1_dupes + g2_dupes + g3_dupes}")

    if args.send_tg:
        import requests
        env = {}
        with open("/root/landtek/.env") as f:
            for l in f:
                if "=" in l and not l.startswith("#"):
                    k, _, v = l.strip().partition("="); env[k.strip()] = v.strip()

        lines = [
            "🧹 <b>Dedup audit complete</b>",
            "",
            f"<b>Tier 1 — exact content_hash:</b> {len(exact)} groups · <b>{g1_dupes}</b> docs are byte-identical re-ingests",
            f"<b>Tier 2 — same name + case, different hash:</b> {len(near)} groups · <b>{g2_dupes}</b> docs (likely re-OCR or alternate copies)",
            f"<b>Tier 3 — same canonical name:</b> {len(similar)} groups · <b>{g3_dupes}</b> docs (post-rename collisions — likely true duplicates)",
            "",
            f"<b>Total flagged as duplicate: {g1_dupes + g2_dupes + g3_dupes}</b>",
            "",
            "<i>Per the gold-information rule: nothing deleted — just flagged. Each group has a 'keeper' (best-metadata copy) and member rows marked is_keeper=false.</i>",
            "",
            "<b>Top exact-match groups:</b>",
        ]
        for g in exact[:8]:
            lines.append(f"  • hash {g['content_hash'][:16]}… → {len(g['ids'])} copies (ids {','.join(map(str, g['ids'][:5]))}{'…' if len(g['ids'])>5 else ''})")
        text = "\n".join(lines)
        r = requests.post(f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage",
                          json={"chat_id": "6513067717", "text": text,
                                "parse_mode": "HTML", "disable_web_page_preview": True})
        print(f"  TG: {r.status_code}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
