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
  agent_concept_map.py --orphans  # tables NO python agent touches (dead-by-code candidates)
  agent_concept_map.py --review   # built-not-consumed (written, never read) + overlap candidates (§3)

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
from collections import defaultdict

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WRITE_RE = re.compile(r'(?:insert\s+into|update|delete\s+from|create\s+table(?:\s+if\s+not\s+exists)?)\s+["\']?([a-z_][a-z0-9_]*)', re.I)
READ_RE = re.compile(r'(?:from|join)\s+["\']?([a-z_][a-z0-9_]*)', re.I)

PLUMBING = ("workflow", "execution", "credentials", "shared_", "oauth", "chat_hub", "instance_ai",
            "installed_", "folder", "data_table", "annotation", "webhook", "tag_", "project",
            "insights", "test_case", "auth_provider", "secrets_provider", "dynamic_credential",
            "role", "scope", "user", "settings", "migrations", "variables", "processed_data",
            "invalid_auth", "api_keys")


PLUMBING_NAMES = {"role", "scope", "role_scope", "user", "settings", "migrations", "auth_identity",
                  "binary_data", "credential_dependency", "event_destinations", "gmail_oauth_tokens",
                  "instance_version_history", "token_exchange_jti", "auth_provider_sync_history"}


def is_plumbing(t):
    return t.startswith(PLUMBING) or t in PLUMBING_NAMES


def live_tables(cur):
    cur.execute("SELECT relname, n_live_tup FROM pg_stat_user_tables;")
    return {r[0]: r[1] for r in cur.fetchall()}


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
    # Walk ALL agent code (scripts/, root, holes/, heightened_ocr/, worker/, leo_tools/, autonomous/,
    # n8n_code_nodes/, …) — not just scripts/+root, or subdir agents show as false orphans.
    skip = {".git", "archive", "node_modules", ".claude", "staging", "snapshots", "drafts", "__pycache__"}
    files = []
    for root, dirs, fs in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        files += [os.path.join(root, fn) for fn in fs if fn.endswith(".py")]
    files.sort()
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
        dormant = [t for t in orphaned if not live.get(t)]
        active = sorted(((t, live[t]) for t in orphaned if live.get(t)), key=lambda x: -x[1])
        print(f"=== {len(orphaned)} domain tables with NO python agent writer/reader — oriented ===")
        print(f"\n  🌱 DORMANT / empty ({len(dormant)}) — EXPECTED: awaiting an activation flow, or superseded")
        print(f"     (already oriented in ONTOLOGY §8.8/8.10/8.12). No writer is correct — nothing to fix.")
        print("     " + ", ".join(dormant))
        print(f"\n  ⚠️  ACTIVE but python-unbound ({len(active)}) — has rows, no python writer. Legit sources:")
        print(f"     DB trigger · n8n/Leo (LangChain.js) · seed/migration · shell · dynamic SQL. Confirm each:")
        for t, n in active:
            print(f"       [{n:>6}]  {t}")
        return

    if "--review" in sys.argv:
        dom = {t for t in live if not is_plumbing(t)}
        # BUILT-NOT-CONSUMED: a python agent WRITES it, none READS it.
        wnr = sorted((t for t in writers if t not in readers and t in dom), key=lambda t: -live.get(t, 0))
        terminal = [t for t in wnr if any(k in t for k in ("log", "audit", "queue", "block", "sent",
                                                            "alert", "heartbeat", "snapshot", "runs", "_bak"))]
        investigate = [t for t in wnr if t not in terminal]
        print(f"=== BUILT-NOT-CONSUMED — {len(wnr)} tables written by an agent, read by none ===")
        print(f"  terminal sinks ({len(terminal)}) — logs/audit/queues/backups, consumed by dashboards/humans/n8n (EXPECTED):")
        print("     " + ", ".join(terminal))
        print(f"  ⚠️  produced-but-unconsumed ({len(investigate)}) — a loop may not be closing:")
        for t in investigate:
            print(f"       [{live.get(t, 0):>6}] {t:30} written by {sorted(writers[t])[:2]}")
        # OVERLAP CANDIDATES — name-stem clusters (confirm distinct vs redundant; see ONTOLOGY §3).
        clusters = defaultdict(list)
        for t in dom:
            toks = t.split("_")
            clusters["_".join(toks[:2]) if len(toks) > 2 else toks[0]].append(t)
        print("\n=== OVERLAP CANDIDATES — name-stem clusters (>1 table) — confirm distinct vs redundant (§3) ===")
        for stem, ts in sorted(clusters.items()):
            if len(ts) > 1:
                print(f"   {stem:18} {sorted(ts)}")
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
