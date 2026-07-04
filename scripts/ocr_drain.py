#!/usr/bin/env python3
"""ocr_drain.py — $0 Tesseract drain of unreadable client docs into the canonical adoption path.

Reuses (does NOT rebuild):
  - ocr_quality.score_text / THRESHOLD           (the readability meter + flag rule)
  - ocr_browser_adapter.write_ocr                (canonical adoption: backup->update->rescore->reflag)
Adds only: local-file Tesseract for PDF *and* image docs (ocr_triage handled PDF only, PDF from a
narrow dir set), a client filter, and a conservative ADOPT gate so a worse/garbage read never lands.

Discipline:
  - Adopt ONLY when new readability clears THRESHOLD by a margin AND clearly beats the old score.
    A Tesseract read that stays garbage (dict-hit low) never clears the flag -> never adopted.
  - Facts still flow through verify_worker's excerpt_grounded gate; this only makes a doc *readable*.
  - $0: local Tesseract/pdftoppm only. No Gemini, no paid API.
  - Bounded (--limit) and fully logged: every skip reason printed, nothing silently capped.

  python3 ocr_drain.py --client Paracale-001 --limit 5 --dry
  python3 ocr_drain.py --client Paracale-001 --limit 40 --go
"""
import argparse, os, re, subprocess, sys, tempfile
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
from ocr_quality import score_text, THRESHOLD
import ocr_browser_adapter

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ADOPT_MARGIN = 0.05  # new score must clear THRESHOLD+margin
IMG_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff")

def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c

def _tess_image(path):
    r = subprocess.run(["tesseract", path, "-", "-l", "eng"], capture_output=True, text=True, timeout=120)
    return r.stdout

def _tess_pdf(path, maxpages=4):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "150", "-png", "-f", "1", "-l", str(maxpages), path, f"{tmp}/p"],
                       capture_output=True, timeout=300)
        out = []
        for png in sorted(os.listdir(tmp)):
            if png.endswith(".png"):
                r = subprocess.run(["tesseract", f"{tmp}/{png}", "-", "-l", "eng"],
                                   capture_output=True, text=True, timeout=120)
                out.append(r.stdout)
        return "\n".join(out)

def _ocr(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _tess_pdf(path)
    if ext in IMG_EXT:
        return _tess_image(path)
    return None  # unsupported here (docx/zip handled elsewhere)

def run(client, limit, go):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT d.id, d.file_path, coalesce((SELECT score FROM ocr_quality q WHERE q.doc_id=d.id),0) old_score,
               left(coalesce(NULLIF(d.smart_filename,''),d.original_filename,''),50) fn
          FROM documents d LEFT JOIN ocr_quality q ON q.doc_id=d.id
         WHERE d.case_file=%s AND coalesce(q.flagged,true) IS TRUE
           AND coalesce(d.file_path,'')<>''
           AND NOT EXISTS (SELECT 1 FROM ocr_browser_log b WHERE b.doc_id=d.id)
         ORDER BY d.id
    """, (client,))
    rows = cur.fetchall()
    stats = {"eligible": len(rows), "no_file": 0, "unsupported": 0, "ocr_empty": 0,
             "not_better": 0, "adopted": 0, "still_flagged_after": 0}
    processed = 0
    for r in rows:
        if processed >= limit:
            break
        fp = r["file_path"]
        if not (fp and os.path.exists(fp)):
            stats["no_file"] += 1; continue
        ext = os.path.splitext(fp)[1].lower()
        if ext != ".pdf" and ext not in IMG_EXT:
            stats["unsupported"] += 1; continue
        processed += 1
        try:
            text = _ocr(fp) or ""
        except Exception as e:
            print(f"  doc:{r['id']} OCR-ERROR {str(e)[:60]}"); continue
        if len(text.strip()) < 50:
            stats["ocr_empty"] += 1
            print(f"  doc:{r['id']} [{r['fn']}] empty OCR ({len(text)} chars) — skip"); continue
        new_score, _ = score_text(text)
        old = float(r["old_score"])
        clears = new_score >= (THRESHOLD + ADOPT_MARGIN)
        better = new_score > old + ADOPT_MARGIN
        verdict = "ADOPT" if (clears and better) else "keep-old"
        print(f"  doc:{r['id']} [{r['fn']}] {old:.2f}->{new_score:.2f} ({len(text)}ch) {verdict}")
        if verdict == "ADOPT" and go:
            ocr_browser_adapter.write_ocr(r["id"], text)
            stats["adopted"] += 1
            if new_score < THRESHOLD:
                stats["still_flagged_after"] += 1
        elif verdict != "ADOPT":
            stats["not_better"] += 1
    print(f"\n[ocr_drain] client={client} processed={processed} {'WROTE' if go else 'DRY'}")
    for k, v in stats.items():
        print(f"    {k}: {v}")
    cur.close(); c.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    run(a.client, a.limit, a.go and not a.dry)
