#!/usr/bin/env python3
"""tlfh_embed.py — VPS-native query embedder for the Truth-Layer Fitness Harness's Findability axis.

Runs in the dedicated venv (.venv-tlfh, which has fastembed); prints ONE query's bge-small vector as a
pgvector literal. Embedding ONLY — the harness does the pgvector search on its own (role-restricted) cursor,
so the system Python never imports fastembed and nothing touches facts. Model matches rag_embed_local
exactly (BAAI/bge-small-en-v1.5, 384-dim) so query and stored vectors are comparable.

  .venv-tlfh/bin/python scripts/tlfh_embed.py "some query"   -> [0.01,-0.02,...]
"""
import os
import sys

from fastembed import TextEmbedding

_cache = os.path.expanduser("~/.cache/landtek_fastembed")
os.makedirs(_cache, exist_ok=True)
_m = TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=_cache)
v = list(_m.embed([sys.argv[1]]))[0]
print("[" + ",".join(f"{x:.6f}" for x in v) + "]")
