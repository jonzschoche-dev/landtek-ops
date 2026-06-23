#!/usr/bin/env python3
"""pdf_pages.py — carve specific pages out of a corpus PDF (a focused exhibit), not the whole bundle. $0.

Many corpus documents are bundles — e.g. a single 50-page filing holding CART Resolutions 1-6 plus a
cover letter. This pulls only the page(s) a researcher needs into a small PDF, by page range or by
finding the text. The source is read locally (or fetched once from Drive); only the selected pages are
emitted, so nobody has to open or transfer the whole bundle.

  python3 scripts/pdf_pages.py 700 --toc                  # what's on each page (first line) — find what you need
  python3 scripts/pdf_pages.py 700 --find "CART Resolution No. 3"   # locate the page(s) with that text
  python3 scripts/pdf_pages.py 700 12-14                  # extract pages 12-14 -> a small PDF
  python3 scripts/pdf_pages.py 700 3,5,9 --send           # extract pages 3,5,9 -> Telegram
"""
import os
import re
import subprocess
import sys

import fitz  # PyMuPDF
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
DOCBASE = os.environ.get("LANDTEK_DOC_BASE", "http://localhost:8765")
CHAT = "6513067717"


def _tok():
    try:
        for line in open("/root/landtek/.env"):
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def _meta(did):
    c = psycopg2.connect(DSN); cur = c.cursor()
    cur.execute("SELECT coalesce(original_filename,smart_filename,'document'), file_path, coalesce(drive_file_id,'') FROM documents WHERE id=%s", (did,))
    row = cur.fetchone(); c.close()
    if not row:
        sys.exit(f"[pdf_pages] no document with id {did}")
    return row  # (title, file_path, drive_file_id)


def resolve(did):
    """Return a local path to the source PDF — the local file if present, else fetched once via the serve endpoint."""
    title, fp, drid = _meta(did)
    if fp and os.path.exists(fp):
        return title, fp
    tmp = f"/tmp/src_{did}.pdf"
    # the /files/c endpoint serves disk-or-Drive; fetch the source once (server-side / over Tailscale)
    r = subprocess.run(["curl", "-fsSL", "-o", tmp, f"{DOCBASE}/files/c/{did}"], capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 100:
        return title, tmp
    sys.exit(f"[pdf_pages] source PDF for doc {did} not available locally or via Drive")


def parse_spec(spec, n):
    """'12-14', '3,5,9', '1-3,7' -> sorted unique 1-based page list, clamped to [1,n]."""
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            for p in range(int(a), int(b) + 1):
                out.add(p)
        elif part.isdigit():
            out.add(int(part))
    return sorted(p for p in out if 1 <= p <= n)


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower())


def page_text(src, i, ocr=False):
    """Page text from the PDF's own text layer. OCR (render+Tesseract) is an explicit last resort, not default —
    the corpus already holds confirmed digital text; we should not re-OCR at query time."""
    t = src[i].get_text() or ""
    if t.strip() or not ocr:
        return t
    try:
        png = src[i].get_pixmap(dpi=144).tobytes("png")
        r = subprocess.run(["tesseract", "-", "-", "-l", "eng"], input=png, capture_output=True, timeout=45)
        return r.stdout.decode("utf-8", "ignore")
    except Exception:
        return t


def find_pages(src, query, ocr=False):
    q = _norm(query)
    return [i + 1 for i in range(src.page_count) if q in _norm(page_text(src, i, ocr))]


def _chunks_pages(did, query):
    """Pages from the already-digital, page-indexed corpus (document_chunks). [] if this doc isn't page-indexed yet."""
    c = psycopg2.connect(DSN); cur = c.cursor()
    cur.execute("""SELECT DISTINCT page_number FROM document_chunks
                   WHERE document_id=%s AND page_number IS NOT NULL AND content ILIKE %s
                   ORDER BY page_number""", (did, f"%{query}%"))
    pages = [r[0] for r in cur.fetchall()]
    c.close()
    return pages


def _in_corpus_text(did, query):
    """Is the phrase in the document's confirmed digital text (extracted_text)? Doc-level — no page mapping."""
    c = psycopg2.connect(DSN); cur = c.cursor()
    cur.execute("SELECT coalesce(extracted_text,'') ILIKE %s FROM documents WHERE id=%s", (f"%{query}%", did))
    r = cur.fetchone(); c.close()
    return bool(r and r[0])


