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
import time
import urllib.request
import urllib.error

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_KEY_FALLBACK = os.environ.get("GEMINI_API_KEY_FALLBACK", "")
# economy ladder: high-quality 2.5-flash first; on quota (429) fall back to higher-quota 2.0-flash,
# then roll over to the FALLBACK key (separate project = separate free-tier quota) on the same ladder.
MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL = os.environ.get("GEMINI_VISION_FALLBACK", "gemini-2.0-flash")
MAXPAGES = int(os.environ.get("REOCR_MAXPAGES", "15"))


class QuotaExhausted(Exception):
    """All gemini key/model combos returned 429 — real free-tier exhaustion (resets later)."""


def _ladder():
    keys = [k for k in (GEMINI_KEY, GEMINI_KEY_FALLBACK) if k]
    return [(k, m) for k in keys for m in (MODEL, FALLBACK_MODEL)]

# rate-limit state (free-tier RPM). _RPM=0 means no throttle (single --doc runs).
_RPM = 0
_LAST = [0.0]
_CALLS = [0]
PROMPT = (
    "Transcribe ALL text on this page of a Philippine land document faithfully and completely. "
    "Preserve names, dates, title/TCT numbers, entry/PE numbers, bearings (e.g. \"N. 86 deg 23' E., "
    "269.35 m\") and technical descriptions EXACTLY as written. Keep reading order. "
    "Output only the transcription — no commentary, no markdown."
)


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _log_reocr(cur, doc_id, before, after, note):
    cur.execute("""CREATE TABLE IF NOT EXISTS reocr_log (doc_id int PRIMARY KEY, ts timestamptz DEFAULT now(),
                   chars_before int, chars_after int, note text)""")
    cur.execute("""INSERT INTO reocr_log (doc_id, ts, chars_before, chars_after, note)
                   VALUES (%s, now(), %s, %s, %s)
                   ON CONFLICT (doc_id) DO UPDATE SET ts=now(), chars_before=EXCLUDED.chars_before,
                   chars_after=EXCLUDED.chars_after, note=EXCLUDED.note""", (doc_id, before, after, note))


_DRIVE = None


def _drive():
    global _DRIVE
    if _DRIVE is None:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            "/root/landtek/google-creds.json", scopes=["https://www.googleapis.com/auth/drive.readonly"])
        _DRIVE = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _DRIVE


def _drive_fetch(fid):
    """Download a Drive file to a temp path (for docs whose bytes aren't local)."""
    import io
    import tempfile
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, _drive().files().get_media(fileId=fid, supportsAllDrives=True))
    done = False
    while not done:
        _, done = dl.next_chunk()
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    f.write(buf.getvalue()); f.close()
    return f.name


def _throttle():
    if _RPM > 0:
        gap = 60.0 / _RPM
        wait = gap - (time.time() - _LAST[0])
        if wait > 0:
            time.sleep(wait)
    _LAST[0] = time.time()


def _call_gemini(png_b64, key, model):
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/png", "data": png_b64}},
                                    {"text": PROMPT}]}],
            "generationConfig": {"temperature": 0}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    return "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])


def _key_label(k):
    """Human label for the key that succeeded (for the earned-provenance stamp)."""
    if k and k == GEMINI_KEY:          return "GEMINI_API_KEY"
    if k and k == GEMINI_KEY_FALLBACK: return "GEMINI_API_KEY_FALLBACK"
    return "GEMINI_KEY"


def _gemini_page(png_b64):
    """Transcribe one page, walking the key×model ladder: (primary,2.5)->(primary,2.0)->
    (fallback,2.5)->(fallback,2.0). 429 advances to the next combo; one timeout retry per combo.
    Returns (text, engine_label) — the engine_label names the model+key that ACTUALLY read the page,
    so the caller can earn provenance (A42). Raises QuotaExhausted only when every combo is 429."""
    _throttle(); _CALLS[0] += 1
    for key, model in _ladder():
        for attempt in (1, 2):  # one timeout retry per combo
            try:
                return _call_gemini(png_b64, key, model), f"{model} / {_key_label(key)}"
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):  # quota OR transient overload -> next combo
                    time.sleep(1); _throttle()
                    break
                raise
            except (TimeoutError, urllib.error.URLError, OSError):
                if attempt == 2:
                    break  # give up this combo after the retry
                time.sleep(2); _throttle()
    # every key/model combo is quota'd or overloaded — transient; leave the doc for retry
    raise QuotaExhausted("all gemini key/model combos returned 429/5xx")


