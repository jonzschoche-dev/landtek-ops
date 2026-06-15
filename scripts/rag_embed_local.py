#!/usr/bin/env python3
"""rag_embed_local.py — embed the whole corpus with a LOCAL model (free, unlimited, no quota).

The RAG bottleneck was the embedding engine: Gemini free-tier died at 9/1055 docs, chat
subscriptions can't embed, and we won't burn credits. fastembed (bge-small-en-v1.5, 384-dim,
ONNX — no GPU/torch) runs on the Mac for $0 with no quota wall. Corpus text lives in the VPS DB,
so this embeds on the Mac and ships vectors to the VPS over the proven ssh+docker-exec channel
(content base64-encoded to avoid COPY/quoting issues). Resumable + idempotent.

Stores into a dedicated rag_local table (doc_id, chunk_index, content_b64, embedding vector(384))
with an HNSW cosine index — kept separate from document_chunks (halfvec 3072) so the local-model
vector space is internally consistent.

  python3 scripts/rag_embed_local.py --setup            # create table + index (idempotent)
  python3 scripts/rag_embed_local.py --embed --limit 100
  python3 scripts/rag_embed_local.py --embed            # whole remaining corpus
  python3 scripts/rag_embed_local.py --search "void SPA de la Fuente negotiate" --k 6
  python3 scripts/rag_embed_local.py --status
"""
import base64
import subprocess
import sys

SSH = ["ssh", "-o", "ConnectTimeout=60", "root@100.85.203.58"]
DOCKER_PSQL = "docker exec -i n8n-postgres-1 psql -U n8n -d n8n"
CHUNK, OVERLAP = 1500, 200
_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from fastembed import TextEmbedding
        _MODEL = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _MODEL


def _psql(sql, want_out=True):
    r = subprocess.run(SSH + [f"{DOCKER_PSQL} -t -A -c \"{sql}\""],
                       capture_output=True, text=True, timeout=120)
    return r.stdout.strip()


def _copy(tsv):
    """Pipe TSV rows into rag_local via COPY FROM STDIN over ssh."""
    cmd = SSH + [f"{DOCKER_PSQL} -c \"COPY rag_local(doc_id,chunk_index,content_b64,embedding) FROM STDIN\""]
    r = subprocess.run(cmd, input=tsv, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError("COPY failed: " + r.stderr[:300])


def setup():
    out = _psql("CREATE EXTENSION IF NOT EXISTS vector; "
                "CREATE TABLE IF NOT EXISTS rag_local (id serial PRIMARY KEY, doc_id int, chunk_index int, "
                "content_b64 text, embedding vector(384), created_at timestamptz DEFAULT now()); "
                "CREATE INDEX IF NOT EXISTS rag_local_emb_idx ON rag_local USING hnsw (embedding vector_cosine_ops); "
                "CREATE INDEX IF NOT EXISTS rag_local_doc_idx ON rag_local(doc_id);")
    print("[setup] rag_local table + hnsw index ready", out)


def _chunks(text):
    text = " ".join(text.split())
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + CHUNK]); i += CHUNK - OVERLAP
    return out or [""]


def _vec_literal(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def embed_all(limit=None):
    model = _model()
    done = chunks_total = 0
    while True:
        n = min(40, (limit - done) if limit else 40)
        if n <= 0:
            break
        rows = _psql("SELECT d.id, replace(encode(convert_to(d.extracted_text,'UTF8'),'base64'), chr(10), '') "
                     "FROM documents d WHERE d.extracted_text IS NOT NULL AND length(d.extracted_text) >= 50 "
                     "AND d.id NOT IN (SELECT DISTINCT doc_id FROM rag_local) "
                     f"ORDER BY d.id LIMIT {n}")
        if not rows:
            break
        tsv_lines = []
        batch_docs = 0
        for line in rows.splitlines():
            if "|" not in line:
                continue
            did, b64 = line.split("|", 1)
            try:
                text = base64.b64decode(b64).decode("utf-8", "replace")
            except Exception:
                continue
            chs = _chunks(text)
            vecs = list(model.embed(chs))
            for idx, (ch, v) in enumerate(zip(chs, vecs)):
                cb64 = base64.b64encode(ch.encode()).decode()
                tsv_lines.append(f"{did}\t{idx}\t{cb64}\t{_vec_literal(v)}")
                chunks_total += 1
            batch_docs += 1
        if tsv_lines:
            _copy("\n".join(tsv_lines) + "\n")
        done += batch_docs
        print(f"  embedded {done} docs / {chunks_total} chunks", flush=True)
        if batch_docs == 0:
            break
    print(f"[embed] DONE docs={done} chunks={chunks_total} (local bge-small, $0)")


def status():
    out = _psql("SELECT count(*) chunks, count(DISTINCT doc_id) docs FROM rag_local")
    tot = _psql("SELECT count(*) FROM documents WHERE extracted_text IS NOT NULL AND length(extracted_text)>=50")
    print(f"[rag_local] {out.replace('|', ' chunks / ')} docs embedded · corpus target = {tot} docs")


def search(query, k=6):
    qv = _vec_literal(list(_model().embed([query]))[0])
    sql = (f"SELECT r.doc_id, round((r.embedding <=> '{qv}')::numeric,4) dist, "
           "left(convert_from(decode(r.content_b64,'base64'),'UTF8'),140) snippet, "
           "coalesce(d.original_filename,'') fn "
           f"FROM rag_local r JOIN documents d ON d.id=r.doc_id ORDER BY r.embedding <=> '{qv}' LIMIT {k}")
    print(f"\nRAG search (local): \"{query}\"\n" + "=" * 70)
    print(_psql(sql))


if __name__ == "__main__":
    a = sys.argv
    if "--setup" in a:
        setup()
    elif "--status" in a:
        status()
    elif "--search" in a:
        search(a[a.index("--search") + 1], k=int(a[a.index("--k") + 1]) if "--k" in a else 6)
    elif "--embed" in a:
        embed_all(limit=int(a[a.index("--limit") + 1]) if "--limit" in a else None)
    else:
        print(__doc__)
