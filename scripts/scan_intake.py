#!/usr/bin/env python3
"""scan_intake.py — continuous ScannerPro → corpus intake, ALIGNED to the 2026-07 pipeline (deploy_882).

Supersedes autonomous/scannerpro_ingest.py (May-era), which MISALIGNED with the architecture we hardened:
  ✗ it auto-assigned case_file from a weak per-doc Gemini classify (43 scans → Paracale-001 unverified) — the
    exact A5/A54 client-separation risk the whole ingest layer was rebuilt to prevent;
  ✗ it MOVED the Drive file into a client folder on that weak signal (physical cross-client misfile);
  ✗ it earned no provenance (0/160 model_used) so nothing passed the 5-signal connect-verify gate.

This intake does the LANDING ONLY, correctly, and hands off to the standing pipeline that already works
(proven on the 160 May scans: 158 got text, 159 enriched):
  land UNCLASSIFIED (case_file/matter_code NULL) → enroll flagged in ocr_quality → the reocr LADDER extracts
  text → reenrich.py assigns matter_code DETERMINISTICALLY (docket-exact registry match + cross-client
  tripwire, A5/A54-safe) → embed. No inline LLM classify. No Drive move (dedup makes re-runs idempotent, so
  the scan can stay in ScannerPro untouched).

Why not ingest_drive_folder.py? That one FORCE-TAGS a whole folder to one --case (correct for a per-client
folder). ScannerPro is a MIXED intake — scans from every client land in it (the May batch was 97 MWK / 43
Paracale / others) — so a single force-tag would misfile everyone else. Land-UNCLASSIFIED + deterministic
per-doc matter assignment is the only A5-safe fit for a mixed intake folder. (An unmatched scan stays
UNCLASSIFIED and surfaces for operator review — correct-and-held beats classified-and-wrong.)

Idempotent: dedup by drive_file_id (already a doc → skip) AND sha256 (same bytes under a new file id →
recorded as duplicate, not re-ingested). Safe to run on a timer over the same folder forever.

USAGE: python3 scripts/scan_intake.py [--dry-run] [--limit N] [--folder FID]
"""
import argparse, hashlib, os, sys
from pathlib import Path
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
SA_KEY = os.environ.get("SA_KEY", "/root/landtek/google-creds.json")
# The canonical ScannerPro folder inside the (single, canonical) LANDTEK Drive — the scanner's landing zone.
DEFAULT_FOLDER = os.environ.get("SCANNERPRO_FOLDER_ID", "1TAksYrG-BzoOfc3UEIEZgJ6lBzu3IzmY")
DOWNLOAD_DIR = Path("/root/landtek/uploads/scannerpro")


def _drive():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds)


def _list_pdfs(drive, folder):
    files, tok = [], None
    while True:
        r = drive.files().list(
            q=f"'{folder}' in parents and trashed=false",
            fields="nextPageToken, files(id,name,mimeType,size,md5Checksum)",
            pageToken=tok, pageSize=200).execute()
        files.extend(r.get("files", []))
        tok = r.get("nextPageToken")
        if not tok:
            break
    return [f for f in files
            if f.get("mimeType") == "application/pdf" or f["name"].lower().endswith(".pdf")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--folder", default=DEFAULT_FOLDER)
    args = ap.parse_args()
    dry = args.dry_run

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    drive = _drive()
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = _list_pdfs(drive, args.folder)[: args.limit]
    mode = "DRY-RUN" if dry else "LIVE"
    print(f"  [scan-intake {mode}] {len(pdfs)} PDF(s) in ScannerPro ({args.folder})\n")

    landed = dup = skip_existing = err = 0
    new_ids = []
    for f in pdfs:
        fid, fname = f["id"], f["name"]
        cur.execute("SELECT id, ingest_status FROM documents WHERE drive_file_id=%s", (fid,))
        ex = cur.fetchone()
        if ex:                                            # this exact Drive file already a doc
            skip_existing += 1
            continue

        if dry:
            print(f"    NEW   {fname[:60]}")
            landed += 1
            continue

        # download bytes to hash + land
        local = DOWNLOAD_DIR / f"{fid}.pdf"
        try:
            if not local.exists():
                from googleapiclient.http import MediaIoBaseDownload
                req = drive.files().get_media(fileId=fid)
                with open(local, "wb") as fh:
                    dl = MediaIoBaseDownload(fh, req); done = False
                    while not done:
                        _, done = dl.next_chunk()
            sha = hashlib.sha256(local.read_bytes()).hexdigest()
        except Exception as e:
            print(f"    ✗ {fname[:40]}: {str(e)[:60]}"); err += 1; continue

        cur.execute("SELECT id FROM documents WHERE sha256=%s AND drive_file_id<>%s", (sha, fid))
        d = cur.fetchone()
        if d:                                             # same bytes already ingested under another id
            print(f"    DUP   {fname[:50]} == doc {d['id']}")
            dup += 1
            continue

        # LAND — unclassified, provenance-unearned (the ladder/reenrich earn it); A5-safe (no matter guess)
        cur.execute("""
            INSERT INTO documents
              (drive_file_id, original_filename, smart_filename, file_name, file_path,
               content_hash, sha256, mime_type, master_form, ingest_source, ingest_status,
               case_file, matter_code, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'application/pdf','scanned','scannerpro','ingested',
                    NULL, NULL, now())
            RETURNING id""",
            (fid, fname, fname, fname, str(local), sha, sha))
        did = cur.fetchone()["id"]
        # enroll flagged so the reocr LADDER picks it up next sweep (0 text → OCR from scratch)
        cur.execute("""INSERT INTO ocr_quality (doc_id, score, chars, word_quality, flagged, scored_at)
                       VALUES (%s, 0.0, 0, 0.0, true, now())
                       ON CONFLICT (doc_id) DO NOTHING""", (did,))
        new_ids.append(did); landed += 1
        print(f"    ✓ doc {did}  {fname[:52]}")

    print(f"\n  Summary [{mode}]:")
    print(f"    landed (new, unclassified → OCR queue): {landed}")
    print(f"    duplicate bytes (skipped): {dup}")
    print(f"    already ingested (skipped): {skip_existing}")
    print(f"    download errors: {err}")
    if new_ids:
        print(f"    new doc ids: {new_ids}")
        print(f"    → OCR ladder (reocr sweeps ~8-20m) → reenrich (hourly, matter via docket-exact) → embed")
    if dry:
        print("\n  DRY-RUN — nothing written.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
