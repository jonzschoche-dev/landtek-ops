#!/usr/bin/env python3
"""consolidate_entities.py — Surface fragmented entities + generate
consolidation proposals.

The `entities` table currently has many same-person fragments:
  - 18 "Cesar X / Y de la Fuente" variants → all the keystone Cesar #1348
  - 3 "Bonifacio Barandon" variants → one canonical attorney
  - 3 "Balane" entities that ARE distinct people (Gloria, Efren, Princess)
  - Likely others

This script does NOT consolidate directly. It writes proposals to
proposed_changes per the deploy_221B discipline. Each proposal:
  - operation = 'UPDATE': add aliases to the canonical (keystone) entity
  - operation = 'DELETE': remove a variant (after merging its aliases)

User reviews via: python3 scripts/promote_proposals.py review --table entities

Modes:
  list                   — show fragmentation groups (no writes)
  propose <surname>      — generate proposals for one group
  propose --auto         — auto-detect + propose for known groups (Cesar, Barandon)

Critical: no automatic execution. All consolidation is human-reviewed.
"""
import argparse
import json
import re
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


# Known consolidation targets — canonical entity_id + the surname pattern
# that identifies its variants. Designed conservatively: only the very-high-
# confidence merges. Other surnames go through `list` then case-by-case review.
KEYSTONE_GROUPS = [
    {
        "label": "Cesar de la Fuente",
        "keystone_entity_id": 1348,  # 'Cesar de La Fuente' verified KEYSTONE
        # Postgres POSIX regex uses \y for word boundary, not \b; simpler is .*
        "name_pattern": r"cesar.*fuente",
        "ignore_patterns": [],
        "rationale": (
            "Same person fragmented across 18+ canonical_name forms (Cesar M., Cesar N., "
            "Cesar Dela Fuente, Cesar De La Fuente, Mr. Cesar M., etc). Keystone is #1348 "
            "(verified, role records death 2017-06-21 per doc#364). Consolidate all "
            "variants' aliases into #1348 and mark variants for deletion."
        ),
    },
    {
        "label": "Atty. Bonifacio Barandon",
        "keystone_entity_id": None,
        "name_pattern": r"barandon",
        "ignore_patterns": [r"barandon\s+law"],
        "rationale": (
            "Atty. Bonifacio T. Barandon Jr. is plaintiff's counsel in CV 26-360. "
            "Three entity records exist for the same person. 'Barandon Law Offices' is "
            "the firm — keep distinct. Consolidate the three person-variants."
        ),
    },
    {
        "label": "Mayor Alexander L. Pajarillo",
        "keystone_entity_id": 1635,  # 'Alexander Pajarillo' (47 mentions, verified)
        "name_pattern": r"pajarillo",
        # Exclude: Ma. Luisa R. Pajarillo (different person — different first name)
        "ignore_patterns": [r"luisa", r"ma\."],
        "rationale": (
            "Mayor Alexander L. Pajarillo of Mercedes — adversary in multiple ARTA "
            "matters. Currently 11 variants in entities (Alexander, Alexander L., "
            "Hon. Alexander L., Mayor Alexander, etc.). All same person. "
            "Ma. Luisa R. Pajarillo is a different person — kept distinct via "
            "ignore_pattern."
        ),
    },
    {
        "label": "Patricia Keesey Zschoche",
        "keystone_entity_id": 400,
        "name_pattern": r"patricia",
        "ignore_patterns": [r"road", r"street", r"affidavit"],
        "rationale": (
            "Patricia Keesey Zschoche — plaintiff in CV 26-360. 45+ OCR variants. "
            "Keystone #400 (92 mentions). Excludes street-name + document-title refs."
        ),
    },
    {
        "label": "Geraldine Keesey Hoppe",
        "keystone_entity_id": 16,  # 'Geraldine K. Hoppe' (147 mentions)
        "name_pattern": r"geraldine",
        "ignore_patterns": [],
        "rationale": (
            "Geraldine K. Hoppe is Patricia's sister (per project_title_origins_mwk). "
            "OCR fragmentation: Geraldine Keesey Hoppe, Geraldine Keesee Hoppe, "
            "GERALDINE K. HOPPE, 'Geraldine Alice Teresita Keesey Hoppe' (full name), etc."
        ),
    },
    # ─── Mercedes officials ─────────────────────────────────────────────────
    {
        "label": "Loida E. Macale (Mercedes)",
        "keystone_entity_id": 39,  # 'Loida E. Macale' (155 mentions)
        "name_pattern": r"loida",
        # NOT the same as 'Loida T. Maca' which might be a different person — but
        # given OCR noise we include it. The keystone has Maca/Macale variants.
        "ignore_patterns": [],
        "rationale": (
            "Loida E. Macale — Mercedes side actor in ARTA-1210 correspondence. "
            "Massive OCR fragmentation (155-mention keystone has 10 variants)."
        ),
    },
    {
        "label": "Engr. Erwin H. Balane (Mercedes MEO)",
        "keystone_entity_id": 3060,  # 'Engr. Erwin Balane' (16 mentions)
        "name_pattern": r"erwin.*balane|balane.*erwin",
        "ignore_patterns": [],
        "rationale": (
            "Engr. Erwin H. Balane — Municipal Engineer, Mercedes MEO. Respondent "
            "in MWK-ARTA-0690/0792 and witness in CV-26360. Multiple variants: "
            "'Engr. Erwin Balane', 'Erwin H. Balane', 'Erwin Balane', "
            "'Erwin Hansol Balane', 'Engr. Erwin H. Balane'."
        ),
    },
    {
        "label": "Gloria Balane",
        "keystone_entity_id": 15,  # 'Gloria Balane' (125 mentions, verified)
        "name_pattern": r"^gloria.*balane$",
        "ignore_patterns": [],
        "rationale": (
            "Gloria Balane — defendant in CV-26360. Variants: 'Gloria Balane' "
            "(125 mentions), 'Gloria H. Balane' (22 mentions). Same person; "
            "middle initial preserved as alias."
        ),
    },
    {
        "label": "Efren Balane",
        "keystone_entity_id": 3057,  # 'Efren Balane' (27 mentions)
        "name_pattern": r"^efren.*balane$",
        "ignore_patterns": [],
        "rationale": (
            "Efren Balane — Gloria's husband / co-defendant. Variants: "
            "'Efren Balane' (27), 'Efren M. Balane' (15). Same person."
        ),
    },
    # ─── 20 named transferees ───────────────────────────────────────────────
    {
        "label": "Arnel Mabeza (transferee)",
        "keystone_entity_id": 1333,
        "name_pattern": r"arnel.*mabeza|armel.*mabeza",
        "ignore_patterns": [r"donata", r"joel"],  # other Mabezas — different people
        "rationale": "Arnel Mabeza — named transferee under T-32917. 3 OCR variants.",
    },
    {
        "label": "Cesar S. Ramirez (transferee)",
        "keystone_entity_id": 621,
        "name_pattern": r"cesar.*ramirez",
        "ignore_patterns": [],
        "rationale": "Cesar S. Ramirez — named transferee. 2 variants.",
    },
    {
        "label": "Delfin Gaulit (transferee)",
        "keystone_entity_id": 1295,
        "name_pattern": r"delfin.*gaulit|delein.*gaulit",  # 'Delein' is OCR misread
        "ignore_patterns": [r"eloisa"],  # Eloisa C. Gaulit is a different person
        "rationale": "Delfin Gaulit — named transferee. 'Delein' variants are OCR misreads.",
    },
    {
        "label": "Dolores Vela (transferee)",
        "keystone_entity_id": 1274,
        "name_pattern": r"dolores.*vela",
        "ignore_patterns": [],  # Velante is different surname
        "rationale": "Dolores Vela — named transferee. 'Dolores K. Vela' = same person.",
    },
    {
        "label": "Edgardo Santiago (transferee)",
        "keystone_entity_id": 1229,
        "name_pattern": r"edgar.*santiago",
        "ignore_patterns": [r"justice", r"ivle", r"reli"],  # others are different people
        "rationale": "Edgardo Santiago — named transferee. 'Edgard' variant = same person.",
    },
    {
        "label": "Elsa Iligan / Illigan (transferee)",
        "keystone_entity_id": 1763,
        "name_pattern": r"elsa.*ili[gn]an",  # match both Iligan and Illigan
        "ignore_patterns": [],
        "rationale": "Elsa O. Iligan — named transferee. Spelling varies between L/LL.",
    },
    {
        "label": "Erlinda Tychingco (transferee)",
        "keystone_entity_id": 1241,
        "name_pattern": r"erl.nda.*tychingco",  # match Erlinda / Erllnda OCR
        "ignore_patterns": [],
        "rationale": "Erlinda Tychingco — named transferee. 'Erllnda' OCR misread.",
    },
    {
        "label": "Jose Pascual Jr. (transferee)",
        "keystone_entity_id": 72,
        # Match Jose, José, "Just Pascual", "R. Jose Pascual", and Jr. forms; exclude Sr/Maribel/Bolen
        "name_pattern": r"(jose|just|josé|r\.?\s*jose).*pascual",
        "ignore_patterns": [r"sr\.", r"sr$", r"maribel", r"bolen"],
        "rationale": (
            "Jose Pascual Jr. — named transferee. Multiple OCR forms including "
            "'Just Pascual', 'R. Jose Pascual'. Excludes Sr. (different person) "
            "and other Pascuals."
        ),
    },
    {
        "label": "Librada B. Onrubio (transferee)",
        "keystone_entity_id": 1552,
        "name_pattern": r"librada.*onrubio",
        "ignore_patterns": [],
        "rationale": "Librada B. Onrubio — named transferee. Minor spacing variant.",
    },
    {
        "label": "Maria V. Cereza (transferee)",
        "keystone_entity_id": 1553,
        "name_pattern": r"mar[il]a.*cereza",  # match Maria / Marla OCR misread
        "ignore_patterns": [],
        "rationale": "Maria V. Cereza — named transferee. Multiple OCR variants.",
    },
    {
        "label": "Mariquita Era (transferee)",
        "keystone_entity_id": 1262,
        "name_pattern": r"mariquita.*era",
        "ignore_patterns": [],
        "rationale": "Mariquita Era — named transferee.",
    },
    {
        "label": "Pedro Valledor (transferee)",
        "keystone_entity_id": 1268,
        "name_pattern": r"pedro.*valledor",
        "ignore_patterns": [],
        "rationale": "Pedro Valledor — named transferee. Excludes other Valledors.",
    },
    {
        "label": "Mary Worrick Keesey (root)",
        "keystone_entity_id": 25,  # 'Mary Worrick Keesey' (386 mentions — the actual MWK)
        "name_pattern": r"(mary.*worrick|w.r.ick.*keesey|mary.*keesey)",
        # Exclude 'Heirs of Mary Worrick' (it's a collective reference, not the
        # individual person) and any document-title-like entries that got
        # entity-extracted.
        "ignore_patterns": [
            r"heirs",          # 'Heirs of Mary Worrick' — collective
            r"estate",         # estate-as-entity references
            r"^worrick$",      # just the surname alone
            r"helen",          # Helen Worrick (sister) — different person
            r"alice",          # Alice Worrick (sister) — different person
            r"manuel",         # Manuel Garrido (Helen's widower)
        ],
        "rationale": (
            "Mary Worrick Keesey — root MWK estate entity (deceased 1988-03-17). "
            "Keystone #25 (386 mentions, the canonical form). Variants include "
            "'Mary Worick Keesey' (OCR), 'Mary Worrick Keesee' (Keesee/Keesey), "
            "'KEESEY, MARY WORRICK' (formal allcaps), 'Mary Worrick' (no surname). "
            "Excludes 'Heirs of Mary Worrick' (collective) + the sisters."
        ),
    },
]


