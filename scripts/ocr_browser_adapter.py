#!/usr/bin/env python3
"""ocr_browser_adapter.py — OCR transport for Gemini Advanced (browser), the sibling of
comprehend_browser_adapter.py. Operator does the OCR in the Gemini chat (separate subscription
quota, strong at OCR); this handles the DB side: which doc to transcribe, then write the result
back into the corpus + re-score quality + queue for embedding.

Why: the Gemini API free tier is exhausted, but the Gemini Advanced *subscription* chat is a
separate quota. Driving it by hand (or via the Chrome extension) OCRs the garbage/no-text docs at
$0 marginal and flows clean text into documents.extracted_text — the upstream the comprehension +
RAG layers depend on.

  python3 ocr_browser_adapter.py --status
  python3 ocr_browser_adapter.py --next-ocr 5            # next docs to OCR (id + filename + prompt)
  python3 ocr_browser_adapter.py --write-ocr --doc 39    # paste/transcribe text via stdin -> corpus
  echo "<transcription>" | python3 ocr_browser_adapter.py --write-ocr --doc 39
"""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reocr_gemini import PROMPT  # noqa: E402  — single source for the OCR prompt
try:
    from ocr_quality import score_text, THRESHOLD  # noqa: E402  — re-score on write-back
except Exception:
    score_text, THRESHOLD = (lambda t: (0.0, {})), 0.30

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


def _ensure_log(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS ocr_browser_log (
        id serial PRIMARY KEY, doc_id int, transport text DEFAULT 'gemini_browser',
        chars_before int, chars_after int, score_before real, score_after real,
        created_at timestamptz DEFAULT now())""")


def _pending_query():
    # high-value first: flagged-garbage text-bearing docs, worst score first, then no-text docs
    return """SELECT d.id, coalesce(d.original_filename,'(no name)') AS fn,
                     coalesce(q.score, 0) AS score, length(coalesce(d.extracted_text,'')) AS chars
              FROM documents d
              LEFT JOIN ocr_quality q ON q.doc_id = d.id
              WHERE (q.flagged OR length(coalesce(d.extracted_text,'')) < 50)
                AND (d.file_path IS NOT NULL OR d.drive_file_id IS NOT NULL)
                AND lower(coalesce(d.original_filename,'')) !~ '[.](zip|docx|xlsx|doc|eml|csv|pptx|json)$'
              ORDER BY (length(coalesce(d.extracted_text,'')) >= 200) DESC, q.score ASC NULLS LAST"""


def status():
    c = _conn(); cur = c.cursor()
    cur.execute(f"SELECT count(*) FROM ({_pending_query()}) s")
    n = cur.fetchone()[0]
    cur.close(); c.close()
    print(json.dumps({"pending_ocr": n, "interpretation": "drain via Gemini Advanced browser; "
                      "each write-back re-scores quality + feeds comprehension/RAG"}, indent=2))


def next_ocr(n):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(_pending_query() + " LIMIT %s", (n,))
    rows = cur.fetchall(); cur.close(); c.close()
    jobs = [{"doc_id": r["id"], "filename": r["fn"], "current_score": round(float(r["score"]), 2),
             "prompt": PROMPT,
             "instructions": f"Open the local PDF named '{r['fn']}', upload to Gemini Advanced with the "
                             f"PROMPT, then: python3 ocr_browser_adapter.py --write-ocr --doc {r['id']} (paste text via stdin)"}
            for r in rows]
    print(json.dumps(jobs, indent=2))


def write_ocr(doc_id, text):
    text = (text or "").strip()
    if len(text) < 50:
        print(json.dumps({"doc": doc_id, "error": "transcription too short (<50 chars)"})); return
    c = _conn(); cur = c.cursor()
    _ensure_log(cur)
    cur.execute("SELECT length(coalesce(extracted_text,'')), coalesce((SELECT score FROM ocr_quality WHERE doc_id=%s),0) FROM documents WHERE id=%s", (doc_id, doc_id))
    row = cur.fetchone()
    if not row:
        print(json.dumps({"doc": doc_id, "error": "no such doc"})); cur.close(); c.close(); return
    before, score_before = row
    cur.execute("CREATE TABLE IF NOT EXISTS reocr_backup (doc_id int, old_text text, ts timestamptz DEFAULT now())")
    cur.execute("INSERT INTO reocr_backup (doc_id, old_text) SELECT id, extracted_text FROM documents WHERE id=%s", (doc_id,))
    cur.execute("UPDATE documents SET extracted_text=%s, text_length=%s, ocr_used=true WHERE id=%s",
                (text[:300000], len(text), doc_id))
    sc, _ = score_text(text)
    cur.execute("""INSERT INTO ocr_quality (doc_id, score, chars, flagged, scored_at)
                   VALUES (%s,%s,%s,%s, now())
                   ON CONFLICT (doc_id) DO UPDATE SET score=EXCLUDED.score, chars=EXCLUDED.chars,
                   flagged=EXCLUDED.flagged, scored_at=now()""",
                (doc_id, sc, len(text), sc < THRESHOLD))
    cur.execute("""INSERT INTO ocr_browser_log (doc_id, chars_before, chars_after, score_before, score_after)
                   VALUES (%s,%s,%s,%s,%s)""", (doc_id, before, len(text), score_before, sc))
    cur.close(); c.close()
    print(json.dumps({"doc": doc_id, "chars": f"{before}->{len(text)}",
                      "quality": f"{round(float(score_before),2)}->{round(sc,2)}",
                      "now_clean": sc >= THRESHOLD}, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--next-ocr", type=int, default=None)
    ap.add_argument("--write-ocr", action="store_true")
    ap.add_argument("--doc", type=int)
    ap.add_argument("--text", default=None)
    a = ap.parse_args()
    if a.status:
        status()
    elif a.next_ocr is not None:
        next_ocr(a.next_ocr)
    elif a.write_ocr:
        if not a.doc:
            print("ERROR: --write-ocr requires --doc", file=sys.stderr); sys.exit(2)
        text = a.text if a.text is not None else sys.stdin.read()
        write_ocr(a.doc, text)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
