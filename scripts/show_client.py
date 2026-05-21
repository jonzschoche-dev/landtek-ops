#!/usr/bin/env python3
"""show_client.py — Display per-client registry state.

Verifies the registry against actual DB state (counts matters / docs / emails
per client; checks keystone entity IDs still resolve).

Usage:
  python3 scripts/show_client.py             # all clients
  python3 scripts/show_client.py --client MWK
"""
import argparse
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")
from case_theories._clients import CLIENTS, get, all_ids

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def show(cur, client_id):
    c = get(client_id)
    print(f"# Client: {c['label']} ({c['client_id']})")
    print(f"  case_file: {c['case_file']}")
    print(f"  matter_prefix: {c['matter_prefix']}")
    print()

    # Counts from DB
    cur.execute("SELECT COUNT(*) AS n FROM matters WHERE matter_code LIKE %s",
                (c["matter_prefix"] + "%",))
    n_matters = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM documents WHERE case_file = %s",
                (c["case_file"],))
    n_docs = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM documents "
                "WHERE matter_code LIKE %s", (c["matter_prefix"] + "%",))
    n_docs_tagged = cur.fetchone()["n"]

    cur.execute("""SELECT COUNT(*) AS n FROM gmail_messages
                   WHERE EXISTS (SELECT 1 FROM unnest(matter_codes) mc
                                  WHERE mc LIKE %s)""",
                (c["matter_prefix"] + "%",))
    n_emails = cur.fetchone()["n"]

    cur.execute("""SELECT COUNT(*) AS n FROM resolutions
                   WHERE EXISTS (SELECT 1 FROM unnest(affected_matter_codes) mc
                                  WHERE mc LIKE %s)""",
                (c["matter_prefix"] + "%",))
    n_res = cur.fetchone()["n"]

    print(f"  ## Live DB coverage")
    print(f"    matters registered:        {n_matters}")
    print(f"    docs (case_file scoped):   {n_docs}")
    print(f"    docs (matter-tagged):      {n_docs_tagged}  ({100*n_docs_tagged/max(1,n_docs):.0f}%)")
    print(f"    emails linked to matters:  {n_emails}")
    print(f"    resolutions tracked:       {n_res}")
    print()

    # Keystone entities — verify each ID still resolves
    print(f"  ## Keystone entities ({len(c['keystone_entities'])})")
    unresolved = []
    for k, eid in c["keystone_entities"].items():
        if eid is None:
            print(f"    {k:<32s}  not yet identified (TBD)")
            continue
        cur.execute("SELECT canonical_name, mentions_count FROM entities WHERE id = %s", (eid,))
        r = cur.fetchone()
        if not r:
            print(f"    {k:<32s}  #{eid} MISSING from entities table!")
            unresolved.append((k, eid))
        else:
            print(f"    {k:<32s}  #{eid}  {r['canonical_name']!r} ({r['mentions_count']} mentions)")

    if unresolved:
        print()
        print(f"  ⚠ {len(unresolved)} keystone IDs no longer resolve. Investigate.")

    # Title chain canon
    if c.get("operative_root"):
        print()
        print(f"  ## Title chain canon")
        print(f"    operative root:  {c['operative_root']}")
        print(f"    ghost titles:    {c['ghost_titles']}")
        print(f"    trunk titles:    {c['trunk_titles']}")

    # Civil case mappings
    if c["civil_case_mappings"]:
        print()
        print(f"  ## Civil-case → matter mappings ({len(c['civil_case_mappings'])})")
        for k, v in c["civil_case_mappings"].items():
            print(f"    {k:<10s} → {v}")

    # Pointers
    if c["case_theory_modules"]:
        print()
        print(f"  ## Case theory modules ({len(c['case_theory_modules'])})")
        for m in c["case_theory_modules"]:
            print(f"    - {m}")

    if c["memory_rules"]:
        print()
        print(f"  ## Memory rules ({len(c['memory_rules'])})")
        for m in c["memory_rules"]:
            print(f"    - {m}")

    # Forcing function
    if c.get("next_forcing_function"):
        ff = c["next_forcing_function"]
        print()
        print(f"  ## Next forcing function")
        print(f"    {ff['type']} on {ff['date']} — {ff.get('venue', '?')}  ({ff.get('matter_code', '?')})")

    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Single client id (e.g., MWK)")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.client:
        show(cur, args.client)
    else:
        for cid in all_ids():
            show(cur, cid)
            print("=" * 70)
            print()

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