def reocr(doc_id, go=False, stamp=False):
    """Re-OCR one doc. go=write text. stamp=EARN provenance (A42): on an accepted read, record a real
    extraction_runs row (status='completed') and set documents.model_used from it. stamp=False (default)
    is SHADOW: it logs the model_used it WOULD stamp but writes no provenance — verify before enabling."""
    if not GEMINI_KEY:
        return {"error": "no GEMINI_API_KEY"}
    import fitz
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT file_path, drive_file_id, length(coalesce(extracted_text,'')) FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); c.close(); return {"doc": doc_id, "error": "no such doc"}
    path, drive_id, before = row
    tmp = None
    if not path or not os.path.exists(path or ""):
        if not drive_id:
            cur.close(); c.close(); return {"doc": doc_id, "error": "no local file and no drive_file_id"}
        try:
            path = tmp = _drive_fetch(drive_id)
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
    models = []
    for i in range(pages):
        try:
            png = d[i].get_pixmap(matrix=fitz.Matrix(2.2, 2.2)).tobytes("png")
            txt, mdl = _gemini_page(base64.b64encode(png).decode())
            chunks.append(txt); models.append(mdl)
        except QuotaExhausted:
            # leave the doc untouched (no partial write, no failure log) — retry after quota reset
            if tmp:
                try: os.remove(tmp)
                except Exception: pass
            cur.close(); c.close()
            raise
        except urllib.error.HTTPError as e:
            cur.close(); c.close()
            return {"doc": doc_id, "error": f"gemini http_{e.code}: {e.read().decode('utf-8','replace')[:120]}", "page": i}
        except Exception as e:
            chunks.append(f"[page {i+1} failed: {str(e)[:60]}]")
    text = "\n\n".join(chunks).strip()
    # the engine(s) that ACTUALLY read this doc — the truthful basis for the earned-provenance stamp (A42)
    engine = " ; ".join(sorted(set(models))) if models else MODEL
    model_str = f"{engine} (reocr_gemini vision)"
    res = {"doc": doc_id, "pages": pages, "chars_before": before, "chars_after": len(text),
           "sample": text[:300]}
    if go and len(text) >= 50:
        cur.execute("CREATE TABLE IF NOT EXISTS reocr_backup (doc_id int, old_text text, ts timestamptz DEFAULT now())")
        cur.execute("INSERT INTO reocr_backup (doc_id, old_text) SELECT id, extracted_text FROM documents WHERE id=%s", (doc_id,))
        cur.execute("""UPDATE documents SET extracted_text=%s, text_length=%s, ocr_used=true
                       WHERE id=%s""", (text[:300000], len(text), doc_id))
        _log_reocr(cur, doc_id, before, len(text), "ok")
        res["written"] = True
        # PROVENANCE (A42) — earn model_used ONLY from a real extraction_runs record; never fabricated.
        if stamp:
            cur.execute("""INSERT INTO extraction_runs (doc_id, model, status, started_at, completed_at, fields_extracted)
                           VALUES (%s, %s, 'completed', now(), now(), %s)""", (doc_id, model_str, len(text)))
            cur.execute("UPDATE documents SET model_used=%s WHERE id=%s AND coalesce(model_used,'')=''",
                        (model_str, doc_id))
            res["provenance"] = f"earned:{engine}"
        else:
            res["provenance_shadow"] = model_str   # what enabling --stamp WOULD earn
    if tmp:
        try: os.remove(tmp)
        except Exception: pass
    cur.close(); c.close()
    return res


