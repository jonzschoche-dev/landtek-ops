#!/usr/bin/env python3
"""reocr_gemini.py — heightened re-OCR of low-quality scans via Gemini vision (FREE tier).

Tesseract (and old extraction passes) on faint/old Philippine land scans produce text that
passes a length check but is unreadable garbage — and it lands on the documents that matter
most (TCT T-4497, the Llamanzares SPA, the title chain). Gemini vision transcribes these far
better. This renders each page → Gemini faithful transcription → replaces extracted_text.
Creditless re: Anthropic (uses GEMINI_API_KEY free-tier). Old text is backed up to reocr_backup.

  python3 reocr_gemini.py --doc 39                  # dry: show before/after sample
  python3 reocr_gemini.py --docs 25,39,97,224 --go  # re-OCR + write
"""
import base64
import json
import os
import sys
import urllib.request
import urllib.error

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
MAXPAGES = int(os.environ.get("REOCR_MAXPAGES", "15"))
PROMPT = (
    "Transcribe ALL text on this page of a Philippine land document faithfully and completely. "
    "Preserve names, dates, title/TCT numbers, entry/PE numbers, bearings (e.g. \"N. 86 deg 23' E., "
    "269.35 m\") and technical descriptions EXACTLY as written. Keep reading order. "
    "Output only the transcription — no commentary, no markdown."
)


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _gemini_page(png_b64):
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/png", "data": png_b64}},
                                    {"text": PROMPT}]}],
            "generationConfig": {"temperature": 0}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_KEY}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    return "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])


def reocr(doc_id, go=False):
    if not GEMINI_KEY:
        return {"error": "no GEMINI_API_KEY"}
    import fitz
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT file_path, length(coalesce(extracted_text,'')) FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        cur.close(); c.close(); return {"doc": doc_id, "error": "no file_path"}
    path, before = row
    try:
        d = fitz.open(path)
    except Exception as e:
        cur.close(); c.close(); return {"doc": doc_id, "error": f"open: {e}"}
    pages = min(d.page_count, MAXPAGES)
    chunks = []
    for i in range(pages):
        try:
            png = d[i].get_pixmap(matrix=fitz.Matrix(2.2, 2.2)).tobytes("png")
            chunks.append(_gemini_page(base64.b64encode(png).decode()))
        except urllib.error.HTTPError as e:
            cur.close(); c.close()
            return {"doc": doc_id, "error": f"gemini http_{e.code}: {e.read().decode('utf-8','replace')[:120]}", "page": i}
        except Exception as e:
            chunks.append(f"[page {i+1} failed: {str(e)[:60]}]")
    text = "\n\n".join(chunks).strip()
    res = {"doc": doc_id, "pages": pages, "chars_before": before, "chars_after": len(text),
           "sample": text[:300]}
    if go and len(text) >= 50:
        cur.execute("CREATE TABLE IF NOT EXISTS reocr_backup (doc_id int, old_text text, ts timestamptz DEFAULT now())")
        cur.execute("INSERT INTO reocr_backup (doc_id, old_text) SELECT id, extracted_text FROM documents WHERE id=%s", (doc_id,))
        cur.execute("""UPDATE documents SET extracted_text=%s, text_length=%s, ocr_used=true,
                       extraction_method='gemini_reocr' WHERE id=%s""", (text[:300000], len(text), doc_id))
        res["written"] = True
    cur.close(); c.close()
    return res


if __name__ == "__main__":
    a = sys.argv
    go = "--go" in a
    ids = []
    if "--doc" in a:
        ids = [int(a[a.index("--doc") + 1])]
    elif "--docs" in a:
        ids = [int(x) for x in a[a.index("--docs") + 1].split(",")]
    if not ids:
        print(__doc__); sys.exit(0)
    for did in ids:
        print(json.dumps(reocr(did, go=go), indent=2)[:700])
