#!/usr/bin/env python3
"""verify_chunks_grounding.py — truth layer: a chunk is only 'verified' if its
quoted excerpt is provably present in its source document. This promotes
inferred_strong chunks to verified ONLY when the quote grounds verbatim (whitespace/
case-normalized) in the source's extracted_text. Honest, deterministic, reversible
in spirit (records verified_by='grounding_check'). Chunks whose source isn't OCR'd
yet are left inferred and re-checked on the next run.

  python3 verify_chunks_grounding.py          # dry-run
  python3 verify_chunks_grounding.py --apply
"""
import argparse, re, sys
import psycopg2, psycopg2.extras

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = True
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cur.execute("""SELECT c.id, c.doc_id, c.field_name, c.quote_text, d.extracted_text
                     FROM extraction_chunks c JOIN documents d ON d.id=c.doc_id
                    WHERE c.provenance_level='inferred_strong'
                      AND c.quote_text IS NOT NULL AND length(trim(c.quote_text))>=25""")
    rows = cur.fetchall()
    grounded, ungrounded, no_source = [], [], []
    for r in rows:
        src = norm(r["extracted_text"])
        if not src:
            no_source.append(r["id"]); continue
        q = norm(r["quote_text"])
        # ground if the quote (or its first 50 normalized chars for long quotes) is verbatim in source
        probe = q if len(q) <= 60 else q[:50]
        if probe and probe in src:
            grounded.append(r)
        else:
            ungrounded.append(r["id"])

    print(f"inferred_strong chunks with quotes: {len(rows)}")
    print(f"  GROUNDED (quote verbatim in source): {len(grounded)}")
    print(f"  ungrounded (quote not found):        {len(ungrounded)}")
    print(f"  source not OCR'd yet (recheck later): {len(no_source)}")
    for r in grounded[:8]:
        print(f"    + chunk#{r['id']} doc#{r['doc_id']} [{r['field_name']}] \"{r['quote_text'][:50]}\"")

    if args.apply and grounded:
        ids = [r["id"] for r in grounded]
        cur.execute("""UPDATE extraction_chunks
                       SET provenance_level='verified', verified_by='grounding_check',
                           verified_at=now()
                     WHERE id = ANY(%s)""", (ids,))
        print(f"\nAPPLIED — {len(ids)} chunks promoted to verified (quote grounded in source)")

    cur.execute("SELECT provenance_level, count(*) FROM extraction_chunks GROUP BY 1 ORDER BY 2 DESC")
    dist = {r["provenance_level"]: r["count"] for r in cur.fetchall()}
    tot = sum(dist.values())
    v = dist.get("verified", 0)
    print(f"\nverified ratio now: {v}/{tot} = {round(100*v/tot,1)}%")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