def _has_text_layer(src, sample=4):
    return any((src[i].get_text() or "").strip() for i in range(min(src.page_count, sample)))


def extract(src_path, pages, out_path):
    src = fitz.open(src_path)
    out = fitz.open()
    for p in pages:
        out.insert_pdf(src, from_page=p - 1, to_page=p - 1)
    out.save(out_path, garbage=4, deflate=True)
    out.close(); src.close()
    return out_path


def send(path, caption):
    tok = _tok()
    r = subprocess.run(["curl", "-s", "-F", f"chat_id={CHAT}", "-F", f"caption={caption}",
                        "-F", f"document=@{path}", f"https://api.telegram.org/bot{tok}/sendDocument"],
                       capture_output=True, text=True)
    print("[send] sent ✓" if '"ok":true' in r.stdout else f"[send] FAIL {r.stdout[:160]}")


def main():
    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        sys.exit("usage: pdf_pages.py DOC_ID [PAGESPEC | --find TEXT | --toc | --info] [--send]")
    did = int(sys.argv[1])
    args = sys.argv[2:]
    title, path = resolve(did)
    src = fitz.open(path)
    n = src.page_count
    short = re.sub(r"\.(pdf|PDF)$", "", title)[:48]

    if "--info" in args or not args:
        print(f"[pdf_pages] {short}: {n} pages, {os.path.getsize(path)//1024} KB")
        return
    if "--toc" in args:
        ocr = "--ocr" in args
        if not _has_text_layer(src) and not ocr:
            print(f"[pdf_pages] {short} — {n} pages: scanned (no text layer). Per-page text isn't indexed yet — "
                  f"build the page index, or pass --ocr to read each page now (slow).")
            return
        print(f"[pdf_pages] {short} — {n} pages:")
        for i in range(n):
            print(f"  p{i+1:>3}: {' '.join(page_text(src, i, ocr).split())[:84]}")
        return
    if "--find" in args:
        q = args[args.index("--find") + 1]
        # 1) the already-digital page index (document_chunks) — instant, no OCR
        pages = _chunks_pages(did, q)
        via = "page index"
        # 2) the PDF's own text layer (born-digital) — instant, no OCR
        if not pages and _has_text_layer(src):
            pages = find_pages(src, q, ocr=False); via = "PDF text layer"
        # 3) explicit last resort only
        if not pages and "--ocr" in args:
            print(f"[pdf_pages] --ocr: OCR'ing {n} pages to locate '{q}' (slow)…", file=sys.stderr)
            pages = find_pages(src, q, ocr=True); via = "OCR (last resort)"
        src.close()
        if not pages:
            if _in_corpus_text(did, q):
                print(f"[pdf_pages] '{q}' IS in this document's confirmed digital text, but the doc isn't page-indexed "
                      f"(scanned bundle, no page map). Build the page index for instant page lookup, or pass --ocr to locate it now.")
            else:
                print(f"[pdf_pages] '{q}' not in {short}'s digital text ({n} pages).")
            return
        print(f"[pdf_pages] '{q}' on page(s) {', '.join(map(str, pages))} of {n} (via {via})")
        spec = ",".join(map(str, pages))
    else:
        spec = args[0]
        src.close()
        pages = parse_spec(spec, n)
        if not pages:
            sys.exit(f"[pdf_pages] no valid pages in '{spec}' (doc has {n} pages)")

    out_path = f"/tmp/doc{did}_p{spec.replace(',', '_').replace('-', 'to')}.pdf"
    extract(path, pages, out_path)
    kb = os.path.getsize(out_path) // 1024
    print(f"[pdf_pages] extracted {len(pages)} page(s) [{spec}] of {n} → {out_path} ({kb} KB)")
    if "--compress" in args:
        from pdf_compress import compress
        small, ras = compress(out_path)
        akb = os.path.getsize(small) // 1024
        print(f"[pdf_pages] compressed → {small} ({akb} KB, {100-akb*100//max(kb,1)}% smaller, {ras} page(s) re-imaged)")
        out_path = small
    if "--send" in args:
        send(out_path, f"{short} — page{'s' if len(pages) > 1 else ''} {spec}")


if __name__ == "__main__":
    main()