def sweep(limit=None, rpm=10, max_calls=250, force=False, retry_failed=False, stamp=False):
    """Drain the re-OCR queue (ocr_quality.flagged) worst-first, rate-limited + resumable.
    Economy: only flagged docs, page-capped, one Gemini ladder call per page, bounded per run.
    stamp=False (default) = SHADOW: log the model_used each accept WOULD earn, write no provenance."""
    global _RPM
    _RPM = max(0, rpm)
    c = _conn(); cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS reocr_log (doc_id int PRIMARY KEY, ts timestamptz DEFAULT now(),
                   chars_before int, chars_after int, note text)""")
    if retry_failed:
        cur.execute("DELETE FROM reocr_log WHERE note IS NOT NULL AND note <> 'ok'")
    skip = "" if force else "AND q.doc_id NOT IN (SELECT doc_id FROM reocr_log)"
    # only renderable bytes (PDF/image) — fitz can't open zip/docx/xlsx; extract_formats handles those.
    # Order: text-bearing garbage first (real legal docs w/ bad OCR, e.g. T-4497), worst dict_hit first,
    # then the no-text images. This spends quota on the high-value docs before passport pics / screenshots.
    cur.execute(f"""SELECT q.doc_id FROM ocr_quality q JOIN documents d ON d.id=q.doc_id
        WHERE q.flagged AND (d.file_path IS NOT NULL OR d.drive_file_id IS NOT NULL)
          AND lower(coalesce(d.original_filename,'')) !~ '\\.(zip|docx|xlsx|doc|eml|csv|txt|pptx|json)$'
        {skip} ORDER BY (q.chars >= 200) DESC, q.score ASC""")
    ids = [r[0] for r in cur.fetchall()]
    if limit:
        ids = ids[:limit]
    print(f"[sweep] queue={len(ids)} rpm={rpm} max_calls={max_calls} model={MODEL}->{FALLBACK_MODEL} "
          f"provenance={'STAMP (writing)' if stamp else 'SHADOW (log-only)'}", flush=True)
    done = ok = prov = 0
    for did in ids:
        if _CALLS[0] >= max_calls:
            print(f"[sweep] reached max_calls={max_calls} after {done} docs — resume next run", flush=True)
            break
        try:
            r = reocr(did, go=True, stamp=stamp)
        except QuotaExhausted:
            print(f"[sweep] Gemini quota exhausted (all keys/models 429) after {done} docs — "
                  f"stopping; resume after reset (doc {did} left for retry)", flush=True)
            break
        except urllib.error.HTTPError as e:
            print(f"  doc {did}: HTTP {e.code} — stopping; resume next run", flush=True)
            break
        except Exception as e:
            r = {"error": str(e)[:120]}
        if r.get("written"):
            ok += 1
            if r.get("provenance"):
                prov += 1; provnote = f"prov={r['provenance']}"
            else:
                provnote = f"SHADOW would-earn[{r.get('provenance_shadow','?')}]"
            print(f"  doc {did}: {r.get('chars_before')}->{r.get('chars_after')} ok {provnote} calls={_CALLS[0]}", flush=True)
        else:
            _log_reocr(cur, did, 0, -1, (r.get("error") or "no_text")[:200])
            print(f"  doc {did}: SKIP [{r.get('error','no_text')}] calls={_CALLS[0]}", flush=True)
        done += 1
    print(f"[sweep] processed={done} rewritten={ok} provenance_{'earned' if stamp else 'shadow'}={prov if stamp else ok} "
          f"total_gemini_calls={_CALLS[0]}", flush=True)
    cur.close(); c.close()


def _arg(a, name, default=None, cast=str):
    return cast(a[a.index(name) + 1]) if name in a else default


if __name__ == "__main__":
    a = sys.argv
    go = "--go" in a
    if "--sweep" in a:
        sweep(limit=_arg(a, "--limit", None, int), rpm=_arg(a, "--rpm", 10, int),
              max_calls=_arg(a, "--max-calls", 250, int),
              force="--force" in a, retry_failed="--retry-failed" in a, stamp="--stamp" in a)
        sys.exit(0)
    ids = []
    if "--doc" in a:
        ids = [int(a[a.index("--doc") + 1])]
    elif "--docs" in a:
        ids = [int(x) for x in a[a.index("--docs") + 1].split(",")]
    if not ids:
        print(__doc__); sys.exit(0)
    for did in ids:
        print(json.dumps(reocr(did, go=go, stamp="--stamp" in a), indent=2)[:700])