def list_fragmentation(cur):
    """Print fragmented entity groups by surname pattern."""
    print("=== Fragmentation report ===\n")
    for group in KEYSTONE_GROUPS:
        print(f"## {group['label']}")
        cur.execute("""
            SELECT id, canonical_name, aliases, provenance_level, mentions_count, role
              FROM entities
             WHERE canonical_name ~* %s
             ORDER BY mentions_count DESC NULLS LAST
        """, (group["name_pattern"],))
        rows = cur.fetchall()
        # Filter ignore patterns
        for ig in group["ignore_patterns"]:
            rows = [r for r in rows if not re.search(ig, r["canonical_name"], re.IGNORECASE)]
        print(f"  {len(rows)} entity rows match:")
        for r in rows:
            keystone_mark = " ← KEYSTONE" if r["id"] == group["keystone_entity_id"] else ""
            aliases = r["aliases"] or []
            print(f"    #{r['id']}  {r['canonical_name']!r}  "
                  f"({r['provenance_level']}, mentions={r['mentions_count']}){keystone_mark}")
            if aliases:
                print(f"        aliases: {aliases[:6]}{'…' if len(aliases) > 6 else ''}")
        print()


def determine_keystone(cur, group):
    """Return entity_id of the keystone for a group.

    If group['keystone_entity_id'] is set, use it. Else pick the verified
    entity with highest mentions_count.
    """
    if group["keystone_entity_id"]:
        return group["keystone_entity_id"]

    cur.execute("""
        SELECT id, canonical_name, mentions_count
          FROM entities
         WHERE canonical_name ~* %s AND provenance_level = 'verified'
         ORDER BY mentions_count DESC NULLS LAST LIMIT 1
    """, (group["name_pattern"],))
    r = cur.fetchone()
    if not r:
        return None
    print(f"  Auto-selected keystone for {group['label']}: #{r['id']} "
          f"({r['canonical_name']}, mentions={r['mentions_count']})")
    return r["id"]


