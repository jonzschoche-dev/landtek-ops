#!/usr/bin/env python3
"""Deploy 252 — entity-graph guard for flag_unrelated proposals.

Platform-level fix triggered by the Torralba/Balane correction (deploy_251).
The LLM scored those docs flag_unrelated at 0.95 confidence; the
entity-graph would have surfaced Princess Balane Torralba (#2391) as
incontrovertible evidence that the docs ARE client litigation. This
deploy automates that cross-check for every client.

Algorithm
=========
For each (client, flag_unrelated proposal at status='proposed'):

  1. Gather the CLIENT GRAPH:
       - canonical names of every entity_id in keystone_entities (registry)
       - canonical names of every entity_id linked to the client's transferees
       - canonical names of every entity already attached via doc_entities
         to documents in the client's case_file (>= MIN_DOC_LINKS times,
         to keep noise down)
     → produce a normalized set of surname tokens + full-name strings.

  2. Gather the DOC'S ENTITY FOOTPRINT:
       - all entity_ids in doc_entities for this proposal's doc_id
       - their canonical_names + aliases

  3. CROSS-CHECK:
       - For each doc entity, check whether its surname (last token) or any
         full-name token overlaps with the client graph.
       - Also check whether any doc-entity canonical_name appears as a
         substring of a client-graph canonical_name (or vice versa).

  4. ACTION:
       - If overlap evidence found:
           proposal.status = 'needs_manual_review'
           proposal.review_notes = '[entity-graph guard] overlap: <ev list>'
       - If no overlap: leave at 'proposed' (LLM verdict is plausible;
         still wants human eyes but lower priority).

Idempotent. Runs per --client. Audited via app.actor='entity_graph_guard'.

Usage:
  python3 migrations/apply_deploy_252_entity_graph_guard.py --client MWK
  python3 migrations/apply_deploy_252_entity_graph_guard.py --client MWK --apply
"""
import argparse
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")
from case_theories._clients import get, all_ids

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
MIN_DOC_LINKS = 3  # noise floor for "this entity is in the client graph"
STOPWORD_SURNAMES = {
    "atty", "judge", "hon", "mr", "ms", "mrs", "dr", "engr", "sr", "jr",
    "ii", "iii", "iv", "law", "office", "offices", "court", "jr.",
}


def tokenize_name(name):
    """Split a name into normalized tokens (lowercased, alpha-only)."""
    if not name:
        return []
    parts = re.split(r"[\s,.\-]+", name)
    out = []
    for p in parts:
        p = re.sub(r"[^A-Za-z]", "", p).lower()
        if len(p) >= 3 and p not in STOPWORD_SURNAMES:
            out.append(p)
    return out


def surname_of(name):
    """Take the last meaningful token (proxy for surname). Returns None if can't."""
    toks = tokenize_name(name)
    return toks[-1] if toks else None


def gather_client_graph(cur, client_config):
    """Build (full_names, surnames) sets from the client's known entity graph."""
    full_names = set()
    surnames = set()

    # 1. Keystone entities
    for k, eid in (client_config.get("keystone_entities") or {}).items():
        if eid is None:
            continue
        cur.execute("SELECT canonical_name FROM entities WHERE id = %s", (eid,))
        r = cur.fetchone()
        if r and r["canonical_name"]:
            full_names.add(r["canonical_name"])
            sn = surname_of(r["canonical_name"])
            if sn:
                surnames.add(sn)

    # 2. Transferees
    try:
        cur.execute("""SELECT full_name FROM transferees
                        WHERE case_file = %s""", (client_config["case_file"],))
        for r in cur.fetchall():
            if r["full_name"]:
                full_names.add(r["full_name"])
                sn = surname_of(r["full_name"])
                if sn:
                    surnames.add(sn)
    except psycopg2.errors.UndefinedTable:
        pass

    # 3. Frequently-attached entities (proxy: doc_entities backreference)
    cur.execute("""
        SELECT e.canonical_name, COUNT(*) AS n
          FROM doc_entities de
          JOIN entities e ON e.id = de.entity_id
          JOIN documents d ON d.id = de.doc_id
         WHERE d.case_file = %s
         GROUP BY e.canonical_name
        HAVING COUNT(*) >= %s
    """, (client_config["case_file"], MIN_DOC_LINKS))
    for r in cur.fetchall():
        if r["canonical_name"]:
            full_names.add(r["canonical_name"])
            sn = surname_of(r["canonical_name"])
            if sn:
                surnames.add(sn)

    return full_names, surnames


