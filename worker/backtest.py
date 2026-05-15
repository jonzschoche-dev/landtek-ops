"""Phase 4 — semantic backtest against Qdrant landtek_documents.

Runs three queries (per spec) and prints top 3 results with score + filename + snippet.
"""
import sys, requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from config import GEMINI_API_KEY, QDRANT_URL, QDRANT_KEY

QDRANT_COLL = "landtek_documents"
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768

QUERIES = [
    ("MWK-001", "ARTA referral DILG estate administration obstruction Balane"),
    ("MWK-001", "accion reinvindicatoria Gloria Balane pretrial May 13"),
    ("Paracale-001", "ARTA filing mining concession submission Allan Inocalla"),
]


def embed(text):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:embedContent?key={GEMINI_API_KEY}",
        json={"model": f"models/{EMBED_MODEL}",
              "content": {"parts": [{"text": text}]},
              "outputDimensionality": EMBED_DIM},
        timeout=30)
    r.raise_for_status()
    return r.json()["embedding"]["values"]


def search(case_file, query, k=3):
    v = embed(query)
    body = {"vector": v, "limit": k, "with_payload": True,
            "filter": {"must": [{"key": "case_file", "match": {"value": case_file}}]}}
    r = requests.post(f"{QDRANT_URL}/collections/{QDRANT_COLL}/points/search",
        headers={"api-key": QDRANT_KEY, "Content-Type": "application/json"},
        json=body, timeout=30)
    r.raise_for_status()
    return r.json().get("result", [])


def main():
    print(f"Backtesting against Qdrant {QDRANT_COLL}\n")
    for case, q in QUERIES:
        print(f"\n{'='*72}\n[{case}] {q}\n{'='*72}")
        try:
            res = search(case, q)
        except Exception as e:
            print(f"  search failed: {e}"); continue
        if not res:
            print("  No matches."); continue
        for i, r in enumerate(res, 1):
            p = r.get("payload", {})
            score = r.get("score", 0)
            text = (p.get("text", "") or "").replace("\n", " ")[:300]
            print(f"  [{i}] score={score:.3f} | doc={p.get('filename','?')} "
                  f"(chunk {p.get('chunk_index','?')}/{p.get('total_chunks','?')}) "
                  f"| type={p.get('document_type','?')} | date={p.get('document_date','?')}")
            print(f"      summary: {p.get('summary','')[:200]}")
            print(f"      snippet: {text}")


if __name__ == "__main__":
    main()
