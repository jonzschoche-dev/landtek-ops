#!/usr/bin/env python3
"""drive_offload.py — Drive-canonical PDF policy: push local PDFs to Drive, then drop the local file.

Operator policy: PDFs belong in Google Drive. Once a doc is properly ingested (text in the DB + a copy in
Drive) we don't waste local storage/compute holding the PDF. For each doc with a local file_path but NO
drive_file_id, this:
  1. uploads the PDF to the LANDTEK Drive folder (via the proven /api/upload_to_drive endpoint)
  2. records documents.drive_file_id + drive_link
  3. deletes the local file (so /files/c/<id> then streams from Drive; the extracted text stays in the DB)

OPERATOR-RUN: steps 2–3 mutate the shared DB + filesystem, which the autonomous agent is blocked from.
Safe + staged: --plan is read-only; --go --keep-local uploads + records but keeps the local file (so you
can verify Drive serves before deleting anything).

  python3 scripts/drive_offload.py                 # PLAN — count + total MB (read-only)
  python3 scripts/drive_offload.py --go --keep-local --limit 5   # upload+record 5, keep local (verify)
  python3 scripts/drive_offload.py --go            # upload+record+delete-local (full policy)
"""
import json
import os
import subprocess
import sys

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ROOT = os.environ.get("LANDTEK_DRIVE_FOLDER", "1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP")
UPLOAD_URL = os.environ.get("LANDTEK_UPLOAD_URL", "http://localhost:8765/api/upload_to_drive")


def _upload(fp, fn, mime):
    r = subprocess.run(["curl", "-s", "-F", f"file=@{fp}", "-F", f"folder_id={ROOT}",
                        "-F", f"target_filename={fn}", "-F", f"mime_type={mime}", UPLOAD_URL],
                       capture_output=True, text=True, timeout=300)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"ok": False, "status": r.stdout[:160]}


def main():
    go = "--go" in sys.argv
    keep = "--keep-local" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("""SELECT id, file_path, coalesce(original_filename,smart_filename,'document.pdf'),
                   coalesce(mime_type,'application/pdf')
                   FROM documents WHERE file_path IS NOT NULL AND coalesce(drive_file_id,'')=''
                   ORDER BY id""")
    rows = [r for r in cur.fetchall() if r[1] and os.path.exists(r[1])]
    mb = sum(os.path.getsize(r[1]) for r in rows) / 1e6
    print(f"local-only PDFs (on disk, no Drive copy): {len(rows)} files, {mb:.0f} MB total")
    if not go:
        for did, fp, fn, mt in rows[:15]:
            print(f"  doc:{did:>5}  {os.path.getsize(fp)/1e6:>6.2f} MB  {fn[:48]}")
        print("\n(PLAN only — --go --keep-local to upload+record (keep file), --go for full offload)")
        return

    done = fail = 0
    for did, fp, fn, mt in (rows[:limit] if limit else rows):
        res = _upload(fp, fn, mt)
        if not res.get("ok"):
            fail += 1; print(f"  ✗ doc:{did} upload failed: {res.get('status')}"); continue
        cur.execute("UPDATE documents SET drive_file_id=%s, drive_link=coalesce(nullif(drive_link,''),%s) WHERE id=%s",
                    (res["drive_file_id"], res.get("drive_link"), did))
        if not keep:
            try:
                os.remove(fp)
                cur.execute("UPDATE documents SET file_path=NULL WHERE id=%s", (did,))
            except OSError as e:
                print(f"    (could not delete local {fp}: {e})")
        done += 1
        print(f"  ✓ doc:{did} → drive:{res['drive_file_id']} {'(local kept)' if keep else '(local dropped)'}")
    print(f"[drive_offload] {done} offloaded, {fail} failed")


if __name__ == "__main__":
    main()
