#!/usr/bin/env python3
"""refresh_relationship_graph.py — refresh the materialized structural graph (deploy_888).

The internal reasoning plane (A76 `equilibrium_propagate`) reads `mv_relationship_graph_structural` so
ego queries are millisecond index scans instead of a 15-30s per-edge `_client_of()` walk. This keeps it
current as facts/chats land. Bounded staleness is acceptable for the internal/shadow plane. ~20-30s/run;
run on a timer (landtek-graph-refresh.timer). Degrade-don't-crash: logs + exits, never hangs a caller.
"""
import os
import sys

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    try:
        c = psycopg2.connect(DSN, connect_timeout=10); c.autocommit = True
        cur = c.cursor()
        cur.execute("REFRESH MATERIALIZED VIEW mv_relationship_graph_structural")
        cur.execute("SELECT count(*) FROM mv_relationship_graph_structural")
        print(f"[graph_refresh] mv_relationship_graph_structural refreshed — {cur.fetchone()[0]} edges")
        c.close()
    except Exception as e:
        print(f"[graph_refresh] refresh failed (non-fatal): {str(e)[:120]}")
        sys.exit(0)  # never fail the timer; the stale matview keeps serving


if __name__ == "__main__":
    main()
