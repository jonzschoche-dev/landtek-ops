#!/usr/bin/env python3
"""ocr_triage.py — resident agent: re-OCR the OCR-garbage docs locally. $0 (Tesseract, no quota).

Some documents are linked to matters but their OCR is garbage (ocr_quality.flagged), so the worker
can't read them. This re-OCRs such docs with LOCAL Tesseract (pdftoppm → tesseract; $0, no Gemini
quota) and scores the result. It NEVER overwrites documents.extracted_text — the re-OCR'd text + its
readability score go to the `re_ocr_results` side table, marked `better` only when it clearly beats
the existing text. Adoption is a separate, deliberate step (so a worse Tesseract pass can't corrupt a
doc). Docs whose source PDF is only in Drive (not local) are reported as the Drive-fetch increment.

  python3 scripts/ocr_triage.py --limit 5         # re-OCR local-file garbage docs -> side table
  python3 scripts/ocr_triage.py --report
"""
import argparse
import os
import re
import subprocess
import tempfile

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
SEARCH_DIRS = ["/root/landtek/uploads", "/root/landtek/inbox"]


def _readability(t):
    """Crude readability: fraction of tokens that look like real words (alpha, len>=3)."""
    toks = re.findall(r"[A-Za-z]{2,}", t or "")
    if not toks:
        return 0.0
    good = sum(1 for w in toks if 3 <= len(w) <= 15)
    return round(good / max(len(toks), 1), 3)


def _find_pdf(file_path, doc_id):
    for p in ([file_path] if file_path else []):
        if p and os.path.exists(p):
            return p
    for d in SEARCH_DIRS:
        for cand in (f"{d}/file_{doc_id}.pdf", f"{d}/{doc_id}.pdf"):
            if os.path.exists(cand):
                return cand
    return None


def _tesseract(pdf):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "200", "-png", "-f", "1", "-l", "3", pdf, f"{tmp}/p"],
                       capture_output=True, timeout=120)
        out = []
        for png in sorted(os.listdir(tmp)):
            if png.endswith(".png"):
                r = subprocess.run(["tesseract", f"{tmp}/{png}", "-", "-l", "eng"],
                                   capture_output=True, text=True, timeout=120)
                out.append(r.stdout)
        return "\n".join(out)


def scan(cur, limit):
    cur.execute("""CREATE TABLE IF NOT EXISTS re_ocr_results (
        doc_id int PRIMARY KEY, old_score numeric, new_score numeric, old_len int, new_len int,
        better bool, new_text text, created_at timestamptz DEFAULT now())""")
    cur.execute("""SELECT d.id, d.file_path, length(coalesce(d.extracted_text,'')) olen,
        coalesce(d.extracted_text,'') otext, d.drive_file_id
        FROM documents d JOIN ocr_quality q ON q.doc_id=d.id
        WHERE q.flagged=true AND d.matter_code IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM re_ocr_results r WHERE r.doc_id=d.id)
        ORDER BY d.id""")
    rows = cur.fetchall()
    done = drive_only = improved = 0
    for did, fp, olen, otext, drive in rows:
        if done >= limit:
            break
        pdf = _find_pdf(fp, did)
        if not pdf:
            drive_only += 1
            continue
        try:
            ntext = _tesseract(pdf)
        except Exception:
            continue
        done += 1
        os_, ns = _readability(otext), _readability(ntext)
        better = ns > os_ + 0.05 and len(ntext) > 200
        cur.execute("""INSERT INTO re_ocr_results (doc_id,old_score,new_score,old_len,new_len,better,new_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (doc_id) DO UPDATE SET
            new_score=EXCLUDED.new_score, new_len=EXCLUDED.new_len, better=EXCLUDED.better,
            new_text=EXCLUDED.new_text""",
            (did, os_, ns, olen, len(ntext), better, ntext[:50000]))
        if better:
            improved += 1
            print(f"  doc:{did} re-OCR better: {os_}→{ns} ({olen}→{len(ntext)} chars)")
    print(f"[ocr-triage] re-OCR'd {done} local-file docs · {improved} improved · {drive_only} Drive-only (queued for fetch)")


def report(cur):
    cur.execute("SELECT count(*) FILTER (WHERE better), count(*) FROM re_ocr_results")
    b, t = cur.fetchone()
    print(f"re_ocr_results: {t} re-OCR'd, {b} better than original (adopt via a deliberate step)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    if not a.report:
        scan(cur, a.limit)
    report(c.cursor())


if __name__ == "__main__":
    main()