def propose_consolidation(cur, group, dry_run=False):
    """Generate proposed_changes rows for one group's consolidation."""
    keystone_id = determine_keystone(cur, group)
    if not keystone_id:
        print(f"  ✗ No keystone for {group['label']}")
        return 0, 0

    # Fetch all matching variants
    cur.execute("""
        SELECT id, canonical_name, aliases, mentions_count, role, family_group, notes
          FROM entities
         WHERE canonical_name ~* %s AND id != %s
         ORDER BY mentions_count DESC NULLS LAST
    """, (group["name_pattern"], keystone_id))
    variants = cur.fetchall()

    # Filter ignore patterns
    for ig in group["ignore_patterns"]:
        variants = [v for v in variants if not re.search(ig, v["canonical_name"], re.IGNORECASE)]

    # Fetch keystone's current aliases for merging
    cur.execute("SELECT aliases, canonical_name FROM entities WHERE id = %s", (keystone_id,))
    ks = cur.fetchone()
    current_aliases = set(ks["aliases"] or [])

    new_aliases = set(current_aliases)
    new_aliases.add(ks["canonical_name"])  # ensure canonical itself is alias-listed too

    for v in variants:
        new_aliases.add(v["canonical_name"])
        for a in (v["aliases"] or []):
            new_aliases.add(a)

    # Remove duplicates / empty
    new_aliases = sorted(a for a in new_aliases if a and len(a) >= 2 and a != ks["canonical_name"])

    print(f"\n  Group: {group['label']}")
    print(f"    Keystone: #{keystone_id} ({ks['canonical_name']})")
    print(f"    Variants to merge: {len(variants)}")
    print(f"    Aliases after merge: {len(new_aliases)} "
          f"(was {len(current_aliases)}, +{len(new_aliases) - len(current_aliases)})")

    if dry_run:
        print("    [dry-run — no proposals written]")
        return 0, 0

    # Build proposal A: UPDATE keystone with expanded aliases
    state_update = {
        "aliases": new_aliases,
        "notes": (ks.get("notes") or "") + (
            f" | deploy_230: alias set expanded to merge {len(variants)} variant entities; "
            f"see proposed_changes for the corresponding DELETE proposals."
        ),
    }
    cur.execute("""
        INSERT INTO proposed_changes
            (target_table, target_row_id, operation, proposed_state,
             proposed_by, rationale, review_status)
        VALUES ('entities', %s, 'UPDATE', %s::jsonb,
                'deploy_230_consolidate', %s, 'pending')
        RETURNING id
    """, (keystone_id, json.dumps(state_update), group["rationale"]))
    update_pid = cur.fetchone()["id"]
    proposals_made = 1
    print(f"    ✓ proposal #{update_pid}: UPDATE entity #{keystone_id} aliases")

    # Build proposals B: DELETE each variant
    delete_count = 0
    for v in variants:
        state_delete = {
            "_marker": "variant of keystone",
            "keystone_entity_id": keystone_id,
            "keystone_canonical_name": ks["canonical_name"],
            "removed_canonical": v["canonical_name"],
        }
        cur.execute("""
            INSERT INTO proposed_changes
                (target_table, target_row_id, operation, proposed_state,
                 proposed_by, rationale, review_status)
            VALUES ('entities', %s, 'DELETE', %s::jsonb,
                    'deploy_230_consolidate',
                    %s, 'pending')
            RETURNING id
        """, (v["id"],
              json.dumps(state_delete),
              f"Variant of keystone #{keystone_id}: '{v['canonical_name']}' subsumed by "
              f"alias expansion. Mentions={v['mentions_count']}, "
              f"provenance={v.get('canonical_name')}. Delete after UPDATE proposal lands."))
        proposals_made += 1
        delete_count += 1

    print(f"    ✓ {delete_count} DELETE proposals for variants")
    return 1, delete_count