def find_overlap(doc_entities, client_full_names, client_surnames):
    """Return list of overlap-evidence strings, empty if no overlap."""
    evidence = []
    for de in doc_entities:
        cn = de["canonical_name"] or ""
        if not cn:
            continue
        # Surname-level match
        sn = surname_of(cn)
        if sn and sn in client_surnames:
            evidence.append(f"surname '{sn}' (doc:{cn!r})")
        # Substring match — doc entity contained in a client name or vice versa
        for cfn in client_full_names:
            if not cfn:
                continue
            if (cn.lower() in cfn.lower() and len(cn) >= 6) or \
               (cfn.lower() in cn.lower() and len(cfn) >= 6):
                evidence.append(f"name-overlap {cn!r}↔{cfn!r}")
                break
    # De-duplicate while preserving order
    seen = set()
    out = []
    for e in evidence:
        if e not in seen:
            out.append(e)
            seen.add(e)
    return out


def fetch_doc_entities(cur, doc_id):
    cur.execute("""
        SELECT DISTINCT e.id, e.canonical_name
          FROM doc_entities de
          JOIN entities e ON e.id = de.entity_id
         WHERE de.doc_id = %s
    """, (doc_id,))
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default="MWK")
    ap.add_argument("--apply", action="store_true",
                    help="Without --apply: dry-run report only")
    ap.add_argument("--proposed-action", default="flag_unrelated",
                    help="Which proposal action to guard against (default: flag_unrelated)")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.apply:
        cur.execute("SET LOCAL app.actor = 'entity_graph_guard'")

    print(f"Deploy 252 — entity-graph guard ({args.client}, action={args.proposed_action})")
    print("=" * 60)

    client_config = get(args.client)

    print("  Building client graph…")
    full_names, surnames = gather_client_graph(cur, client_config)
    print(f"    {len(full_names)} full-names · {len(surnames)} surnames")
    print(f"    sample surnames: {sorted(list(surnames))[:15]}...")

    # Pull all current 'proposed' rows matching the action under guard
    cur.execute("""
        SELECT id, doc_id, confidence, reasoning
          FROM doc_classification_proposals
         WHERE client_id = %s
           AND proposed_action = %s
           AND status = 'proposed'
         ORDER BY confidence DESC, id
    """, (args.client, args.proposed_action))
    targets = cur.fetchall()
    print(f"\n  {len(targets)} candidate proposals to audit")

    downgraded = []
    survived = []

    for p in targets:
        des = fetch_doc_entities(cur, p["doc_id"])
        evidence = find_overlap(des, full_names, surnames)
        if evidence:
            downgraded.append((p, evidence[:5]))
        else:
            survived.append(p)

    print(f"\n  → {len(downgraded)} would downgrade to needs_manual_review (entity-graph overlap found)")
    print(f"  → {len(survived)} survive as 'proposed' (no overlap; LLM verdict plausible)")

    # Show top 10 of each
    print("\n  Sample downgrades (top 10):")
    for p, ev in downgraded[:10]:
        print(f"    proposal#{p['id']:>4d} doc#{p['doc_id']:>4d} (conf={float(p['confidence']):.2f})")
        for e in ev:
            print(f"        ↳ {e}")
    if len(downgraded) > 10:
        print(f"    …+{len(downgraded)-10} more")

    print("\n  Sample survivors (top 5):")
    for p in survived[:5]:
        print(f"    proposal#{p['id']:>4d} doc#{p['doc_id']:>4d} (conf={float(p['confidence']):.2f}) — {(p['reasoning'] or '')[:80]}")

    if not args.apply:
        print("\n  (dry-run — pass --apply to commit)")
        return

    # Apply downgrades
    print("\n  Applying downgrades...")
    for p, ev in downgraded:
        note = f"[entity_graph_guard 2026-05-21] overlap evidence: " + "; ".join(ev[:5])
        cur.execute("""
            UPDATE doc_classification_proposals
               SET status = 'needs_manual_review',
                   reviewed_at = now(),
                   reviewed_by = 'entity_graph_guard',
                   review_notes = %s
             WHERE id = %s
        """, (note, p["id"]))

    conn.commit()
    print(f"  ✓ {len(downgraded)} downgraded to status='needs_manual_review'")

    # Final counts
    cur.execute("""
        SELECT status, COUNT(*) FROM doc_classification_proposals
         WHERE client_id = %s GROUP BY 1 ORDER BY 2 DESC
    """, (args.client,))
    print(f"\n  {args.client} proposal status distribution:")
    for r in cur.fetchall():
        print(f"    {r['status']:<25s} {r['count']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
