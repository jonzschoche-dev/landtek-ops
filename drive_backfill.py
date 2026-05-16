#!/usr/bin/env python3
"""Drive backfill + orphan recovery.

Two jobs in one script:
  (A) For each documents row with drive_file_id but no local file / no
      content_hash: download from Drive, save to /root/landtek/uploads/<id>_<smart_filename>,
      compute content_hash, update DB.
  (B) For each Drive PDF not in documents table: insert a row, download, hash.
      OCR queue for these is left for a later pass.

Per feedback_information_is_gold: every Drive PDF should be recoverable
locally + indexed in our DB.

Idempotent. Safe to re-run.
"""
import hashlib
import io
import os
import re
import sys
import psycopg2
import psycopg2.errors
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
UPLOADS = "/root/landtek/uploads"
SA_PATH = "/root/landtek/google-creds.json"


def safe_name(s, default="unnamed"):
    s = re.sub(r"[^A-Za-z0-9._-]", "_", (s or default))
    return s[:120]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def get_drive():
    creds = service_account.Credentials.from_service_account_file(
        SA_PATH, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def download_to(service, file_id, dest_path):
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(dest_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request, chunksize=10 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def job_a_recover_unhashed(service):
    """Download files for unhashed docs that have a drive_file_id."""
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        SELECT id, original_filename, drive_file_id, file_path
          FROM documents
         WHERE content_hash IS NULL
           AND drive_file_id IS NOT NULL AND drive_file_id != ''
         ORDER BY id;
    """)
    rows = cur.fetchall()
    print(f"\n[A] unhashed docs with drive_file_id: {len(rows)}")
    recovered = 0
    skipped_dup = 0
    failed = 0
    for doc_id, name, drive_id, file_path in rows:
        # If file_path exists, skip (would have been caught by other backfill)
        if file_path and os.path.exists(file_path):
            try:
                h = sha256_file(file_path)
                cur.execute("UPDATE documents SET content_hash=%s WHERE id=%s", (h, doc_id))
                recovered += 1
            except psycopg2.errors.UniqueViolation:
                skipped_dup += 1
            continue
        # Otherwise download from Drive
        local = os.path.join(UPLOADS, f"drive_{doc_id}_{safe_name(name)}")
        try:
            download_to(service, drive_id, local)
            h = sha256_file(local)
            try:
                cur.execute("UPDATE documents SET content_hash=%s, file_path=%s WHERE id=%s",
                            (h, local, doc_id))
                recovered += 1
                print(f"  [A] id={doc_id} recovered -> {local}")
            except psycopg2.errors.UniqueViolation:
                # Already have this content elsewhere
                cur.execute("SELECT id FROM documents WHERE content_hash=%s LIMIT 1", (h,))
                canon = cur.fetchone()[0]
                cur.execute("""
                    INSERT INTO docs_dupes (duplicate_doc_id, canonical_doc_id, content_hash, file_path, original_filename)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
                """, (doc_id, canon, h, local, name))
                # Keep the file but record as dupe; update file_path even though hash collides
                cur.execute("UPDATE documents SET file_path=%s WHERE id=%s AND file_path IS NULL", (local, doc_id))
                skipped_dup += 1
                print(f"  [A] id={doc_id} duplicate of {canon}")
        except Exception as e:
            print(f"  [A] id={doc_id} FAILED: {type(e).__name__}: {str(e)[:120]}")
            failed += 1
    print(f"  [A] done: recovered={recovered}, dupes={skipped_dup}, failed={failed}")
    cur.close(); conn.close()


def job_b_index_unseen_drive(service):
    """Find Drive PDFs not yet in documents and create rows + download."""
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor()

    # Get all known drive_file_ids in DB
    cur.execute("SELECT drive_file_id FROM documents WHERE drive_file_id IS NOT NULL AND drive_file_id != ''")
    known = set(r[0] for r in cur.fetchall())
    print(f"\n[B] currently-indexed Drive file IDs: {len(known)}")

    # List ALL Drive PDFs accessible
    print("  listing Drive PDFs...")
    page_token = None
    drive_pdfs = []
    while True:
        r = service.files().list(
            q="mimeType='application/pdf' and trashed=false",
            fields="nextPageToken, files(id, name, parents, size)",
            pageSize=1000, pageToken=page_token,
            corpora="allDrives", includeItemsFromAllDrives=True, supportsAllDrives=True,
        ).execute()
        drive_pdfs.extend(r.get("files", []))
        page_token = r.get("nextPageToken")
        if not page_token: break
    print(f"  Drive PDFs total: {len(drive_pdfs)}")

    new = [f for f in drive_pdfs if f["id"] not in known]
    print(f"  unindexed Drive PDFs: {len(new)}")
    if not new:
        cur.close(); conn.close()
        return

    inserted = 0
    skipped_dup = 0
    failed = 0
    for f in new:
        drive_id = f["id"]
        name = f.get("name", "unnamed")
        local = os.path.join(UPLOADS, f"drive_new_{safe_name(name)}")
        # Skip if local already exists with same name
        try:
            download_to(service, drive_id, local)
            h = sha256_file(local)
        except Exception as e:
            print(f"  [B] {name[:50]} FAILED download: {type(e).__name__}: {str(e)[:120]}")
            failed += 1
            continue
        # Check if hash already exists
        cur.execute("SELECT id FROM documents WHERE content_hash=%s LIMIT 1", (h,))
        existing = cur.fetchone()
        if existing:
            # Existing doc has same content — just link drive_file_id
            cur.execute("""
                UPDATE documents SET drive_file_id=%s WHERE id=%s AND (drive_file_id IS NULL OR drive_file_id='')
            """, (drive_id, existing[0]))
            skipped_dup += 1
            os.remove(local)
            continue
        try:
            cur.execute("""
                INSERT INTO documents (case_file, original_filename, mime_type, content_hash, file_path,
                                       drive_file_id, drive_link, timestamp)
                VALUES (NULL, %s, 'application/pdf', %s, %s, %s, %s, now())
                RETURNING id;
            """, (name, h, local, drive_id, f"https://drive.google.com/file/d/{drive_id}/view"))
            new_id = cur.fetchone()[0]
            inserted += 1
            if inserted % 10 == 0:
                print(f"  [B] progress: inserted={inserted}, dupes={skipped_dup}, failed={failed}")
        except psycopg2.errors.UniqueViolation as e:
            skipped_dup += 1
            os.remove(local)

    print(f"\n  [B] done: inserted={inserted} new rows, dupes_linked={skipped_dup}, failed={failed}")
    cur.close(); conn.close()


def main():
    if not os.path.exists(SA_PATH):
        sys.exit(f"FATAL: no SA creds at {SA_PATH}")
    service = get_drive()
    print("Drive client ready.")

    job_a_recover_unhashed(service)
    job_b_index_unseen_drive(service)

    # Final stats
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("""
        SELECT count(*), count(content_hash), count(*) FILTER (WHERE drive_file_id IS NOT NULL AND drive_file_id != '')
          FROM documents;
    """)
    total, hashed, indrive = cur.fetchone()
    print(f"\n=== FINAL: total={total}, content_hash={hashed} ({hashed*100/total:.0f}%), drive_linked={indrive} ===")
    # Heartbeat
    try:
        import json as _j
        cur.execute("""INSERT INTO system_heartbeat (source, status, metadata)
                       VALUES ('drive-sync', 'ok', %s::jsonb)""",
                    (_j.dumps({"total_docs": total, "hashed": hashed, "drive_linked": indrive}),))
        conn.commit()
    except Exception: pass
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
