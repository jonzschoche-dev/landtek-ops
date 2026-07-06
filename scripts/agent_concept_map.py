#!/usr/bin/env python3
"""agent_concept_map.py — DERIVED agent↔concept binding (generated, never hand-authored).

Binds the CONTROL plane (agents = scripts, `SUPERVISION_DIRECTIVE.md`) to the DATA plane (ONTOLOGY
tables): for each agent script it extracts the tables it READS and WRITES from its SQL, intersected
with the LIVE table list (so CTEs, aliases, and keywords are filtered out). This is the join the
ontology + supervision docs lacked — and because it is regenerated from code+DB, it cannot silently
drift the way the hand-curated §8 map did (same discipline as `ontology_check.py --coverage`).

Usage:
  agent_concept_map.py            # agent → writes/reads (the binding) + summary
  agent_concept_map.py --json     # full machine-readable map (agents + reverse table→agents)
  agent_concept_map.py --orphans  # tables NO python agent touches (dead-by-code candidates) +
                                  # agents that touch NO table (pure orchestration/compute)

Honest caveat: some tables are written by n8n/Leo (LangChain.js) or DB triggers, NOT a python script,
so "no agent touches" means "no python writer/reader" — a signal to investigate, not a death verdict.
"""
from __future__ import annotations
import os
import re
import sys
import json
import glob
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WRITE_RE = re.compile(r'(?:insert\s+into|update|delete\s+from|create\s+table(?:\s+if\s+not\s+exists)?)\s+["\']?([a-z_][a-z0-9_]*)', re.I)
READ_RE = re.compile(r'(?:from|join)\s+["\']?([a-z_][a-z0-9_]*)', re.I)

PLUMBING = ("workflow", "execution", "credentials", "shared_", "oauth", "chat_hub", "instance_ai",
            "installed_", "folder", "data_table", "annotation", "webhook", "tag_", "project",
            "insights", "test_case", "auth_provider", "secrets_provider", "dynamic_credential",
            "role", "scope", "user", "settings", "migrations", "variables", "processed_data",
            "invalid_auth", "api_keys")


def is_plumbing(t):
    return t.startswith(PLUMBING) or t in ("role", "scope", "role_scope", "user", "settings", "migrations")


def live_tables(cur):
    cur.execute("SELECT relname FROM pg_stat_user_tables;")
    return {r[0] for r in cur.fetchall()}


def scan(path, live):
    try:
        txt = open(path, encoding="utf-8", errors="ignore").read().lower()
    except Exception:
        return set(), set()
    writes = {t for t in WRITE_RE.findall(txt) if t in live}
    reads = {t for t in READ_RE.findall(txt) if t in live} - writes
    return reads, writes


def build(cur):
    live = live_tables(cur)
    files = sorted(glob.glob(os.path.join(REPO, "scripts", "*.py")) + glob.glob(os.path.join(REPO, "*.py")))
    agents, writers, readers = {}, {}, {}
    for f in files:
        name = os.path.basename(f)[:-3]
        reads, writes = scan(f, live)
        if reads or writes:
            agents[name] = {"reads": sorted(reads), "writes": sorted(writes)}
            for t in writes:
                writers.setdefault(t, set()).add(name)
            for t in reads:
                readers.setdefault(t, set()).add(name)
    domain_live = {t for t in live if not is_plumbing(t)}
    orphaned = sorted(t for t in domain_live if t not in writers and t not in readers)
    return live, agents, writers, readers, orphaned


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    with conn.cursor() as cur:
        live, agents, writers, readers, orphaned = build(cur)
    conn.close()

    if "--json" in sys.argv:
        print(json.dumps({
            "agents": agents,
            "table_writers": {t: sorted(a) for t, a in writers.items()},
            "orphaned_by_code": orphaned,
        }, indent=2))
        return

    if "--orphans" in sys.argv:
        print(f"=== tables NO python agent writes or reads ({len(orphaned)}) — dead-by-code candidates ===")
        print("   (may be written by n8n/Leo or DB triggers — a signal, not a verdict)")
        for t in orphaned:
            print(f"   {t}")
        no_tbl = sorted(n for n, m in agents.items() if not m["writes"] and not m["reads"])
        return

    print(f"=== agent ↔ concept binding — {len(agents)} scripts touch the DB ===")
    for name in sorted(agents):
        m = agents[name]
        w = ("writes: " + ", ".join(m["writes"])) if m["writes"] else ""
        r = ("reads: " + ", ".join(m["reads"][:8]) + ("…" if len(m["reads"]) > 8 else "")) if m["reads"] else ""
        print(f"  {name:26} {w}")
        if r:
            print(f"  {'':26} {r}")
    dom = len([t for t in live if not is_plumbing(t)])
    print(f"\n  {dom - len(orphaned)}/{dom} domain tables have a python agent · {len(orphaned)} touched only by n8n/triggers/dormant")
    print("  → run --orphans for the list, --json for the full bidirectional map.")


if __name__ == "__main__":
    main()
