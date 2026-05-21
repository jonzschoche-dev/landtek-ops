#!/usr/bin/env python3
"""audit_case_file_assignments.py — find docs whose case_file looks wrong.

Platform-level audit. For every client in the registry, this script:

  1. Pulls the client's keystone surname set (registry + transferees +
     doc-attached entities).
  2. For each doc NOT in the client's case_file, greps extracted_text for
     keystone surnames (word-boundary).
  3. Reports docs that hit the client's graph but live under a different
     case_file — candidates for reassignment.

This is how we found docs 406, 411, 568, 586 (tagged Paracale-001 but
actually MWK Balane-family / Worrick-chain material). The platform now
catches this class of misclassification structurally rather than relying
on manual audit.

Read-only. Outputs a report; no writes. Pair with a manual review or a
deploy-time confirmation step before reassigning case_file.

Usage:
  python3 scripts/audit_case_file_assignments.py                    # audit every client
  python3 scripts/audit_case_file_assignments.py --client MWK       # one client
  python3 scripts/audit_case_file_assignments.py --client MWK --min-hits 2
"""
import argparse
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")
from case_theories._clients import CLIENTS, get, all_ids

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

STOPWORDS = {
    "atty", "judge", "hon", "mr", "ms", "mrs", "dr", "engr", "sr", "jr",
    "ii", "iii", "iv", "law", "office", "offices", "court",
    "norte", "sur", "este", "oeste", "luzon", "visayas", "mindanao",
    "philippines", "manila", "quezon", "city", "province", "municipality",
    "barangay", "brgy", "mercedes", "daet", "camarines", "san", "santa",
    "santo", "poblacion", "vicente", "rural", "urban",
    "deeds", "registry", "republic", "government", "national", "regional",
    "branch", "department", "section", "rule", "act",
    "petition", "respondent", "complainant", "petitioner", "vs", "versus",
    "mwk", "par", "arta", "tct", "oct", "rtc", "csc", "dilg", "carp",
    "mary", "jose", "juan", "rosa", "ana", "elena",
}


def surname_of(name):
    if not name:
        return None
    parts = re.split(r"[\s,.\-]+", name)
    for p in reversed(parts):
        p = re.sub(r"[^A-Za-z]", "", p).lower()
        if len(p) >= 5 and p not in STOPWORDS:
            return p
    return None


def gather_surnames(cur, client_config):
    """Set of distinctive surnames known to belong to this client's graph."""
    out = set()

    # Keystone entities
    for k, eid in (client_config.get("keystone_entities") or {}).items():
        if eid:
            cur.execute("SELECT canonical_name FROM entities WHERE id=%s", (eid,))
            r = cur.fetchone()
            if r and r["canonical_name"]:
                sn = surname_of(r["canonical_name"])
                if sn:
                    out.add(sn)
        # Also the registry key itself (handles None entries)
        toks = [t for t in k.split("_") if t not in {"jr", "sr", "ii", "iii"}]
        if toks:
            sn = toks[-1].lower()
            if len(sn) >= 5 and sn not in STOPWORDS:
                out.add(sn)

    # Transferees table
    try:
        cur.execute("SELECT canonical_name FROM transferees WHERE case_file=%s",
                    (client_config["case_file"],))
        for r in cur.fetchall():
            sn = surname_of(r["canonical_name"])
            if sn:
                out.add(sn)
    except psycopg2.errors.UndefinedTable:
        pass

    return out


def audit_client(cur, client_id, min_hits):
    cfg = get(client_id)
    print(f"\n## {cfg['label']} ({client_id}) — case_file='{cfg['case_file']}'")
    print("=" * 70)

    surnames = gather_surnames(cur, cfg)
    print(f"  client surname set ({len(surnames)}): {sorted(surnames)}")

    # Build a single regex of alternations for efficiency
    if not surnames:
        print("  ⚠ no surnames — nothing to audit")
        return
    surname_pat = r"\m(" + "|".join(re.escape(s) for s in surnames) + r")\M"  # \m \M = word boundaries in PG

    # Find docs in OTHER case_files that hit any of these surnames
    cur.execute(f"""
        SELECT id, case_file, matter_code, smart_filename,
               array_agg(DISTINCT match[1]) AS surnames_hit
          FROM (
            SELECT d.id, d.case_file, d.matter_code, d.smart_filename,
                   regexp_matches(LOWER(d.extracted_text), %s, 'g') AS match
              FROM documents d
             WHERE (d.case_file IS NULL OR d.case_file != %s)
               AND d.extracted_text IS NOT NULL
          ) sub
         GROUP BY id, case_file, matter_code, smart_filename
        HAVING COUNT(DISTINCT match[1]) >= %s
         ORDER BY COUNT(DISTINCT match[1]) DESC, id
    """, (surname_pat, cfg["case_file"], min_hits))

    rows = cur.fetchall()
    if not rows:
        print(f"  ✓ no suspicious docs (min_hits={min_hits})")
        return

    print(f"\n  {len(rows)} docs match ≥{min_hits} {client_id} surnames but live under different case_file:")
    print(f"  {'doc_id':>6}  {'case_file':<14}  {'matter_code':<22}  surnames_hit  filename")
    for r in rows[:40]:
        sn_str = ",".join(r["surnames_hit"])
        fn = (r["smart_filename"] or "")[:50]
        cf = r["case_file"] or "(none)"
        mc = r["matter_code"] or "(none)"
        print(f"  {r['id']:>6}  {cf:<14}  {mc:<22}  [{sn_str}]  {fn}")
    if len(rows) > 40:
        print(f"  …+{len(rows)-40} more")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Only audit this client (default: all)")
    ap.add_argument("--min-hits", type=int, default=2,
                    help="Require this many distinct surname hits (default: 2)")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print(f"case_file audit (min_hits={args.min_hits}, read-only)")

    if args.client:
        audit_client(cur, args.client, args.min_hits)
    else:
        for cid in all_ids():
            audit_client(cur, cid, args.min_hits)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
