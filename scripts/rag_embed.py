#!/usr/bin/env python3
"""rag_embed.py — turn RAG ON: chunk the corpus + embed into document_chunks (pgvector).

document_chunks (halfvec(3072), HNSW cosine) is the schema-blessed RAG store but was never
populated (0 rows) — so retrieval was dead. This chunks each readable doc and embeds with
gemini-embedding-001 (3072-dim, matches the column). Embedding has its OWN free quota, separate
from the exhausted generation quota, so it runs now. Resumable (skips already-chunked docs),
bounded (--limit), stops cleanly on quota. Creditless re: Anthropic. After this, every query is
a vector search + a few-k-token answer = fractions of a cent.

  python3 rag_embed.py --embed --limit 200 --go      # chunk + embed a batch
  python3 rag_embed.py --search "void SPA de la Fuente" --k 5
  python3 rag_embed.py --status
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
KEYS = [k for k in (os.environ.get("GEMINI_API_KEY", ""), os.environ.get("GEMINI_API_KEY_FALLBACK", "")) if k]
EMODEL = "gemini-embedding-001"
DIM = 3072
CHUNK, OVERLAP = 4000, 400


class QuotaExhausted(Exception):
    pass


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _chunks(text):
    text = " ".join(text.split())
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + CHUNK])
        i += CHUNK - OVERLAP
    return out


def _embed(text, task="RETRIEVAL_DOCUMENT"):
    body = {"content": {"parts": [{"text": text[:18000]}]}, "taskType": task, "outputDimensionality": DIM}
    for key in KEYS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{EMODEL}:embedContent?key={key}"
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.loads(r.read())
            return out["embedding"]["values"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(1); continue
            raise
    raise QuotaExhausted("all embedding keys 429/5xx")


def _vec(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def embed_corpus(limit=None, go=False):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT id, extracted_text FROM documents
                   WHERE extracted_text IS NOT NULL AND length(extracted_text) > 80
                     AND id NOT IN (SELECT DISTINCT document_id FROM document_chunks)
                   ORDER BY id""")
    docs = cur.fetchall()
    if limit:
        docs = docs[:limit]
    print(f"[rag] {'EMBED' if go else 'DRY'} docs_to_process={len(docs)} model={EMODEL} dim={DIM}", flush=True)
    nd = nc = 0
    for d in docs:
        chunks = _chunks(d["extracted_text"])
        try:
            for idx, ch in enumerate(chunks):
                if go:
                    vec = _embed(ch)
                    cur.execute("""INSERT INTO document_chunks (document_id, chunk_index, content, content_hash, chunk_type, embedding, created_at)
                                   VALUES (%s,%s,%s,%s,'text',%s::halfvec, now())""",
                                (d["id"], idx, ch, hashlib.md5(ch.encode()).hexdigest(), _vec(vec)))
                nc += 1
        except QuotaExhausted:
            print(f"[rag] embedding quota exhausted after {nd} docs — resume next run", flush=True)
            break
        nd += 1
        if nd % 25 == 0:
            print(f"  ...{nd} docs, {nc} chunks", flush=True)
    print(f"[rag] {'EMBEDDED' if go else 'WOULD embed'} docs={nd} chunks={nc}", flush=True)
    cur.close(); c.close()


def search(query, k=5):
    c = _conn(); cur = c.cursor()
    qv = _vec(_embed(query, task="RETRIEVAL_QUERY"))
    cur.execute("""SELECT dc.document_id, left(coalesce(d.original_filename,''),36) fn,
                          round((dc.embedding <=> %s::halfvec)::numeric, 4) dist,
                          left(regexp_replace(dc.content, E'\\s+', ' ', 'g'), 150) snippet
                   FROM document_chunks dc JOIN documents d ON d.id = dc.document_id
                   ORDER BY dc.embedding <=> %s::halfvec LIMIT %s""", (qv, qv, k))
    print(f"\nRAG search: \"{query}\"")
    for did, fn, dist, snip in cur.fetchall():
        print(f"  [{dist}] doc {did} {fn}\n        {snip}")
    cur.close(); c.close()


def status():
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT count(*) chunks, count(DISTINCT document_id) docs, count(embedding) embedded FROM document_chunks")
    ch, dc, emb = cur.fetchone()
    cur.execute("SELECT count(*) FROM documents WHERE extracted_text IS NOT NULL AND length(extracted_text)>80")
    total = cur.fetchone()[0]
    print(f"[rag status] {dc}/{total} docs embedded · {ch} chunks · {emb} vectors")
    cur.close(); c.close()


if __name__ == "__main__":
    a = sys.argv
    try:
        if "--embed" in a:
            embed_corpus(limit=int(a[a.index("--limit") + 1]) if "--limit" in a else None, go="--go" in a)
        elif "--search" in a:
            search(a[a.index("--search") + 1], k=int(a[a.index("--k") + 1]) if "--k" in a else 5)
        elif "--status" in a:
            status()
        else:
            print(__doc__)
    except QuotaExhausted:
        print(json.dumps({"error": "embedding quota exhausted — resume later"}))
