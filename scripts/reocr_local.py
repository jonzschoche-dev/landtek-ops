#!/usr/bin/env python3
"""reocr_local.py — creditless re-OCR via the OWNED local vision model (Mac Ollama).

Token-free twin of reocr_gemini.py: same job (render a page → faithful transcription →
replace garbled extracted_text, with backup + reocr_log), but the transcription comes from
the sovereign local vision model over Tailscale (http://100.117.118.47:11434 by default),
NOT Gemini. No quota, no billing — this is the offline-sovereignty path: the stack recovers
its own plot geometry with nothing but owned compute.

Shares the exact tables reocr_gemini uses (reocr_backup, reocr_log) so the drip's
"already done" skip and the priority queue work identically across backends. Reuses
reocr_gemini's Drive-fetch (docs whose bytes live only in Drive).

  python3 reocr_local.py --doc 287            # dry: show transcription sample
  python3 reocr_local.py --doc 287 --go       # re-OCR + write
  python3 reocr_local.py --docs 96,21 --go

Env: OLLAMA_URL (default http://100.117.118.47:11434), REOCR_LOCAL_MODEL (default qwen2.5vl:7b),
     REOCR_MAXPAGES (default 15).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
import urllib.error

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reocr_gemini as G  # reuse _drive_fetch, _log_reocr, _conn, DSN

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
MODEL = os.environ.get("REOCR_LOCAL_MODEL", "qwen2.5vl:7b")
MAXPAGES = int(os.environ.get("REOCR_MAXPAGES", "15"))
RENDER_SCALE = float(os.environ.get("REOCR_RENDER_SCALE", "2.2"))

PROMPT = (
    "Transcribe ALL text on this page of a Philippine land document faithfully and completely. "
    "Preserve names, dates, title/TCT numbers, entry/PE numbers, and especially every "
    "metes-and-bounds course EXACTLY as written, e.g. \"N. 86 deg 23' E., 269.35 m\" — keep the "
    "direction letters (N/S, E/W), degrees, minutes, and the distance in meters precise. "
    "Keep reading order. Output only the transcription — no commentary, no markdown."
)


class LocalTierDown(Exception):
    """The owned local vision tier (Mac Ollama) is unreachable — degrade, retry later."""


def _ollama_ocr(png_b64: str, timeout: int = 300) -> str:
    body = {"model": MODEL, "prompt": PROMPT, "images": [png_b64],
            "stream": False, "options": {"temperature": 0}}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        if e.code == 404:  # model not pulled
            raise LocalTierDown(f"model {MODEL} not found on {OLLAMA_URL} (ollama pull {MODEL}?): {body}")
        raise
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        raise LocalTierDown(f"{OLLAMA_URL} unreachable: {type(e).__name__}: {str(e)[:120]}")
    return out.get("response", "")


def reocr(doc_id, go=False):
    """Re-OCR one doc with the local vision model. Returns the same shape as
    reocr_gemini.reocr (doc/pages/chars_before/chars_after/sample[/written] or error).
    Raises LocalTierDown if the owned tier is unreachable (drip should stop cleanly)."""
    import fitz
    c = G._conn(); cur = c.cursor()
    cur.execute("SELECT file_path, drive_file_id, length(coalesce(extracted_text,'')) "
                "FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); c.close(); return {"doc": doc_id, "error": "no such doc"}
    path, drive_id, before = row
    tmp = None
    if not path or not os.path.exists(path or ""):
        if not drive_id:
            cur.close(); c.close(); return {"doc": doc_id, "error": "no local file and no drive_file_id"}
        try:
            path = tmp = G._drive_fetch(drive_id)
        except Exception as e:
            cur.close(); c.close(); return {"doc": doc_id, "error": f"drive fetch: {str(e)[:100]}"}
    try:
        d = fitz.open(path)
    except Exception as e:
        if tmp:
            try: os.remove(tmp)
            except Exception: pass
        cur.close(); c.close(); return {"doc": doc_id, "error": f"open: {e}"}
    pages = min(d.page_count, MAXPAGES)
    chunks = []
    try:
        for i in range(pages):
            png = d[i].get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE)).tobytes("png")
            chunks.append(_ollama_ocr(base64.b64encode(png).decode()))
    except LocalTierDown:
        if tmp:
            try: os.remove(tmp)
            except Exception: pass
        cur.close(); c.close()
        raise  # let the drip stop cleanly and retry later
    finally:
        pass
    text = "\n\n".join(chunks).strip()
    res = {"doc": doc_id, "pages": pages, "chars_before": before,
           "chars_after": len(text), "sample": text[:300]}
    if go and len(text) >= 50:
        cur.execute("CREATE TABLE IF NOT EXISTS reocr_backup "
                    "(doc_id int, old_text text, ts timestamptz DEFAULT now())")
        cur.execute("INSERT INTO reocr_backup (doc_id, old_text) "
                    "SELECT id, extracted_text FROM documents WHERE id=%s", (doc_id,))
        cur.execute("UPDATE documents SET extracted_text=%s, text_length=%s, ocr_used=true "
                    "WHERE id=%s", (text[:300000], len(text), doc_id))
        G._log_reocr(cur, doc_id, before, len(text), f"ok:local:{MODEL}")
        res["written"] = True
    if tmp:
        try: os.remove(tmp)
        except Exception: pass
    cur.close(); c.close()
    return res


def main():
    a = sys.argv
    go = "--go" in a
    ids = []
    if "--doc" in a:
        ids = [int(a[a.index("--doc") + 1])]
    elif "--docs" in a:
        ids = [int(x) for x in a[a.index("--docs") + 1].split(",")]
    else:
        print(__doc__); sys.exit(0)
    for did in ids:
        try:
            r = reocr(did, go=go)
        except LocalTierDown as e:
            print(json.dumps({"doc": did, "error": f"local_tier_down: {e}"}, indent=2)); sys.exit(2)
        print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
