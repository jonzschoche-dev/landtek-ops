#!/usr/bin/env python3
"""Batch-extract text for unextracted documents (deploy_115-B).

Pipeline per doc:
  1. If local file exists in /root/landtek/uploads/ → use it
  2. Else download from Drive via service account
  3. Try PyMuPDF (fitz) text extraction — free, fast (handles text-PDFs)
  4. If extracted text < 200 chars → fall back to Gemini Vision
  5. Update documents.extracted_text + length

Targets:
  --case MWK-001     (default — prioritize MWK-001)
  --limit N          (default 50)
  --gemini-fallback  (allow Gemini calls, paid)
"""
import argparse
import io
import os
import re
import sys
import time
from datetime import datetime
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
SA_PATH = "/root/landtek/google-creds.json"
UPLOADS = "/root/landtek/uploads"


def load_env():
    env = {}
    with open("/root/landtek/.env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, _, v = line.strip().partition("=")
                env[k.strip()] = v.strip()
    return env


def drive_client():
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        SA_PATH, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def download_drive_file(svc, drive_file_id, out_path):
    from googleapiclient.http import MediaIoBaseDownload
    req = svc.files().get_media(fileId=drive_file_id, supportsAllDrives=True)
    with open(out_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, req, chunksize=2_000_000)
        done = False
        while not done:
            status, done = downloader.next_chunk()
    return os.path.getsize(out_path)


def pymupdf_extract(pdf_path):
    """Extract text via PyMuPDF. Returns text or None on failure."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text.strip()
    except Exception as e:
        return None


def gemini_vision_extract(pdf_path, api_key):
    """Fallback to Gemini Vision when PyMuPDF returns nothing (image PDFs)."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        with open(pdf_path, "rb") as f:
            data = f.read()
        # Use 2.5-flash (faster, cheaper) for general extraction
        model = genai.GenerativeModel("gemini-2.5-flash")
        import sys as _sys; _sys.path.insert(0, "/root/landtek")
        from llm_billing import gemini_call
        result = gemini_call(
            model,
            called_from="batch_extract_unextracted",
            purpose="vision_fallback",
            case_file="MWK-001",
            model_name="gemini-2.5-flash",
            contents=[
                {"mime_type": "application/pdf", "data": data},
                "Extract ALL text from this PDF, preserving line breaks. If a page is illegible, note '[illegible page]' and continue. Output ONLY the text, no commentary."
            ])
        return (result.text or "").strip()
    except Exception as e:
        print(f"  ⚠ Gemini failed: {str(e)[:200]}", file=sys.stderr)
        return None


def find_local_file(doc):
    """Try to find a local file for this doc id."""
    sf = (doc.get("smart_filename") or "").strip()
    paths_to_try = []
    if sf:
        paths_to_try.append(os.path.join(UPLOADS, f"{doc['id']}_{re.sub(r'[^A-Za-z0-9._-]', '_', sf)[:120]}"))
        paths_to_try.append(os.path.join(UPLOADS, doc.get("case_file") or "", f"{doc['id']}_{re.sub(r'[^A-Za-z0-9._-]', '_', sf)[:120]}"))
    # by id pattern
    for f in os.listdir(UPLOADS):
        if f.startswith(f"{doc['id']}_"):
            paths_to_try.insert(0, os.path.join(UPLOADS, f))
    for p in paths_to_try:
        if os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--gemini-fallback", action="store_true",
                    help="allow paid Gemini calls for image PDFs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env = load_env()
    api_key = env.get("GEMINI_API_KEY")
    if args.gemini_fallback and not api_key:
        print("FATAL: --gemini-fallback set but no GEMINI_API_KEY")
        sys.exit(1)

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.case == "ANY":
        cur.execute("""
            SELECT id, smart_filename, case_file, drive_file_id, mime_type
              FROM documents
             WHERE (extracted_text IS NULL OR length(extracted_text) < 200)
               AND drive_file_id IS NOT NULL
             ORDER BY id DESC
             LIMIT %s
        """, (args.limit,))
    else:
        cur.execute("""
            SELECT id, smart_filename, case_file, drive_file_id, mime_type
              FROM documents
             WHERE (extracted_text IS NULL OR length(extracted_text) < 200)
               AND drive_file_id IS NOT NULL
               AND (case_file = %s OR (%s = 'NULL_CASE' AND (case_file IS NULL OR case_file = '')))
             ORDER BY id DESC
             LIMIT %s
        """, (args.case, args.case, args.limit))
    docs = cur.fetchall()
    print(f"  {len(docs)} unextracted docs to process (case={args.case})")
    if not docs:
        return

    svc = drive_client()
    stats = {"pymupdf_ok": 0, "gemini_ok": 0, "failed": 0, "skipped_pdf": 0}

    for d in docs:
        doc_id = d["id"]
        drive_id = d["drive_file_id"]
        mime = (d.get("mime_type") or "").lower()
        # Assume PDF unless we see a clearly non-PDF mime
        if mime and "pdf" not in mime and "document" not in mime and "octet-stream" not in mime:
            print(f"  ⊘ #{doc_id} non-PDF mime={mime}")
            stats["skipped_pdf"] += 1
            continue

        # Find/download local file
        local = find_local_file(d)
        if not local:
            local = os.path.join(UPLOADS, f"{doc_id}_drive.pdf")
            try:
                size = download_drive_file(svc, drive_id, local)
                print(f"  ↓ #{doc_id} downloaded {size:,}b → {local}")
            except Exception as e:
                print(f"  ✗ #{doc_id} download failed: {str(e)[:150]}")
                stats["failed"] += 1
                continue

        # Extract with PyMuPDF
        text = pymupdf_extract(local)
        method = "pymupdf"
        if not text or len(text) < 200:
            if args.gemini_fallback and api_key:
                print(f"  ⤴ #{doc_id} PyMuPDF returned {len(text or '')} chars — trying Gemini")
                text = gemini_vision_extract(local, api_key)
                method = "gemini"
                time.sleep(1)  # rate limit
            elif not text:
                stats["failed"] += 1
                print(f"  ✗ #{doc_id} PyMuPDF empty + no Gemini fallback")
                continue

        if not text or len(text) < 100:
            stats["failed"] += 1
            print(f"  ✗ #{doc_id} both methods returned nothing usable")
            continue

        if args.dry_run:
            print(f"  [DRY] #{doc_id} {method} → {len(text)} chars")
            continue

        cur.execute("""
            UPDATE documents
               SET extracted_text = %s,
                   text_length = %s,
                   status = 'extracted',
                   updated_at = now()
             WHERE id = %s
        """, (text, len(text), doc_id))
        if method == "pymupdf":
            stats["pymupdf_ok"] += 1
        else:
            stats["gemini_ok"] += 1
        print(f"  ✓ #{doc_id} {method:8s} {len(text):>7,} chars  {(d['smart_filename'] or '')[:60]}")

    print(f"\n  pymupdf: {stats['pymupdf_ok']}  gemini: {stats['gemini_ok']}  failed: {stats['failed']}  non-pdf: {stats['skipped_pdf']}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
