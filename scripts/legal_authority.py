#!/usr/bin/env python3
"""legal_authority.py — the forum agents' law library (per-forum statute/IRR/circular RAG). $0.

Embeds VERBATIM authority text per forum into a pgvector store (legal_chunks) using the in-house Ollama
embedder (nomic-embed-text — sovereign, $0), so each forum agent (ARTA / CSC / Ombudsman / Civil)
retrieves the ACTUAL law instead of paraphrasing it. This is the accuracy layer the agents need to
build cases.

DISCIPLINE: only verbatim text from a CITED source is ingested — never model-generated statute. Each
chunk carries its source + a verify flag; web-sourced text is flagged 'verify-vs-official' until the
operator's official copy replaces it.

  python3 scripts/legal_authority.py --ingest --forum ARTA --citation "RA 11032" --title "ARTA Act" \\
        --source "https://lawphil.net/..." --file /path/text.txt [--verify]
  python3 scripts/legal_authority.py --retrieve --forum ARTA --q "processing deadline simple transaction"
  python3 scripts/legal_authority.py --list
"""
import argparse
import json
import os
import re
import urllib.request

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
EMBED_MODEL = os.environ.get("LEGAL_EMBED_MODEL", "nomic-embed-text")
DIM = 768


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


def _ensure(cur):
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cur.execute(f"""CREATE TABLE IF NOT EXISTS legal_chunks (
        id serial PRIMARY KEY, forum text, citation text, title text, source text, chunk_no int,
        text text, embedding vector({DIM}), verify_flag text, created_at timestamptz DEFAULT now())""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_legal_forum ON legal_chunks(forum)")


def _embed(text):
    body = {"model": EMBED_MODEL, "prompt": text[:8000]}
    req = urllib.request.Request(OLLAMA_URL + "/api/embeddings", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        v = json.loads(r.read()).get("embedding")
    if not v or len(v) != DIM:
        raise RuntimeError(f"embed failed (got {len(v) if v else 0} dims)")
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def _chunks(text, target=900):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # hard-split oversized paragraphs (few-break sources like big HTML statutes) so no chunk exceeds the
    # embedder's context — otherwise a single 40k-char paragraph becomes one chunk and is truncated on embed
    split = []
    for p in paras:
        while len(p) > target * 2:
            cut = p.rfind(" ", target, target * 2)
            cut = cut if cut > target else target * 2
            split.append(p[:cut].strip()); p = p[cut:].strip()
        if p:
            split.append(p)
    paras = split
    out, buf = [], ""
    for p in paras:
        if len(buf) + len(p) > target and buf:
            out.append(buf); buf = p
        else:
            buf = (buf + "\n" + p).strip()
    if buf:
        out.append(buf)
    return out


def ingest(forum, citation, title, source, text, verify):
    c = _conn(); cur = c.cursor(); _ensure(cur)
    chunks = _chunks(text)
    vflag = "verify-vs-official" if verify else "operator-official"
    n = 0
    for i, ch in enumerate(chunks):
        if len(ch) < 40:
            continue
        emb = _embed(ch)
        cur.execute("""INSERT INTO legal_chunks (forum,citation,title,source,chunk_no,text,embedding,verify_flag)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (forum.upper(), citation, title, source, i, ch, emb, vflag))
        n += 1
    print(f"[legal] ingested {n} chunks for {forum.upper()} — {citation} ({vflag})")


def retrieve_chunks(forum, q, k=5):
    """Return [(citation, text, verify_flag, distance)] — for other tools (e.g. case_pdf)."""
    c = _conn(); cur = c.cursor()
    emb = _embed(q)
    cur.execute("""SELECT citation, left(text, 320), verify_flag, (embedding <=> %s) dist
                   FROM legal_chunks WHERE forum=%s ORDER BY embedding <=> %s LIMIT %s""",
                (emb, forum.upper(), emb, k))
    return cur.fetchall()


def retrieve(forum, q, k=5):
    print(f"=== {forum.upper()} law — top {k} for: {q!r} ===")
    for cit, txt, vf, dist in retrieve_chunks(forum, q, k):
        print(f"\n[{cit}] (sim {1-dist:.2f}, {vf})\n  {txt.strip()}…")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true"); ap.add_argument("--retrieve", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--forum"); ap.add_argument("--citation", default=""); ap.add_argument("--title", default="")
    ap.add_argument("--source", default=""); ap.add_argument("--file"); ap.add_argument("--q", default="")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.ingest:
        text = open(a.file, encoding="utf-8", errors="ignore").read() if a.file else ""
        if len(text) < 40:
            print("no/short text to ingest"); return
        ingest(a.forum, a.citation, a.title, a.source, text, a.verify)
    elif a.retrieve:
        retrieve(a.forum, a.q)
    else:
        c = _conn(); cur = c.cursor(); _ensure(cur)
        cur.execute("SELECT forum, count(*), count(DISTINCT citation) FROM legal_chunks GROUP BY 1 ORDER BY 1")
        print("=== legal authority library ===")
        for forum, n, cits in cur.fetchall():
            print(f"  {forum}: {n} chunks across {cits} authority(ies)")
        if cur.rowcount == 0:
            print("  (empty — ingest statutes/IRRs/circulars per forum)")


if __name__ == "__main__":
    main()
