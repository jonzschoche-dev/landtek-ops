#!/usr/bin/env python3
import os, sys, time, uuid, json, requests, psycopg2
from pathlib import Path

# Load .env
env_path = Path("/root/landtek/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

DB_DSN     = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_KEY = os.environ["QDRANT_KEY"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
COLLECTION = "landtek_documents"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

conn = psycopg2.connect(DB_DSN)
cur = conn.cursor()
cur.execute("""
  SELECT id, case_file, document_type, original_filename, extracted_text,
         text_length, chunk_count, drive_file_id
  FROM documents WHERE id = 389
""")
row = cur.fetchone()
if not row:
    sys.exit("doc 389 not found")
doc_id, case_file, doctype, fname, text, tlen, ccount, drive_id = row
log(f"doc 389: {fname}")
log(f"  case={case_file} type={doctype} text_len={tlen} chunk_count={ccount}")

if not text:
    sys.exit("no extracted_text on doc 389")

# Qdrant before
r = requests.get(f"{QDRANT_URL}/collections/{COLLECTION}",
                 headers={"api-key": QDRANT_KEY}, timeout=15)
log(f"Qdrant before: {r.json()['result']['points_count']} points")

def embed_gemini(t, retries=3):
    for attempt in range(retries):
        try:
            rr = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={GEMINI_KEY}",
                json={"model":"models/gemini-embedding-001",
                      "content":{"parts":[{"text":t[:8000]}]},
                      "outputDimensionality":768},
                timeout=30)
            if rr.status_code == 429:
                wait = 2 ** attempt * 5
                log(f"    429, sleeping {wait}s")
                time.sleep(wait)
                continue
            rr.raise_for_status()
            return rr.json()["embedding"]["values"]
        except requests.HTTPError as e:
            if attempt == retries - 1: raise
            time.sleep(5)
    raise RuntimeError("all embed retries failed")

chunks = [text[i:i+6000] for i in range(0, len(text), 6000)] or [text]
log(f"chunking into {len(chunks)} pieces")

points = []
for i, c in enumerate(chunks):
    try:
        vec = embed_gemini(c)
        points.append({
            "id": str(uuid.uuid4()),
            "vector": vec,
            "payload": {
                "doc_id": doc_id,
                "chunk_index": i,
                "case_file": case_file,
                "document_type": doctype,
                "filename": fname,
                "text": c[:1500],
            }
        })
        log(f"  chunk {i}: ok ({len(vec)}d)")
        time.sleep(1.5)
    except Exception as e:
        log(f"  chunk {i}: FAILED {e}")

if points:
    rr = requests.put(
        f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true",
        headers={"api-key": QDRANT_KEY, "Content-Type":"application/json"},
        json={"points": points}, timeout=30)
    log(f"upsert: {rr.status_code} {rr.text[:200]}")
    cur.execute("UPDATE documents SET chunk_count = %s WHERE id = 389",
                (len(points),))
    conn.commit()

r = requests.get(f"{QDRANT_URL}/collections/{COLLECTION}",
                 headers={"api-key": QDRANT_KEY}, timeout=15)
log(f"Qdrant after:  {r.json()['result']['points_count']} points")
