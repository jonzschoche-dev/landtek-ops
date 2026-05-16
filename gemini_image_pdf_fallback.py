#!/usr/bin/env python3
"""Phase 1B — run Gemini Vision specifically on image-only PDFs that PyMuPDF couldn't read.

Targets: docs with extracted_text<200 chars OR NULL, has drive_file_id, mime=pdf.
"""
import argparse, json, os, sys, time
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
UPLOADS = "/root/landtek/uploads"


def load_env():
    env = {}
    with open("/root/landtek/.env") as f:
        for l in f:
            if "=" in l and not l.startswith("#"):
                k, _, v = l.strip().partition("="); env[k.strip()] = v.strip()
    return env


def gemini_extract(pdf_path, api_key):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    with open(pdf_path, "rb") as f:
        data = f.read()
    model = genai.GenerativeModel("gemini-2.5-flash")
    import sys as _sys; _sys.path.insert(0, "/root/landtek")
    from llm_billing import gemini_call
    result = gemini_call(
        model,
        called_from="gemini_image_pdf_fallback",
        purpose="image_pdf_ocr",
        case_file="MWK-001",
        model_name="gemini-2.5-flash",
        contents=[
            {"mime_type": "application/pdf", "data": data},
            "Extract ALL text from this PDF, preserving line breaks. If a page is illegible, note [illegible page] and continue. Output ONLY the text."
        ])
    return (result.text or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()

    env = load_env()
    api_key = env.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("FATAL: GEMINI_API_KEY missing")

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, smart_filename, case_file, drive_file_id, mime_type
          FROM documents
         WHERE (extracted_text IS NULL OR length(extracted_text) < 200)
           AND drive_file_id IS NOT NULL
         ORDER BY case_file NULLS LAST, id DESC
         LIMIT %s
    """, (args.limit,))
    docs = cur.fetchall()
    print(f"  {len(docs)} candidate image-PDFs")

    sys.path.insert(0, "/root/landtek")
    from batch_extract_unextracted import find_local_file, drive_client, download_drive_file

    svc = drive_client()
    ok, fail, skipped = 0, 0, 0
    for d in docs:
        local = find_local_file(d)
        if not local:
            local = os.path.join(UPLOADS, f"{d['id']}_drive.pdf")
            try:
                download_drive_file(svc, d["drive_file_id"], local)
            except Exception as e:
                print(f"  ✗ #{d['id']} download fail: {str(e)[:80]}")
                fail += 1; continue
        if not local.lower().endswith(".pdf"):
            skipped += 1; continue
        try:
            text = gemini_extract(local, api_key)
            if not text or len(text) < 100:
                fail += 1
                print(f"  ⊘ #{d['id']} gemini returned {len(text or '')} chars")
                continue
            cur.execute("""UPDATE documents SET extracted_text=%s, text_length=%s,
                              status='extracted_gemini', updated_at=now() WHERE id=%s""",
                        (text, len(text), d["id"]))
            ok += 1
            print(f"  ✓ #{d['id']} {len(text):>6,} chars  {(d['smart_filename'] or '')[:60]}")
            time.sleep(1.5)  # rate limit
        except Exception as e:
            fail += 1
            print(f"  ✗ #{d['id']}: {str(e)[:120]}")
            time.sleep(3)

    print(f"\n  ok={ok}  fail={fail}  skipped={skipped}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
