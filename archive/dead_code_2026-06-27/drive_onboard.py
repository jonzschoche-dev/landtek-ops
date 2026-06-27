#!/usr/bin/env python3
"""drive_onboard.py — make the canonical corpus COMPLETE w.r.t. the Drive.

Walks the whole LANDTEK Drive tree and ingests every PDF/image that isn't already
in the corpus, so any document in the Drive becomes a canonical, findable doc —
by CONTENT, not by its (often lying) filename. Text-layer PDFs get free fitz text
immediately; image-only scans are left for the corpus_backfill daemon to OCR +
embed. Idempotent: dedups by drive_file_id and by content_hash.

Run once to backfill, and on a cron so new Drive uploads auto-onboard (the
'every document in the corpus, no exceptions' guarantee, extended to the Drive).

  python3 drive_onboard.py --limit 8   # test
  python3 drive_onboard.py             # full sweep
"""
import argparse, hashlib, io, sys
import psycopg2, psycopg2.extras
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import fitz

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
ROOT = "1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP"
creds = service_account.Credentials.from_service_account_file(
    "/root/landtek/google-creds.json", scopes=["https://www.googleapis.com/auth/drive.readonly"])
svc = build("drive", "v3", credentials=creds, cache_discovery=False)


def walk(folder, path=""):
    out, pt = [], None
    while True:
        r = svc.files().list(
            q=f"'{folder}' in parents and trashed=false",
            fields="nextPageToken, files(id,name,mimeType)",
            pageSize=1000, pageToken=pt,
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        for f in r.get("files", []):
            if f["mimeType"] == "application/vnd.google-apps.folder":
                out += walk(f["id"], path + "/" + f["name"])
            else:
                out.append((path + "/" + f["name"], f["id"], f["mimeType"], f["name"]))
        pt = r.get("nextPageToken")
        if not pt:
            break
    return out


def download(fid):
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=fid, supportsAllDrives=True))
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


def pdf_text(data):
    try:
        d = fitz.open(stream=data, filetype="pdf")
        t = "\n".join(p.get_text() for p in d)
        d.close()
        return t.strip()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    files = walk(ROOT)
    ingestible = [f for f in files if "pdf" in f[2] or f[2].startswith("image/")]
    cur.execute("SELECT drive_file_id FROM documents WHERE drive_file_id IS NOT NULL")
    have = {r["drive_file_id"] for r in cur.fetchall()}
    todo = [f for f in ingestible if f[1] not in have]
    print(f"Drive: {len(files)} files, {len(ingestible)} PDFs/images, {len(have)} already onboarded, {len(todo)} to ingest")

    ingested = deduped = errors = 0
    for path, fid, mime, name in todo:
        try:
            data = download(fid)
        except Exception as e:
            errors += 1
            continue
        chash = hashlib.sha256(data).hexdigest()
        cur.execute("SELECT 1 FROM documents WHERE content_hash=%s LIMIT 1", (chash,))
        if cur.fetchone():
            deduped += 1
            continue
        txt = pdf_text(data) if "pdf" in mime else ""
        case_file = "MWK-001" if "mary worrick" in path.lower() else None
        try:
            cur.execute("""INSERT INTO documents
                (master_form, ingest_source, drive_file_id, original_filename, smart_filename,
                 mime_type, content_hash, case_file, extracted_text, summary)
                VALUES ('digital','drive',%s,%s,%s,%s,%s,%s,%s,%s)""",
                (fid, name, name, mime, chash, case_file, (txt or None),
                 f"Drive path: {path[:300]}"))
            ingested += 1
            if ingested % 20 == 0:
                print(f"  ingested {ingested}...")
        except psycopg2.errors.UniqueViolation:
            deduped += 1
        if args.limit and ingested >= args.limit:
            break

    print(f"\n[drive_onboard] ingested {ingested} new canonical docs "
          f"({deduped} dedup-skipped, {errors} errors). "
          f"Image-only ones now queued for the OCR daemon.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
