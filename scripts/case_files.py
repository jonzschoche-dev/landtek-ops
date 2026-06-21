#!/usr/bin/env python3
"""case_files.py — find every file of a case in the corpus, with links to the originals. $0.

For a matter: each linked document — what it is, whether it's been read into verified facts, how many
verified facts it grounds, its OCR legibility, and a link to the ORIGINAL (Drive). The fast answer to
"pull everything on this case." Sorted by evidentiary weight (facts it grounds) so the load-bearing
documents are on top.

  python3 scripts/case_files.py MWK-CV26360
  python3 scripts/case_files.py MWK-CV26360 --read-only   # only docs that produced verified facts
"""
import sys

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def link(drive_link, drive_id, path):
    if drive_link:
        return drive_link
    if drive_id:
        return f"https://drive.google.com/file/d/{drive_id}/view"
    return path or "(no link)"


def main():
    a = sys.argv
    if len(a) < 2 or a[1].startswith("-"):
        print(__doc__); return
    mc = a[1]
    read_only = "--read-only" in a
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("""
        SELECT d.id, coalesce(d.original_filename, d.smart_filename, d.file_name, '?') fn,
               d.drive_link, d.drive_file_id, d.file_path,
               coalesce(q.flagged, false) garbage, length(coalesce(d.extracted_text,'')) tlen,
               (SELECT count(*) FROM matter_facts f WHERE f.provenance_level='verified'
                  AND f.source_kind='doc' AND f.source_id=d.id::text) nfacts
        FROM documents d LEFT JOIN ocr_quality q ON q.doc_id=d.id
        WHERE d.matter_code=%s ORDER BY nfacts DESC, tlen DESC""", (mc,))
    rows = cur.fetchall()
    if read_only:
        rows = [r for r in rows if r[7] > 0]
    print("=" * 92)
    print(f"CASE FILES — {mc}  ({len(rows)} documents)")
    print("=" * 92)
    read = sum(1 for r in rows if r[7] > 0)
    legible = sum(1 for r in rows if not r[5] and r[6] >= 1000)
    print(f"read into verified facts: {read} · legible: {legible} · total: {len(rows)}\n")
    for did, fn, dl, did_drive, path, garbage, tlen, nfacts in rows:
        st = f"✅{nfacts}f" if nfacts else ("⛔OCR" if (garbage or tlen < 1000) else "📄")
        print(f"  doc:{did:<5} {st:6} {fn[:52]:52} {link(dl, did_drive, path)}")


if __name__ == "__main__":
    main()
