#!/usr/bin/env python3
"""Organize /root/landtek/uploads/ into Drive-matching hierarchy.

Per Jonathan's directive (information is gold + easy to locate):
  /root/landtek/uploads/
    MWK-001/<smart_filename_or_original>.<ext>
    Paracale-001/<smart_filename_or_original>.<ext>
    Owner/<smart_filename_or_original>.<ext>
    Unclassified/<...>     (for case_file = NULL/Unknown/'')
    scannerpro/<existing>  (preserved as-is)

For each documents row with file_path under /root/landtek/uploads/ AND not
already in a <case_file>/ subdir:
  1. Determine target case_file dir (case_file or 'Unclassified')
  2. Determine target filename: smart_filename + extension(from original_filename
     or current file_path), with id suffix for uniqueness
  3. mkdir if needed
  4. shutil.move
  5. UPDATE documents.file_path

Idempotent: re-running on already-moved files is a no-op.
"""
import os
import re
import shutil
import sys
import psycopg2

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
UPLOADS = "/root/landtek/uploads"


def safe(s):
    """Filesystem-safe filename component."""
    if not s:
        return ""
    s = re.sub(r"[^A-Za-z0-9._\- ]", "_", s).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:150]


def main():
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        SELECT id, case_file, smart_filename, original_filename, file_path
          FROM documents
         WHERE file_path IS NOT NULL
           AND file_path LIKE '/root/landtek/uploads/%%'
           AND file_path NOT LIKE '/root/landtek/uploads/MWK-001/%%'
           AND file_path NOT LIKE '/root/landtek/uploads/Paracale-001/%%'
           AND file_path NOT LIKE '/root/landtek/uploads/Owner/%%'
           AND file_path NOT LIKE '/root/landtek/uploads/Unclassified/%%'
           AND file_path NOT LIKE '/root/landtek/uploads/scannerpro/%%'
           AND file_path NOT LIKE '/root/landtek/uploads/_archive%%'
         ORDER BY id;
    """)
    rows = cur.fetchall()
    print(f"  candidates to organize: {len(rows)}")

    moved = 0
    skipped_missing = 0
    skipped_exists = 0
    errors = 0

    for doc_id, case_file, smart, original, path in rows:
        if not os.path.exists(path):
            skipped_missing += 1
            continue

        # Target dir
        case_dir = case_file if case_file in ("MWK-001", "Paracale-001", "Owner") else "Unclassified"
        target_dir = os.path.join(UPLOADS, case_dir)
        os.makedirs(target_dir, exist_ok=True)

        # Target filename: smart_filename preferred, fall back to original, then current basename
        base_name = safe(smart) or safe(original) or safe(os.path.basename(path))
        # Preserve extension from original or current file
        ext = ""
        for cand in (original, path):
            if cand and "." in os.path.basename(cand):
                ext = "." + os.path.basename(cand).rsplit(".", 1)[1].lower()
                break
        # Strip existing ext from base_name if present
        if base_name.lower().endswith(ext.lower()):
            stem = base_name[: -len(ext)]
        else:
            stem = base_name
        target_name = f"{doc_id}_{stem}{ext}"
        target_path = os.path.join(target_dir, target_name)

        if os.path.exists(target_path):
            # Already moved (re-run) — just ensure DB matches
            if path != target_path:
                cur.execute("UPDATE documents SET file_path=%s WHERE id=%s", (target_path, doc_id))
            skipped_exists += 1
            continue

        try:
            shutil.move(path, target_path)
            cur.execute("UPDATE documents SET file_path=%s WHERE id=%s", (target_path, doc_id))
            moved += 1
            if moved % 25 == 0:
                print(f"  ...moved {moved}")
        except Exception as e:
            print(f"  ERROR moving id={doc_id} {path} -> {target_path}: {e}")
            errors += 1

    print(f"\n  ✓ moved: {moved}")
    print(f"  - skipped (already organized): {skipped_exists}")
    print(f"  - skipped (file missing on disk): {skipped_missing}")
    print(f"  ⚠ errors: {errors}")

    # Final layout
    cur.execute("""
        SELECT
          CASE
            WHEN file_path LIKE '/root/landtek/uploads/MWK-001/%%' THEN 'MWK-001/'
            WHEN file_path LIKE '/root/landtek/uploads/Paracale-001/%%' THEN 'Paracale-001/'
            WHEN file_path LIKE '/root/landtek/uploads/Owner/%%' THEN 'Owner/'
            WHEN file_path LIKE '/root/landtek/uploads/Unclassified/%%' THEN 'Unclassified/'
            WHEN file_path LIKE '/root/landtek/uploads/scannerpro/%%' THEN 'scannerpro/'
            WHEN file_path LIKE '/root/landtek/uploads/%%' THEN '(flat)'
            ELSE 'other'
          END AS bucket,
          count(*)
          FROM documents WHERE file_path IS NOT NULL
         GROUP BY bucket ORDER BY count DESC;
    """)
    print(f"\n  Final layout:")
    for bucket, count in cur.fetchall():
        print(f"    {bucket}: {count}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
