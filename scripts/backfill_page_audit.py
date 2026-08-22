#!/usr/bin/env python3
"""backfill_page_audit.py — find and repair SILENT PARTIAL extractions (deploy_994).

Root cause (2026-08-22, doc 1163 "Molina Recomendation.pdf", NIBDC-001): corpus_backfill.do_ocr
(deploy_405) OCR'd at most 15 pages, wrote the result as extracted_text and marked ocr_done=true —
no page_count, no partial flag. A 19-page MGB memo lost pages 16-19 (incl. "Action Requested: ...
issuance of Exploration Permit") and corpus searches concluded it "was not in the corpus".

    audit  (default)  open the bytes of every backfill-OCR'd doc, set documents.page_count (additive,
                      only when NULL), and for docs longer than the old cap PROBE page 16 against the
                      stored text to decide complete vs truncated. Also flags char-capped docs
                      (text_length >= 200000 — the ingest_drive_folder text[:200000] cap).
                      Results upsert into corpus_page_audit (idempotent).
    --fix             for status='truncated': back up to documents_text_bak, then APPEND the missing
                      pages (page 16..N, PDF text layer per page else Tesseract OCR). Pages 1-15 are
                      kept VERBATIM so excerpts already quoted from them keep grounding
                      (reocr_reground_guard demotes verified matter_facts whose excerpt stops
                      grounding — replacing the text would have been a provenance regression).
                      Any per-page failure is recorded as partial on the row, never silent.
    --report          before/after counts only.

Scope flags: --ids 1163 1170 ... · --case-file NIBDC-001 · --limit N · --all-pdf (audit also sets
page_count for every canonical PDF with local bytes, no Drive downloads).

Never deletes. Never re-OCRs a doc whose text already covers page 16+ (probe says complete).
"""
import argparse, gc, json, os, re, sys, time, urllib.request
import psycopg2, psycopg2.extras
import fitz  # PyMuPDF

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLD_CAP = 15            # deploy_405 page cap
NATIVE_MIN_CHARS = 40
OCR_DPI = 120
CHAR_CAP = 200000       # ingest_drive_folder.py text[:200000]
CANON = "master_form='digital' AND coalesce(ingest_status,'') NOT IN ('quarantined_dup','quarantined_ghost','quarantined_nobytes')"
PRIORITY = {"NIBDC-001": 0, "MWK-001": 1, "Paracale-001": 2}
PAGE_MARK = re.compile(r"page\s*(\d{1,4})\s*of\s*(\d{1,4})", re.I)
BAK_REASON = "deploy_994 pre-append: backfill 15-page cap truncation (pages 16+ missing)"


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def ensure_tables(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS corpus_page_audit (
        doc_id int PRIMARY KEY,
        page_count int, text_length int,
        marker_max_n int, marker_max_m int,
        probe_method text, probe_hit bool,
        status text,            -- complete | truncated | char_capped | unopenable | no_bytes | fixed | fix_partial
        detail text,
        pages_added int, chars_added int,
        audited_at timestamptz DEFAULT now(), fixed_at timestamptz)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS documents_text_bak (
        id int, extracted_text text, text_length int, backed_up_at timestamptz DEFAULT now(), reason text)""")


def local_path(row):
    fp = row.get("file_path")
    if fp and os.path.exists(fp):
        return fp, False
    if row.get("drive_file_id"):
        try:
            tmp = f"/tmp/pa_{row['id']}"
            urllib.request.urlretrieve(f"http://localhost:8765/files/c/{row['id']}", tmp)
            if os.path.getsize(tmp) > 0:
                return tmp, True
        except Exception:
            pass
    return None, False


def page_text(page):
    """(text, used_ocr) for one page: text layer if real, else Tesseract."""
    t = page.get_text("text") or ""
    if len(t.strip()) >= NATIVE_MIN_CHARS:
        return t, False
    tp = page.get_textpage_ocr(dpi=OCR_DPI, full=True)
    t = page.get_text("text", textpage=tp) or ""
    del tp
    return t, True


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def probe_tokens(text):
    """Distinctive tokens from a page: longest alnum words >= 6 chars, up to 8."""
    words = sorted({w for w in _norm(text).split() if len(w) >= 6 and not w.isdigit()}, key=len, reverse=True)
    return words[:8]


def probe_page(d, idx, existing):
    """Does the stored text already contain page idx (0-based)? Returns (hit, method, detail)."""
    page = d[idx]
    t, used_ocr = page_text(page)
    toks = probe_tokens(t)
    if len(toks) < 3:
        # nearly blank page (e.g. a separator sheet) — try the next page if there is one
        if idx + 1 < d.page_count:
            return probe_page(d, idx + 1, existing)
        return None, "ocr" if used_ocr else "native", f"p{idx+1}: too little text to probe"
    ex = _norm(existing)
    hits = sum(1 for w in toks if w in ex)
    ratio = hits / len(toks)
    return ratio >= 0.6, ("ocr" if used_ocr else "native"), f"p{idx+1}: {hits}/{len(toks)} probe tokens present"


def markers(text):
    mn = mm = None
    for n, m in PAGE_MARK.findall(text or ""):
        n, m = int(n), int(m)
        if n <= m:
            mn = max(mn or 0, n); mm = max(mm or 0, m)
    return mn, mm


def upsert(cur, doc_id, **kv):
    kv["doc_id"] = doc_id
    cols = list(kv)
    cur.execute(f"""INSERT INTO corpus_page_audit ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})
        ON CONFLICT (doc_id) DO UPDATE SET {','.join(f'{c}=EXCLUDED.{c}' for c in cols if c!='doc_id')},
        audited_at=now()""", [kv[c] for c in cols])


def candidates(cur, args):
    where = [CANON]
    params = []
    if args.ids:
        where.append("d.id = ANY(%s)"); params.append(args.ids)
    if args.case_file:
        where.append("d.case_file = %s"); params.append(args.case_file)
    src = ("(s.ocr_done OR coalesce(d.text_length, length(d.extracted_text)) >= %s"
           + (" OR (d.mime_type ILIKE '%%pdf%%' AND coalesce(d.file_path,'')<>'')" if args.all_pdf else "") + ")")
    where.append(src); params.append(CHAR_CAP)
    cur.execute(f"""SELECT d.id, d.case_file, d.file_path, d.drive_file_id, d.mime_type, d.page_count,
                           coalesce(d.text_length, length(d.extracted_text), 0) AS tl,
                           d.extracted_text, d.ocr_used, s.ocr_done, a.status AS prior_status
                      FROM documents d
                      LEFT JOIN corpus_backfill_state s ON s.doc_id = d.id
                      LEFT JOIN corpus_page_audit a ON a.doc_id = d.id
                     WHERE {' AND '.join(where)}
                     ORDER BY d.id""", params)
    rows = cur.fetchall()
    rows.sort(key=lambda r: (PRIORITY.get(r["case_file"], 9), r["id"]))
    return rows[: args.limit] if args.limit else rows


def audit(cur, args):
    rows = candidates(cur, args)
    log(f"audit: {len(rows)} candidate doc(s)")
    counts = {}
    for r in rows:
        if r["prior_status"] in ("fixed",) and not args.ids:
            counts["fixed(prior)"] = counts.get("fixed(prior)", 0) + 1
            continue
        mn, mm = markers(r["extracted_text"])
        if r["tl"] >= CHAR_CAP and not r["ocr_done"]:
            upsert(cur, r["id"], page_count=r["page_count"], text_length=r["tl"], marker_max_n=mn, marker_max_m=mm,
                   status="char_capped", detail=f"text_length {r['tl']} >= {CHAR_CAP} (ingest text cap)")
            counts["char_capped"] = counts.get("char_capped", 0) + 1
            continue
        path, tmp = local_path(r)
        if not path:
            upsert(cur, r["id"], text_length=r["tl"], marker_max_n=mn, marker_max_m=mm, status="no_bytes",
                   detail="no local file_path and Drive fetch failed")
            counts["no_bytes"] = counts.get("no_bytes", 0) + 1
            continue
        try:
            d = fitz.open(path)
            pc = d.page_count
            if pc > OLD_CAP and r["ocr_done"]:
                hit, method, detail = probe_page(d, OLD_CAP, r["extracted_text"] or "")
                status = "complete" if hit else ("truncated" if hit is False else "unknown")
            else:
                hit, method, status = None, None, "complete"
                detail = f"{pc} page(s) <= old cap {OLD_CAP}" if r["ocr_done"] else f"{pc} page(s), not backfill-OCR'd"
            d.close()
        except Exception as e:
            upsert(cur, r["id"], text_length=r["tl"], status="unopenable", detail=f"{type(e).__name__}: {str(e)[:100]}")
            counts["unopenable"] = counts.get("unopenable", 0) + 1
            continue
        finally:
            if tmp and os.path.exists(path):
                os.remove(path)
            gc.collect()
        cur.execute("UPDATE documents SET page_count=%s WHERE id=%s AND page_count IS NULL", (pc, r["id"]))
        upsert(cur, r["id"], page_count=pc, text_length=r["tl"], marker_max_n=mn, marker_max_m=mm,
               probe_method=method, probe_hit=hit, status=status, detail=detail)
        counts[status] = counts.get(status, 0) + 1
        if status != "complete":
            log(f"  doc {r['id']:<5} {r['case_file'] or '-':<13} {pc:>4}p {r['tl']:>7}c  {status:<10} {detail}")
    log(f"audit done: {counts}")


def fix(cur, args):
    where = ["a.status = 'truncated'", CANON]
    params = []
    if args.ids:
        where.append("d.id = ANY(%s)"); params.append(args.ids)
    if args.case_file:
        where.append("d.case_file = %s"); params.append(args.case_file)
    cur.execute(f"""SELECT d.id, d.case_file, d.file_path, d.drive_file_id, d.extracted_text, d.ocr_used,
                           a.page_count, d.analyst_memo
                      FROM corpus_page_audit a JOIN documents d ON d.id = a.doc_id
                     WHERE {' AND '.join(where)} ORDER BY d.id""", params)
    rows = cur.fetchall()
    rows.sort(key=lambda r: (PRIORITY.get(r["case_file"], 9), r["id"]))
    if args.limit:
        rows = rows[: args.limit]
    log(f"fix: {len(rows)} truncated doc(s)")
    fixed = partial = failed = 0
    for r in rows:
        path, tmp = local_path(r)
        if not path:
            upsert(cur, r["id"], status="no_bytes", detail="fix: bytes unavailable"); failed += 1
            continue
        old = r["extracted_text"] or ""
        start = OLD_CAP if len(old.strip()) >= 20 else 0   # nothing to preserve -> extract every page
        try:
            d = fitz.open(path)
            pc = d.page_count
            parts, errors, used_ocr, done = [], [], False, 0
            for i in range(start, pc):
                try:
                    t, o = page_text(d[i])
                    parts.append(t); used_ocr = used_ocr or o; done += 1
                except Exception as e:
                    errors.append(f"p{i+1}:{type(e).__name__}"); parts.append("")
                gc.collect()
            d.close()
        except Exception as e:
            upsert(cur, r["id"], status="unopenable", detail=f"fix: {type(e).__name__}: {str(e)[:100]}"); failed += 1
            continue
        finally:
            if tmp and os.path.exists(path):
                os.remove(path)
        added = "\n".join(parts).strip()
        if len(added) < 20:
            upsert(cur, r["id"], status="unknown", detail=f"fix: pages {start+1}-{pc} yielded no text ({'; '.join(errors)[:120]})")
            failed += 1
            continue
        if args.dry_run:
            log(f"  [dry] doc {r['id']} {r['case_file']}: would append pages {start+1}-{pc} ({pc-start}, +{len(added)} chars (ocr={used_ocr}, errors={errors})")
            continue
        # backup (idempotent: one bak row per doc per reason)
        cur.execute("SELECT 1 FROM documents_text_bak WHERE id=%s AND reason=%s", (r["id"], BAK_REASON))
        if not cur.fetchone():
            cur.execute("INSERT INTO documents_text_bak (id, extracted_text, text_length, reason) VALUES (%s,%s,%s,%s)",
                        (r["id"], old, len(old), BAK_REASON))
        new_text = old.rstrip() + "\n\n" + added
        is_partial = done < (pc - start)
        err = f"partial extraction: {start + done}/{pc} pages ({'; '.join(errors)[:140]})" if is_partial else None
        memo = {"page_audit": {"deploy": 994, "at": time.strftime("%Y-%m-%d"), "appended_pages": f"{start+1}-{pc}",
                               "pages_ok": done, "chars_added": len(added), "ocr_used_for_append": used_ocr,
                               "errors": errors, "backup": "documents_text_bak"}}
        cur.execute("""UPDATE documents SET extracted_text=%s, text_length=%s, page_count=%s,
                       ocr_used=(coalesce(ocr_used,false) OR %s), processed_at=now(),
                       error=CASE WHEN %s IS NOT NULL THEN %s WHEN error LIKE 'partial extraction%%' THEN NULL ELSE error END,
                       analyst_memo=coalesce(analyst_memo,'{}'::jsonb) || %s::jsonb
                       WHERE id=%s""",
                    (new_text, len(new_text), pc, used_ocr, err, err, json.dumps(memo), r["id"]))
        cur.execute("""INSERT INTO corpus_backfill_state (doc_id, last_error) VALUES (%s,%s)
                       ON CONFLICT (doc_id) DO UPDATE SET last_error=EXCLUDED.last_error, updated_at=now()""",
                    (r["id"], err))
        st = "fix_partial" if is_partial else "fixed"
        cur.execute("""UPDATE corpus_page_audit SET status=%s, detail=%s, pages_added=%s, chars_added=%s,
                       text_length=%s, fixed_at=now() WHERE doc_id=%s""",
                    (st, err or f"appended pages {start+1}-{pc} ({'ocr' if used_ocr else 'native'})",
                     done, len(added), len(new_text), r["id"]))
        if is_partial: partial += 1
        else: fixed += 1
        log(f"  doc {r['id']:<5} {r['case_file'] or '-':<13} {st:<11} +{done}p +{len(added)}c ({'ocr' if used_ocr else 'native'}){' '+err if err else ''}")
        time.sleep(0.5)
    log(f"fix done: fixed={fixed} partial={partial} failed={failed}")


def report(cur):
    cur.execute("SELECT status, count(*) FROM corpus_page_audit GROUP BY 1 ORDER BY 2 DESC")
    log("corpus_page_audit: " + ", ".join(f"{r['status']}={r['count']}" for r in cur.fetchall()))
    cur.execute(f"""SELECT count(*) AS n, count(page_count) AS with_pc FROM documents d WHERE {CANON} AND d.mime_type ILIKE '%pdf%'""")
    r = cur.fetchone(); log(f"canonical PDFs: {r['n']}, page_count set: {r['with_pc']}")
    cur.execute("SELECT count(*) FROM documents WHERE error LIKE 'partial extraction%'")
    log(f"documents flagged partial extraction: {cur.fetchone()['count']}")
    cur.execute("""SELECT a.status, d.case_file, count(*) FROM corpus_page_audit a JOIN documents d ON d.id=a.doc_id
                   WHERE a.status <> 'complete' GROUP BY 1,2 ORDER BY 1,3 DESC""")
    for r in cur.fetchall():
        log(f"  {r['status']:<12} {r['case_file'] or '-':<14} {r['count']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--case-file")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--all-pdf", action="store_true")
    args = ap.parse_args()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    if args.report:
        report(cur); return
    if args.fix:
        fix(cur, args)
    else:
        audit(cur, args)
    report(cur)


if __name__ == "__main__":
    main()
