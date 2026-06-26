#!/usr/bin/env python3
"""cross_matter.py — the cross-matter evidence map (doctrine #4: evidence compounds across matters).

A fact verified in one matter is often ammunition in others. This records, for each verified fact, WHICH
other matters/forums it strengthens and the legal theory — each anchored to a VERBATIM quote that must be a
substring of its source document (the same no-guess gate as the correspondence ledger). Discovery anywhere
then surfaces everywhere: query a matter and see the out-of-matter evidence that bears on it.

Runs ON THE VPS (psycopg2 → internal DSN). Pairs with correspondence_ledger.py.
  python3 cross_matter.py --init
  python3 cross_matter.py --seed seed.json
  python3 cross_matter.py --matter MWK-ARTA-1891     # evidence from OTHER matters that strengthens this one
  python3 cross_matter.py --render
"""
import argparse
import json
import re
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
DDL = """CREATE TABLE IF NOT EXISTS cross_matter_links (
  id serial PRIMARY KEY, fact text, source_matter text, supports_matter text, theory text,
  proof_doc_id int, proof_quote text, verified bool, created_at timestamptz default now());"""


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def add_link(cur, e):
    cur.execute("SELECT regexp_replace(coalesce(extracted_text,''),'[[:space:]]+',' ','g') FROM documents WHERE id=%s",
                (e["proof_doc_id"],))
    row = cur.fetchone()
    ok = bool(row) and _norm(e["proof_quote"]) in _norm(row[0])
    cur.execute("""INSERT INTO cross_matter_links
        (fact,source_matter,supports_matter,theory,proof_doc_id,proof_quote,verified)
        VALUES (%(fact)s,%(source_matter)s,%(supports_matter)s,%(theory)s,%(proof_doc_id)s,%(proof_quote)s,%(v)s)
        RETURNING id""", {**e, "v": ok})
    return cur.fetchone()[0], ok


def render(conn, matter=None):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if matter:
        cur.execute("SELECT * FROM cross_matter_links WHERE supports_matter ILIKE %s ORDER BY source_matter", (f"%{matter}%",))
        rows = cur.fetchall()
        print(f"=== evidence from OTHER matters that strengthens {matter} : {len(rows)} link(s) ===\n")
        for r in rows:
            print(f"• {r['fact']}  (established in {r['source_matter']})")
            print(f"    theory: {r['theory']}")
            print(f"    {'✓' if r['verified'] else '✗ UNVERIFIED'} doc {r['proof_doc_id']}: \"{r['proof_quote'][:100]}\"\n")
    else:
        cur.execute("SELECT * FROM cross_matter_links ORDER BY source_matter, supports_matter")
        rows = cur.fetchall()
        print(f"=== cross-matter evidence map : {len(rows)} link(s) ===\n")
        for r in rows:
            mark = "✓" if r["verified"] else "✗"
            print(f"{mark} [{r['source_matter']}] → [{r['supports_matter']}]  {r['fact']}")
            print(f"    {r['theory']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--seed")
    ap.add_argument("--matter")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    if a.init:
        cur.execute(DDL); print("[cross-matter] table ready")
    if a.seed:
        for e in json.load(open(a.seed)):
            lid, ok = add_link(cur, e)
            print(f"[cross-matter] link {lid} added · verified={ok}" + ("  ✗ QUOTE UNVERIFIED!" if not ok else ""))
    if a.matter:
        render(conn, a.matter)
    elif a.render:
        render(conn)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
