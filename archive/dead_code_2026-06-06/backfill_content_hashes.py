#!/usr/bin/env python3
"""Backfill content_hash with per-row transactions (handles existing UNIQUE constraint).

The 'docs_content_hash_idx' UNIQUE constraint blocks byte-identical files
from sharing a content_hash. For those, we record the conflict (this row
is a dupe of which existing row) for later merge.

Strategy:
  1. Per-row UPDATE in autocommit mode
  2. On unique-constraint violation, SELECT the existing doc with that hash
     and record the dupe relationship in a new docs_dupes table
  3. Report at end
"""
import hashlib
import os
import psycopg2
import psycopg2.errors

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def ensure_dupes_table():
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS docs_dupes (
            id SERIAL PRIMARY KEY,
            duplicate_doc_id INTEGER NOT NULL,
            canonical_doc_id INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            file_path TEXT,
            original_filename TEXT,
            detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved BOOLEAN NOT NULL DEFAULT false,
            resolved_action TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_docs_dupes_dup ON docs_dupes(duplicate_doc_id);
        CREATE INDEX IF NOT EXISTS idx_docs_dupes_canonical ON docs_dupes(canonical_doc_id);
    """)
    cur.close(); conn.close()


def main():
    ensure_dupes_table()
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        SELECT id, file_path, original_filename FROM documents
         WHERE content_hash IS NULL AND file_path IS NOT NULL AND file_path != ''
         ORDER BY id;
    """)
    rows = cur.fetchall()
    print(f"  candidates: {len(rows)}")

    hashed = 0
    dupes_found = 0
    missing = 0
    errors = 0
    for doc_id, path, name in rows:
        if not os.path.exists(path):
            missing += 1
            continue
        try:
            h = sha256_file(path)
        except Exception as e:
            errors += 1
            print(f"  hash error id={doc_id}: {e}")
            continue
        try:
            cur.execute("UPDATE documents SET content_hash=%s WHERE id=%s", (h, doc_id))
            hashed += 1
        except psycopg2.errors.UniqueViolation:
            # Find the canonical (existing) doc
            cur.execute("SELECT id, original_filename FROM documents WHERE content_hash=%s LIMIT 1", (h,))
            canon = cur.fetchone()
            if canon:
                canon_id, canon_name = canon
                cur.execute("""
                    INSERT INTO docs_dupes (duplicate_doc_id, canonical_doc_id, content_hash, file_path, original_filename)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (doc_id, canon_id, h, path, name))
                dupes_found += 1
        if (hashed + dupes_found) % 25 == 0 and (hashed + dupes_found) > 0:
            print(f"  ...progress: hashed={hashed}, dupes={dupes_found}")

    print(f"\n  ✓ hashed: {hashed}")
    print(f"  ✓ dupes recorded: {dupes_found}")
    print(f"  ⚠ missing on disk: {missing}")
    print(f"  ⚠ hash errors: {errors}")

    # Show top dupe groups
    cur.execute("""
        SELECT canonical_doc_id, count(*) AS n_dupes, array_agg(duplicate_doc_id ORDER BY duplicate_doc_id)
          FROM docs_dupes WHERE NOT resolved GROUP BY canonical_doc_id ORDER BY n_dupes DESC LIMIT 10;
    """)
    groups = cur.fetchall()
    print(f"\n  duplicate groups (top 10 by count):")
    for canon, n, ids in groups:
        cur.execute("SELECT original_filename FROM documents WHERE id=%s", (canon,))
        cname = cur.fetchone()[0]
        print(f"    canonical id={canon} ({cname!r:50}) <- {n} dupes: {ids[:5]}{'...' if len(ids)>5 else ''}")

    # Coverage after
    cur.execute("SELECT count(*), count(content_hash) FROM documents;")
    total, have = cur.fetchone()
    print(f"\n  overall content_hash coverage: {have}/{total} = {have*100/total:.0f}%")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
