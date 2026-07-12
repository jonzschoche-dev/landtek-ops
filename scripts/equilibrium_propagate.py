#!/usr/bin/env python3
"""equilibrium_propagate.py — A76 P2: the reactive heart (INTERNAL plane, SHADOW).

An interaction (a reply, a new fact, an attachment) is a GRAPH PERTURBATION. This recomputes the affected
**ego-network** on v_relationship_graph (never the whole corpus) and runs the equilibrium checks, then
records the result to propagation_log. It EMITS NOTHING — surfacing to a recipient is the emission plane
(the A79 clamp at outward_guard). Two planes: internal = maximally accurate + gate-free; external = clamped.

PER-HOP A5 GUARD (the proven doc-bridge fix): traversal follows ONLY edges whose client_code = the seed's
client. Every edge in v_relationship_graph carries its own client_code, so from a client-agnostic document
node you can only follow the seed-client's edges back — the fact->document->fact cross-client bridge
(Paracale-001 -> doc 1176 -> NIBDC-001, proven 2026-07-11) is structurally impossible.

  python3 scripts/equilibrium_propagate.py --seed-fact <id> [--hops 2] [--ref <interaction>]
  # library:  from equilibrium_propagate import propagate
"""
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _seed_client(cur, seed_type, seed_id):
    if seed_type == "fact":
        cur.execute("SELECT _client_of(matter_code) AS c FROM matter_facts WHERE id=%s", (seed_id,))
    elif seed_type == "matter":
        cur.execute("SELECT _client_of(%s) AS c", (seed_id,))
    else:
        return None
    r = cur.fetchone()
    return r["c"] if r else None


def _ego(cur, seed_type, seed_id, client_code, hops):
    """Ego-network via bidirectional traversal — CLIENT-FILTERED edges only (the per-hop A5 guard)."""
    cur.execute("""
        WITH RECURSIVE edges AS (
            SELECT src_type,src_id,tgt_type,tgt_id FROM v_relationship_graph WHERE client_code=%(cc)s
            UNION ALL
            SELECT tgt_type,tgt_id,src_type,src_id FROM v_relationship_graph WHERE client_code=%(cc)s
        ),
        nbr(t,i,d) AS (
            SELECT %(st)s, %(si)s::text, 0
          UNION
            SELECT e.tgt_type,e.tgt_id,n.d+1 FROM edges e JOIN nbr n ON e.src_type=n.t AND e.src_id=n.i
             WHERE n.d < %(h)s
        )
        SELECT t AS node_type, i AS node_id, min(d) AS depth FROM nbr
        WHERE NOT (t=%(st)s AND i=%(si)s::text) GROUP BY t,i
    """, {"cc": client_code, "st": seed_type, "si": str(seed_id), "h": hops})
    return cur.fetchall()


def _cross_client_would_reach(cur, seed_type, seed_id, client_code, hops):
    """Count nodes an UNGUARDED traversal (all edges) would reach that resolve to a DIFFERENT client —
    the leak the per-hop guard refuses. Used for the ledger + the negative-bite."""
    cur.execute("""
        WITH RECURSIVE edges AS (
            SELECT src_type,src_id,tgt_type,tgt_id FROM v_relationship_graph
            UNION ALL SELECT tgt_type,tgt_id,src_type,src_id FROM v_relationship_graph
        ),
        nbr(t,i,d) AS (
            SELECT %(st)s,%(si)s::text,0
          UNION SELECT e.tgt_type,e.tgt_id,n.d+1 FROM edges e JOIN nbr n ON e.src_type=n.t AND e.src_id=n.i
             WHERE n.d < %(h)s
        )
        SELECT count(*) AS n FROM (SELECT DISTINCT t,i FROM nbr WHERE t='fact') f
        JOIN matter_facts mf ON mf.id = f.i::bigint
        WHERE _client_of(mf.matter_code) IS DISTINCT FROM %(cc)s
    """, {"st": seed_type, "si": str(seed_id), "h": hops, "cc": client_code})
    return cur.fetchone()["n"]


def propagate(cur, seed_type, seed_id, interaction_ref=None, hops=2, mode="shadow"):
    client = _seed_client(cur, seed_type, seed_id)
    if client is None:
        # A5 resolve-or-hold: no client => cannot propagate safely. Hold, never guess.
        return {"held": True, "reason": "seed has no resolvable client (A5 hold)"}

    ego = _ego(cur, seed_type, seed_id, client, hops)
    ego_fact_ids = [n["node_id"] for n in ego if n["node_type"] == "fact"]

    # contradiction check (A65/A78) — any contradiction register row touching an ego fact
    contradictions = 0
    if ego_fact_ids:
        cur.execute("""SELECT count(*) AS n FROM contradictions
                       WHERE fact_ids ~ ('(^|[^0-9])(' || array_to_string(%s::text[], '|') || ')([^0-9]|$)')""",
                    (ego_fact_ids,))
        contradictions = cur.fetchone()["n"]

    # cascade/keystone check — a keystone controlling or cascading into any ego matter (this client)
    cur.execute("""SELECT count(*) AS n FROM keystones k
                   WHERE _client_of(k.controlling_matter) = %s""", (client,))
    cascades = cur.fetchone()["n"]

    refused = _cross_client_would_reach(cur, seed_type, seed_id, client, hops)

    detail = {"ego_types": {}, "obligation_extraction": "deferred to emission plane (A68 proposal)"}
    for n in ego:
        detail["ego_types"][n["node_type"]] = detail["ego_types"].get(n["node_type"], 0) + 1

    cur.execute("""INSERT INTO propagation_log
                   (interaction_ref, seed_type, seed_id, client_code, ego_hops, ego_nodes,
                    contradictions_found, cascades_touched, cross_client_refused, mode, detail)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (interaction_ref, seed_type, str(seed_id), client, hops, len(ego),
                 contradictions, cascades, refused, mode, psycopg2.extras.Json(detail)))
    log_id = cur.fetchone()["id"]
    return {"held": False, "log_id": log_id, "client": client, "ego_nodes": len(ego),
            "contradictions": contradictions, "cascades": cascades, "cross_client_refused": refused,
            "emitted": False, "mode": mode}  # SHADOW / internal plane: nothing surfaced


def main():
    a = sys.argv
    if "--seed-fact" not in a:
        sys.exit("usage: equilibrium_propagate.py --seed-fact <id> [--hops N] [--ref <interaction>]")
    seed = a[a.index("--seed-fact") + 1]
    hops = int(a[a.index("--hops") + 1]) if "--hops" in a else 2
    ref = a[a.index("--ref") + 1] if "--ref" in a else None
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(propagate(cur, "fact", seed, interaction_ref=ref, hops=hops))
    cur.close(); c.close()


if __name__ == "__main__":
    main()
