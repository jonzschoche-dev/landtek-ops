#!/usr/bin/env python3
"""corpus_backfill.py — standing canonicalization daemon (free-tier safe).

Grinds the corpus toward bullet-proof on the Gemini FREE tier: a rate-limited,
idempotent, resumable loop that makes every canonical doc
  READ       — OCR the ones with no extracted_text (gemini-2.5-flash vision)
  SEARCHABLE — embed the ones with text but no vector (gemini-embedding-001 -> Qdrant)

Self-adapts to the real rate limit: on HTTP 429 it backs off and retries, so it
never needs the exact RPM hardcoded. Runs forever — also canonicalizes future
uploads. Progress tracked in corpus_backfill_state so restarts resume cleanly.
"""
from __future__ import annotations
import gc, io, os, sys, time, uuid
import psycopg2, psycopg2.extras
import fitz  # PyMuPDF — local Tesseract OCR (no quota)

DSN  = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
COLL = "landtek_documents"
NS   = uuid.UUID("6f1d2c3a-0000-4000-8000-000000000001")  # stable point-id namespace
OCR_PACE, EMB_PACE, IDLE, BACKOFF_MAX = 3.0, 2.0, 120.0, 600.0  # OCR is local now; pace is just a CPU breather for this 1-core box
OCR_PROMPT = (
    "Transcribe ALL text in this document VERBATIM, preserving line order and structure. "
    "Include headers, footers, stamps, captions, and legible handwriting. Mark any span you "
    "cannot read as [illegible]. Do NOT summarize, correct, translate, or omit anything. "
    "Output only the raw transcription.")


def envk(name):
    v = os.environ.get(name)
    if v:
        return v
    try:
        for line in open("/root/landtek/.env"):
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