def cmd_list(args, cur):
    list_fragmentation(cur)


def cmd_propose(args, cur):
    if args.auto:
        targets = KEYSTONE_GROUPS
    elif args.surname:
        targets = [g for g in KEYSTONE_GROUPS
                   if args.surname.lower() in g["label"].lower()]
        if not targets:
            print(f"No known group matches surname '{args.surname}'.")
            print(f"Known groups: {[g['label'] for g in KEYSTONE_GROUPS]}")
            sys.exit(2)
    else:
        print("Specify --auto or --surname <name>")
        sys.exit(2)

    total_updates = 0
    total_deletes = 0
    for g in targets:
        u, d = propose_consolidation(cur, g, dry_run=args.dry_run)
        total_updates += u
        total_deletes += d

    print()
    print(f"=== Summary: {total_updates} UPDATE proposals + {total_deletes} DELETE proposals ===")
    if not args.dry_run:
        print()
        print("Review + promote via:")
        print("    python3 scripts/promote_proposals.py review --table entities")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_list = sub.add_parser("list", help="Show fragmentation groups (no writes)")
    sp_list.set_defaults(func=cmd_list)

    sp_pr = sub.add_parser("propose", help="Generate consolidation proposals")
    sp_pr.add_argument("--surname", help="Group label keyword (e.g., 'cesar')")
    sp_pr.add_argument("--auto", action="store_true", help="Process all known groups")
    sp_pr.add_argument("--dry-run", action="store_true",
                       help="Show what would be proposed without writing")
    sp_pr.add_argument("--client", default=None,
                       help="Filter to a specific client (reads case_theories._clients). "
                            "Currently informational; all KEYSTONE_GROUPS are MWK.")
    sp_pr.set_defaults(func=cmd_propose)

    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        args.func(args, cur)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
