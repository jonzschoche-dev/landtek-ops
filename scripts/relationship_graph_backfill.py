#!/usr/bin/env python3
"""relationship_graph_backfill.py — A76 P1: populate fact_edges (the fact->fact spine) from the live
carriers, deterministically, $0 (no LLM), idempotent, A5-hard-constrained.

Two genuine deterministic fact->fact edge sources (grounded 2026-07-11):
  * shares_source (co-citation): two VERIFIED facts citing the SAME source document — a shared-provenance
    support edge. ~27.7k corpus-wide.
  * contradicts: the fact pairs inside `contradictions.fact_ids` (44 detected; A65 owns the arrow-of-time).

A5 IS A HARD CONSTRAINT, NOT A PARAMETER: an edge whose two facts resolve (via _client_of(matter_code))
to DIFFERENT clients is REFUSED — never written, never weighted. Refusals are counted + reported.
Idempotent via uq_fact_edges_triple + ON CONFLICT DO NOTHING (re-run adds 0). Heterogeneous edges
(person->matter, channel_user->client, …) live in v_relationship_graph, not here (fact_edges is
from_fact/to_fact-only).

  python3 scripts/relationship_graph_backfill.py             # backfill + report
  python3 scripts/relationship_graph_backfill.py --matter MWK-ARTA-1891   # scope to one matter (proof)
"""
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def backfill(cur, matter=None):
    scope = ""
    params = {}
    if matter:
        scope = "AND f1.matter_code = %(m)s AND f2.matter_code = %(m)s"
        params["m"] = matter

    # ── shares_source (co-citation) — A5-scoped in the WHERE (cross-client pairs excluded = refused) ──
    cur.execute(f"""
        INSERT INTO fact_edges (from_fact, to_fact, edge_kind, note)
        SELECT f1.id, f2.id, 'shares_source', 'co-cited doc '||f1.source_id
          FROM matter_facts f1
          JOIN matter_facts f2 ON f1.source_id = f2.source_id AND f1.id < f2.id
         WHERE f1.provenance_level='verified' AND f2.provenance_level='verified'
           AND f1.source_id ~ '^[0-9]+$'
           AND _client_of(f1.matter_code) IS NOT NULL
           AND _client_of(f1.matter_code) IS NOT DISTINCT FROM _client_of(f2.matter_code)
           {scope}
        ON CONFLICT (from_fact, to_fact, edge_kind) DO NOTHING
    """, params)
    shares = cur.rowcount

    # count A5 REFUSALS for shares_source (same doc, DIFFERENT client) — the hard constraint at work
    cur.execute(f"""
        SELECT count(*) AS n FROM matter_facts f1
          JOIN matter_facts f2 ON f1.source_id = f2.source_id AND f1.id < f2.id
         WHERE f1.provenance_level='verified' AND f2.provenance_level='verified'
           AND f1.source_id ~ '^[0-9]+$'
           AND _client_of(f1.matter_code) IS NOT NULL AND _client_of(f2.matter_code) IS NOT NULL
           AND _client_of(f1.matter_code) <> _client_of(f2.matter_code)
           {scope}
    """, params)
    refused = cur.fetchone()["n"]

    # ── contradicts — parse numeric fact ids out of the text fact_ids, keep only pairs of EXISTING,
    #    SAME-CLIENT facts (the FK + existence filter also guard against stray numbers) ──
    mscope = "AND c.matter_code = %(m)s" if matter else ""
    cur.execute(f"""
        WITH ids AS (
          SELECT c.ctid, (regexp_matches(c.fact_ids, '\\d+', 'g'))[1]::bigint AS fid
            FROM contradictions c WHERE c.fact_ids ~ '\\d' {mscope}
        ), pairs AS (
          SELECT a.fid AS fa, b.fid AS fb FROM ids a JOIN ids b ON a.ctid = b.ctid AND a.fid < b.fid
        )
        INSERT INTO fact_edges (from_fact, to_fact, edge_kind, note)
        SELECT p.fa, p.fb, 'contradicts', 'contradiction register'
          FROM pairs p
          JOIN matter_facts m1 ON m1.id = p.fa
          JOIN matter_facts m2 ON m2.id = p.fb
         WHERE _client_of(m1.matter_code) IS NOT DISTINCT FROM _client_of(m2.matter_code)
        ON CONFLICT (from_fact, to_fact, edge_kind) DO NOTHING
    """, params)
    contra = cur.rowcount

    cur.execute("SELECT edge_kind, count(*) AS n FROM fact_edges GROUP BY edge_kind ORDER BY 2 DESC")
    spread = cur.fetchall()
    print(f"[graph_backfill] scope={matter or 'ALL'} :: +{shares} shares_source, +{contra} contradicts, "
          f"{refused} cross-client pair(s) REFUSED (A5)")
    print("[graph_backfill] fact_edges now: " + ", ".join(f"{r['edge_kind']}={r['n']}" for r in spread)
          + f"  (total {sum(r['n'] for r in spread)})")
    return {"shares": shares, "contra": contra, "refused": refused}


def main():
    matter = None
    if "--matter" in sys.argv:
        matter = sys.argv[sys.argv.index("--matter") + 1]
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    backfill(cur, matter)
    cur.close(); c.close()


if __name__ == "__main__":
    main()