import google.generativeai as genai
from qdrant_client import QdrantClient
genai.configure(api_key=envk("GEMINI_API_KEY"))
QC = QdrantClient(url=envk("QDRANT_URL"), api_key=envk("QDRANT_KEY"), timeout=30)
CANON = "master_form='digital' AND coalesce(ingest_status,'') NOT IN ('quarantined_dup','quarantined_ghost')"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ensure_state(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS corpus_backfill_state (
        doc_id int PRIMARY KEY, ocr_attempts int DEFAULT 0, ocr_done bool DEFAULT false,
        embedded bool DEFAULT false, last_error text, updated_at timestamptz DEFAULT now())""")


def is_rate_error(e):
    s = str(e).lower()
    return "429" in s or "resource_exhausted" in s or "quota" in s or "rate" in s


def local_path(row):
    fp = row["file_path"]
    if fp and os.path.exists(fp):
        return fp, False
    if row["drive_file_id"]:
        try:
            import urllib.request
            tmp = f"/tmp/bf_{row['id']}"
            urllib.request.urlretrieve(f"http://localhost:8765/files/c/{row['id']}", tmp)
            if os.path.getsize(tmp) > 0:
                return tmp, True
        except Exception:
            pass
    return None, False


def do_ocr(cur, row):
    path, tmp = local_path(row)
    if not path:
        cur.execute("""INSERT INTO corpus_backfill_state (doc_id, ocr_attempts, last_error)
            VALUES (%s,1,'no local bytes') ON CONFLICT (doc_id) DO UPDATE SET
            ocr_attempts=corpus_backfill_state.ocr_attempts+1, last_error='no local bytes', updated_at=now()""",
            (row["id"],))
        return "skip"
    mime = row["mime_type"] or "application/pdf"
    if not ("pdf" in mime or mime.startswith("image/")):
        cur.execute("""INSERT INTO corpus_backfill_state (doc_id, ocr_attempts, ocr_done, last_error)
            VALUES (%s,1,true,%s) ON CONFLICT (doc_id) DO UPDATE SET ocr_done=true,
            last_error=excluded.last_error, updated_at=now()""", (row["id"], f"unsupported mime {mime}"))
        return "skip"
    # LOCAL OCR via PyMuPDF+Tesseract — no quota. Memory-careful (this box is tiny):
    # one page at a time at modest DPI, gc between pages, cap pages per doc.
    try:
        d = fitz.open(path)
        parts = []
        for i in range(min(d.page_count, 15)):
            page = d[i]
            tp = page.get_textpage_ocr(dpi=120, full=True)
            parts.append(page.get_text("text", textpage=tp))
            del tp, page
            gc.collect()
        d.close()
        text = "\n".join(parts).strip()
    except Exception as e:
        # un-openable (HEIC, corrupt, etc.) — count the attempt so we move on
        # instead of looping forever on one bad file.
        cur.execute("""INSERT INTO corpus_backfill_state (doc_id, ocr_attempts, last_error)
            VALUES (%s,1,%s) ON CONFLICT (doc_id) DO UPDATE SET
            ocr_attempts=corpus_backfill_state.ocr_attempts+1, last_error=excluded.last_error,
            updated_at=now()""", (row["id"], f"open/ocr fail: {type(e).__name__}"[:80]))
        return "skip"
    finally:
        if tmp and os.path.exists(path):
            os.remove(path)
    if len(text) < 20:
        cur.execute("""INSERT INTO corpus_backfill_state (doc_id, ocr_attempts, last_error)
            VALUES (%s,1,'empty ocr') ON CONFLICT (doc_id) DO UPDATE SET
            ocr_attempts=corpus_backfill_state.ocr_attempts+1, last_error='empty ocr', updated_at=now()""",
            (row["id"],))
        return "empty"
    cur.execute("UPDATE documents SET extracted_text=%s WHERE id=%s", (text, row["id"]))
    cur.execute("""INSERT INTO corpus_backfill_state (doc_id, ocr_done) VALUES (%s,true)
        ON CONFLICT (doc_id) DO UPDATE SET ocr_done=true, updated_at=now()""", (row["id"],))
    return f"ocr {len(text)}c"


def do_embed(cur, row):
    text = (row["extracted_text"] or "")[:8000]
    emb = genai.embed_content(model="models/gemini-embedding-001", content=text,
                              task_type="RETRIEVAL_DOCUMENT", output_dimensionality=768)
    vec = emb["embedding"]
    pid = str(uuid.uuid5(NS, f"doc-{row['id']}"))
    QC.upsert(collection_name=COLL, points=[{
        "id": pid, "vector": vec,
        "payload": {"doc_id_postgres": row["id"], "text": text[:500], "source": "backfill"}}])
    cur.execute("""INSERT INTO corpus_backfill_state (doc_id, embedded) VALUES (%s,true)
        ON CONFLICT (doc_id) DO UPDATE SET embedded=true, updated_at=now()""", (row["id"],))
    return "embedded"


def quarantine_unfetchable(cur):
    """Self-healing finish line: a doc whose bytes can't be fetched after 3 tries
    (dead file_path + invalid Drive id) can never be OCR'd — quarantine it so READ
    can reach zero instead of grinding forever."""
    cur.execute(f"""UPDATE documents SET ingest_status='quarantined_nobytes'
        WHERE {CANON} AND id IN (
          SELECT doc_id FROM corpus_backfill_state
           WHERE ocr_attempts>=3 AND NOT ocr_done
             AND (last_error='no local bytes' OR last_error LIKE 'open/ocr fail%'))""")
    if cur.rowcount:
        log(f"quarantined {cur.rowcount} un-OCR-able docs (no bytes / un-openable after 3 tries)")


def next_ocr(cur):
    cur.execute(f"""SELECT d.id, d.file_path, d.drive_file_id, d.mime_type FROM documents d
        LEFT JOIN corpus_backfill_state s ON s.doc_id=d.id
        WHERE {CANON} AND coalesce(length(d.extracted_text),0) < 50
          AND (coalesce(d.file_path,'')<>'' OR coalesce(d.drive_file_id,'')<>'')
          AND coalesce(s.ocr_attempts,0) < 3 AND coalesce(s.ocr_done,false)=false
        ORDER BY d.id LIMIT 1""")
    return cur.fetchone()


def next_embed(cur):
    cur.execute(f"""SELECT d.id, d.extracted_text FROM documents d
        LEFT JOIN corpus_backfill_state s ON s.doc_id=d.id
        WHERE {CANON} AND coalesce(length(d.extracted_text),0) >= 50
          AND coalesce(s.embedded,false)=false
        ORDER BY d.id LIMIT 1""")
    return cur.fetchone()


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_state(cur)
    # seed: mark already-embedded docs so we don't re-embed the existing vectors
    seen, nxt = set(), None
    while True:
        pts, nxt = QC.scroll(collection_name=COLL, limit=512, offset=nxt,
                             with_payload=["doc_id_postgres"], with_vectors=False)
        for p in pts:
            did = (p.payload or {}).get("doc_id_postgres")
            if did is not None:
                seen.add(int(did))
        if nxt is None:
            break
    for did in seen:
        cur.execute("""INSERT INTO corpus_backfill_state (doc_id, embedded) VALUES (%s,true)
            ON CONFLICT (doc_id) DO UPDATE SET embedded=true""", (did,))
    log(f"corpus_backfill started — seeded {len(seen)} already-embedded docs")
    backoff = BACKOFF_MAX / 10
    done_ocr = done_emb = 0
    while True:
        try:
            # embed first — fast, high-count SEARCHABLE win; OCR'd docs re-enter here later
            # OCR FIRST — local Tesseract, no quota, so findability never waits on
            # the (rate-walled) embedding step.
            quarantine_unfetchable(cur)
            row = next_ocr(cur)
            if row:
                r = do_ocr(cur, row)
                if r.startswith("ocr") or r == "empty":
                    done_ocr += 1 if r.startswith("ocr") else 0
                    log(f"OCR doc#{row['id']}: {r}  (ocr done={done_ocr})")
                    time.sleep(OCR_PACE)
                # 'skip' did no work -> loop on immediately
                continue
            row = next_embed(cur)
            if row:
                do_embed(cur, row)
                done_emb += 1
                if done_emb % 25 == 0:
                    log(f"embedded {done_emb} (doc#{row['id']})")
                backoff = BACKOFF_MAX / 10
                time.sleep(EMB_PACE); continue
            log(f"idle — nothing to backfill (ocr={done_ocr}, emb={done_emb})")
            time.sleep(IDLE)
        except Exception as e:
            if is_rate_error(e):
                log(f"rate limited, backing off {int(backoff)}s")
                time.sleep(backoff); backoff = min(backoff * 2, BACKOFF_MAX)
            else:
                log(f"error: {type(e).__name__}: {str(e)[:140]}")
                time.sleep(5)


if __name__ == "__main__":
    main()
