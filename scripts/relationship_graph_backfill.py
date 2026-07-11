#!/usr/bin/env python3
"""relationship_graph_backfill.py — A76 P1 relationship-graph reporter + ego-network query.

AUDIT CORRECTION: fact_edges is a DRIFT table (ontology_validator V1 blocks writes). So there is NO
backfill — the unified graph is v_relationship_graph, which COMPUTES every edge (fact->fact co-citation +
contradicts, fact->matter, matter->matter, channel_user->client, fact->document, message->document) live
from the canonical carriers, A5-refusing cross-client edges IN THE QUERY. This tool reads that view.

  python3 scripts/relationship_graph_backfill.py                 # edge-type spread + A5 refusals
  python3 scripts/relationship_graph_backfill.py --matter MWK-ARTA-1891
  python3 scripts/relationship_graph_backfill.py --ego <fact_id> # N-hop neighborhood of one fact (proof)
"""
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def report(cur, client=None):
    where = "WHERE client_code = %s" if client else ""
    cur.execute(f"SELECT edge_type, count(*) AS n FROM v_relationship_graph {where} GROUP BY 1 ORDER BY 2 DESC",
                ((client,) if client else ()))
    rows = cur.fetchall()
    total = sum(r["n"] for r in rows)
    print(f"[graph] {'client='+client if client else 'ALL clients'} :: {total} edges  ["
          + ", ".join(f"{r['edge_type']}={r['n']}" for r in rows) + "]")
    # A5 refusals: cross-client co-citation pairs the view EXCLUDES (the hard constraint at work)
    cur.execute("""SELECT count(*) AS n FROM matter_facts f1
                     JOIN matter_facts f2 ON f1.source_id=f2.source_id AND f1.id<f2.id
                    WHERE f1.provenance_level='verified' AND f2.provenance_level='verified'
                      AND f1.source_id ~ '^[0-9]+$'
                      AND _client_of(f1.matter_code) IS NOT NULL AND _client_of(f2.matter_code) IS NOT NULL
                      AND _client_of(f1.matter_code) <> _client_of(f2.matter_code)""")
    print(f"[graph] A5 hard constraint: {cur.fetchone()['n']} cross-client co-citation pair(s) REFUSED (never edges)")


def ego(cur, fact_id, hops=2):
    """N-hop neighborhood of a fact node — proves the graph is a real ego-network, not a flat list."""
    cur.execute("""
        WITH RECURSIVE
        edges AS (   -- bidirectional edge set (single recursive term below)
            SELECT src_type, src_id, tgt_type, tgt_id FROM v_relationship_graph
            UNION ALL
            SELECT tgt_type, tgt_id, src_type, src_id FROM v_relationship_graph
        ),
        nbr(node_type, node_id, depth) AS (
            SELECT 'fact', %s::text, 0
          UNION
            SELECT e.tgt_type, e.tgt_id, n.depth+1
              FROM edges e JOIN nbr n ON e.src_type=n.node_type AND e.src_id=n.node_id
             WHERE n.depth < %s
        )
        SELECT node_type, count(DISTINCT node_id) AS n, min(depth) AS nearest
          FROM nbr WHERE NOT (node_type='fact' AND node_id=%s) GROUP BY 1 ORDER BY 2 DESC
    """, (str(fact_id), hops, str(fact_id)))
    rows = cur.fetchall()
    print(f"[graph] {hops}-hop ego-network of fact {fact_id}:")
    for r in rows:
        print(f"          {r['node_type']:12} x{r['n']:<4} (nearest hop {r['nearest']})")


def main():
    a = sys.argv
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if "--ego" in a:
        ego(cur, a[a.index("--ego") + 1])
    elif "--matter" in a:
        m = a[a.index("--matter") + 1]
        cur.execute("SELECT _client_of(%s) AS c", (m,))
        report(cur, cur.fetchone()["c"])
    else:
        report(cur)
    cur.close(); c.close()


if __name__ == "__main__":
    main()
