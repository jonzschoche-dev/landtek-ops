#!/usr/bin/env python3
"""caption_images.py - Gemini Vision captioning for image documents.

For every documents row where mime_type LIKE 'image/%' and vision_caption is
empty, fetch the image bytes (from file_path or Drive) and ask Gemini
2.5 Flash to describe what's visible. The caption is stored both in
vision_caption (for inspection) AND appended to extracted_text (so the
existing query_documents keyword search finds it).

Caption prompt is engineered to surface:
  - People (count, gender, age range, distinctive features, names if visible in caption)
  - Setting (indoor/outdoor, building, landscape)
  - Objects, signs, text visible in image
  - Date hints (clothing era, technology, visible dates)

Idempotent. Skips images already captioned. Cost ~$0.0001 per image at
Gemini 2.5 Flash rates.

Usage:
  python3 scripts/caption_images.py              # caption all uncaptioned
  python3 scripts/caption_images.py --limit 5    # smoke test
  python3 scripts/caption_images.py --doc-id 793 # one specific image
  python3 scripts/caption_images.py --recaption  # ignore existing captions

Audited via app.actor='caption_images'.
"""
import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.request

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
GOOGLE_CREDS = "/root/landtek/google-creds.json"

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

CAPTION_PROMPT = """You are captioning an image for a property/legal document database.
Describe what's visible in this image as a SEARCHABLE caption. Include:

1. People: count, apparent gender/age range, any distinctive features (clothing,
   uniform, props they're holding). Quote any name labels VISIBLE in the image
   (signs, captions, banners) — do NOT guess who someone is from face alone.
2. Setting: indoor/outdoor, the building or landscape, any visible signage,
   street/place names.
3. Document elements: if this is a scanned form/certificate, name the form,
   list visible fields and their values (names, dates, IDs).
4. Distinctive objects: vehicles, equipment, weapons (eskrima sticks, etc.).
5. Date hints: clothing era, technology, any visible date stamps.

Output 2-5 sentences of factual, dense description. No speculation. If text is
visible in the image, quote it verbatim. If unreadable, say "(illegible)".
Begin with the most distinctive concrete fact."""


def load_gemini_key():
    env = "/root/landtek/.env"
    with open(env) as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    raise RuntimeError("GEMINI_API_KEY missing")


_drive_client = None
def get_drive():
    global _drive_client
    if _drive_client is not None:
        return _drive_client
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    _drive_client = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _drive_client


def fetch_image_bytes(file_path, drive_file_id, drive_link=None):
    """Return (bytes, source) or raise. Tries:
       1. file_path on disk
       2. drive_link if it's actually a local path (legacy schema where the
          email-ingest pipeline stored the local upload path here)
       3. Drive API with drive_file_id
    """
    if file_path and os.path.exists(file_path):
        with open(file_path, "rb") as f:
            return f.read(), "local(file_path)"
    # Legacy: some rows store the local upload path in drive_link (email ingest)
    if drive_link and drive_link.startswith("/") and os.path.exists(drive_link):
        with open(drive_link, "rb") as f:
            return f.read(), "local(drive_link)"
    if drive_file_id:
        from googleapiclient.http import MediaIoBaseDownload
        svc = get_drive()
        buf = io.BytesIO()
        req = svc.files().get_media(fileId=drive_file_id, supportsAllDrives=True)
        downloader = MediaIoBaseDownload(buf, req, chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue(), "drive"
    raise RuntimeError("no fetchable source (file_path, drive_link path, drive_file_id all empty/missing)")


def gemini_caption(api_key, image_bytes, mime_type):
    """Call Gemini Vision. Return caption string."""
    payload = {
        "contents": [{
            "parts": [
                {"text": CAPTION_PROMPT},
                {"inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }},
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 800,
        },
    }
    url = GEMINI_URL_TEMPLATE.format(model=GEMINI_MODEL, key=api_key)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    cands = data.get("candidates", [])
    if not cands:
        raise RuntimeError(f"no candidates from Gemini: {data}")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(f"empty caption from Gemini: {data}")
    return text


def ensure_schema(cur):
    cur.execute("""
        ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS vision_caption TEXT,
            ADD COLUMN IF NOT EXISTS vision_captioned_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS vision_caption_model TEXT
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_vision_caption_present
          ON documents ((vision_caption IS NOT NULL))
    """)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--doc-id", type=int, default=None)
    ap.add_argument("--recaption", action="store_true",
                    help="Re-caption even if vision_caption is already set")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api_key = load_gemini_key()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET app.actor = 'caption_images'")

    print("caption_images.py — Gemini Vision captioning")
    print("=" * 60)
    ensure_schema(cur)
    print("  schema ensured (vision_caption + vision_captioned_at + model)")

    where = ["mime_type LIKE 'image/%%'"]
    params = []
    if args.doc_id:
        where.append("id = %s")
        params.append(args.doc_id)
    elif not args.recaption:
        where.append("(vision_caption IS NULL OR vision_caption = '')")
    sql = f"""
        SELECT id, mime_type, file_path, drive_file_id, drive_link,
               COALESCE(smart_filename, original_filename, '') AS fn,
               COALESCE(extracted_text, '') AS extracted_text
          FROM documents
         WHERE {' AND '.join(where)}
         ORDER BY id
    """
    if args.limit:
        sql += f" LIMIT {args.limit}"
    cur.execute(sql, params)
    rows = cur.fetchall()
    print(f"  {len(rows)} image(s) to caption")

    if args.dry_run:
        for r in rows[:10]:
            print(f"    doc#{r['id']}  {r['mime_type']}  {r['fn'][:50]}")
        return

    success, fail = 0, 0
    for r in rows:
        doc_id = r["id"]
        try:
            img, src = fetch_image_bytes(r["file_path"], r["drive_file_id"], r.get("drive_link"))
        except Exception as e:
            print(f"  doc#{doc_id} FETCH FAIL: {e}")
            fail += 1
            continue

        try:
            caption = gemini_caption(api_key, img, r["mime_type"])
        except Exception as e:
            print(f"  doc#{doc_id} CAPTION FAIL: {type(e).__name__}: {str(e)[:200]}")
            fail += 1
            continue

        # Append to extracted_text so existing keyword search hits it
        existing = r["extracted_text"] or ""
        marker = "[vision_caption]"
        if marker in existing:
            # already had a caption, replace the marker section
            head, _, _ = existing.partition(marker)
            new_text = head.rstrip() + f"\n\n{marker} {caption}"
        else:
            new_text = (existing + f"\n\n{marker} {caption}").strip()

        cur.execute(
            """UPDATE documents
                  SET vision_caption = %s,
                      vision_captioned_at = now(),
                      vision_caption_model = %s,
                      extracted_text = %s,
                      updated_at = now()
                WHERE id = %s""",
            (caption, GEMINI_MODEL, new_text, doc_id),
        )
        success += 1
        snippet = caption[:90].replace("\n", " ")
        print(f"  doc#{doc_id} OK ({src}, {len(img):,}B) → {snippet}...")
        time.sleep(0.4)  # gentle rate limit

    cur.close()
    conn.close()
    print()
    print(f"  DONE: {success} captioned, {fail} failed")


if __name__ == "__main__":
    main()
