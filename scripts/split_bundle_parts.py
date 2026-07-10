#!/usr/bin/env python3
"""split_bundle_parts.py — populate document_parts from bundle PDFs, BOOKMARK-driven (deploy_828).

The composition layer's document_parts table (deploy_808) needs page ranges for the constituent documents
inside a bundle PDF ("Annex A = pp.9-11"). Grounding the real corpus bundles showed the honest split signal:

  • Legal bundles carry a PDF OUTLINE (bookmarks) naming each constituent with its start page — reliable and
    deterministic (doc 676 has 25, doc 782 has 19, doc 879 has 31). We split on THAT, never on guessed text
    boundaries. A bookmark title IS the part's semantic label ("OFFICIAL ANSWER OF MUNICIPAL MAYOR PAJARILLO").
  • Image-only bundles (0% extractable text — doc 828/839/700) and plain-text bundles with no outline have NO
    reliable in-document boundary → we record NOTHING and FLAG them (vision-OCR territory), never fabricate.

A part's page range = [bookmark page, next-bookmark page − 1]; last part runs to the final page. Nested
outlines are flattened and page-sorted. kind = 'exhibit' when the title names an exhibit/annex, else
'bundled_document'. A55: document_parts is thin — a part inherits its parent's connectivity/provenance,
carries none of its own.

IDEMPOTENT: a doc with existing parts is skipped unless --force (then its parts are replaced in a txn).
USAGE: python3 scripts/split_bundle_parts.py [--dry] [--doc-id N ...] [--force] [--limit N]
"""
import argparse, os, re, sys
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
EXHIBIT_RE = re.compile(r"(?i)\b(exhibit|annex)\b")
MIN_TEXT_CHARS = 40


def _ranges_from_toc(toc, page_count):
    """[(level,title,page)] → [(title, page_start, page_end)] leaf ranges, page-sorted, 1-indexed, clamped."""
    pts = [(t.strip(), p) for _lvl, t, p in toc if p and p >= 1 and t and t.strip()]
    if not pts:
        return []
    # sort by page; a later bookmark on the same/earlier page (nesting) is deduped to the first title seen
    pts.sort(key=lambda x: x[1])
    out = []
    for i, (title, pg) in enumerate(pts):
        start = max(1, min(pg, page_count))
        nxt = pts[i + 1][1] if i + 1 < len(pts) else page_count + 1
        end = max(start, min(nxt - 1, page_count))
        if out and out[-1][1] == start:          # same start page as previous → keep the earlier (outer) title
            continue
        out.append((title, start, end))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--doc-id", type=int, action="append", default=None)
    ap.add_argument("--force", action="store_true", help="replace existing parts for a doc")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    try:
        import fitz
    except ImportError:
        print("PyMuPDF (fitz) required — run on the VPS"); sys.exit(1)

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.doc_id:
        cur.execute("""SELECT id, original_filename, file_path FROM documents
                        WHERE id = ANY(%s) ORDER BY id""", (args.doc_id,))
    else:  # bundle candidates: cites an exhibit series, has a file, substantial
        cur.execute("""SELECT id, original_filename, file_path FROM documents
                        WHERE analyst_memo->'ingest_signals'->'flags' ? 'cites_exhibit_series'
                          AND file_path IS NOT NULL AND length(coalesce(extracted_text,'')) > 8000
                        ORDER BY length(extracted_text) DESC LIMIT %s""", (args.limit,))
    docs = cur.fetchall()
    mode = "DRY-RUN" if args.dry else "LIVE"
    print(f"  [split-bundle {mode}] {len(docs)} bundle candidate(s)\n")

    split = parts_made = skip_have = flag_notext = flag_nobm = miss = 0
    for d in docs:
        if not d["file_path"] or not os.path.exists(d["file_path"]):
            miss += 1; continue
        cur.execute("SELECT count(*) AS n FROM document_parts WHERE doc_id=%s", (d["id"],))
        have = cur.fetchone()["n"]
        if have and not args.force:
            skip_have += 1; continue
        try:
            pdf = fitz.open(d["file_path"])
        except Exception as e:
            print(f"    ✗ doc {d['id']} open-fail: {str(e)[:50]}"); miss += 1; continue
        pc = pdf.page_count
        textpages = sum(1 for i in range(pc) if len(pdf[i].get_text().strip()) > MIN_TEXT_CHARS)
        toc = pdf.get_toc()
        ranges = _ranges_from_toc(toc, pc) if toc else []
        if not ranges:
            if textpages / max(pc, 1) < 0.2:
                flag_notext += 1
                print(f"    ⚠ doc {d['id']:<5} {(d['original_filename'] or '')[:40]:<42} IMAGE-ONLY ({pc}p, 0 text) → needs vision OCR to split")
            else:
                flag_nobm += 1
                print(f"    ⚠ doc {d['id']:<5} {(d['original_filename'] or '')[:40]:<42} no bookmarks ({pc}p text) → no reliable boundary, skipped")
            pdf.close(); continue

        print(f"  ◆ doc {d['id']:<5} {(d['original_filename'] or '')[:40]:<42} {pc}p → {len(ranges)} part(s)")
        if not args.dry:
            if have:
                cur.execute("DELETE FROM document_parts WHERE doc_id=%s", (d["id"],))
        for idx, (title, ps, pe) in enumerate(ranges):
            kind = "exhibit" if EXHIBIT_RE.search(title) else "bundled_document"
            print(f"      [{idx}] pp.{ps}-{pe:<4} {kind:<16} {title[:46]}")
            if not args.dry:
                cur.execute("""INSERT INTO document_parts (doc_id, part_index, page_start, page_end, kind, label)
                               VALUES (%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (doc_id, part_index) DO NOTHING""",
                            (d["id"], idx, ps, pe, kind, title[:200]))
                parts_made += cur.rowcount
        split += 1
        pdf.close()

    print(f"\n  Summary [{mode}]:")
    print(f"    bundles split: {split}   parts {'previewed' if args.dry else 'created'}: "
          f"{parts_made if not args.dry else 'n/a (dry)'}")
    print(f"    skipped (already have parts): {skip_have}")
    print(f"    FLAGGED image-only (need vision OCR): {flag_notext}")
    print(f"    FLAGGED plain-text no-bookmarks (no boundary signal): {flag_nobm}")
    print(f"    file missing on disk: {miss}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
