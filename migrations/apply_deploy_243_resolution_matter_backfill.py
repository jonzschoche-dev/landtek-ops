#!/usr/bin/env python3
"""Deploy 243 — backfill resolutions.affected_matter_codes via regex on source doc.

Currently 25 of 27 resolutions have empty affected_matter_codes. That makes
matter-filtered queries return ~nothing (show_client.py showed "2 resolutions"
for MWK when there should be ~27).

Approach: for each resolution row with empty affected_matter_codes, regex the
source doc's extracted_text + filename for CTN/CV references. Use the same
rules as deploy_226 (gmail) and deploy_234 (docs).

Idempotent. Reads MWK config from case_theories._clients.
"""
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")
from case_theories._clients import get

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


CTN_RE = re.compile(
    r"\bCTN\s*[-:]?\s*SL\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{3,4})\b",
    re.IGNORECASE,
)
CV_RE = re.compile(
    r"\b(?:Civil\s+Case|CV|Case)\s*(?:No\.?)?\s*[-]?\s*(\d{1,4})[-]?(\d{1,4})\b",
    re.IGNORECASE,
)


def derive_matter_codes(text, client_config, valid_matter_codes):
    if not text:
        return set()
    arta_prefix = client_config.get("arta_ctn_prefix_to_matter")
    cv_map = client_config.get("civil_case_mappings") or {}
    codes = set()
    if arta_prefix:
        for m in CTN_RE.finditer(text):
            suffix = m.group(3)
            if len(suffix) == 3:
                suffix = "0" + suffix
            cand = f"{arta_prefix}{suffix}"
            if cand in valid_matter_codes:
                codes.add(cand)
    for m in CV_RE.finditer(text):
        for k in (f"{m.group(1)}-{m.group(2)}", f"{m.group(1)}{m.group(2)}"):
            if k in cv_map:
                if cv_map[k] in valid_matter_codes:
                    codes.add(cv_map[k])
    return codes


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default="MWK")
    args = ap.parse_args()

    client_config = get(args.client)
    print(f"Deploy 243 — resolution-matter linkage backfill ({args.client})")
    print("=" * 60)

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT matter_code FROM matters WHERE matter_code LIKE %s",
                (client_config["matter_prefix"] + "%",))
    valid = set(r["matter_code"] for r in cur.fetchall())
    print(f"  {len(valid)} matter_codes available")

    cur.execute("""
        SELECT r.id, r.source_doc_id, r.affected_matter_codes,
               d.extracted_text, d.smart_filename
          FROM resolutions r
          LEFT JOIN documents d ON d.id = r.source_doc_id
         WHERE cardinality(COALESCE(r.affected_matter_codes, '{}'::text[])) = 0
    """)
    rows = cur.fetchall()
    print(f"  Scanning {len(rows)} resolutions with empty affected_matter_codes")

    updated = 0
    per_matter = {}

    for r in rows:
        text = (r["smart_filename"] or "") + "\n" + (r["extracted_text"] or "")
        codes = derive_matter_codes(text, client_config, valid)
        if not codes:
            continue
        sorted_codes = sorted(codes)
        cur.execute(
            "UPDATE resolutions SET affected_matter_codes = %s WHERE id = %s",
            (sorted_codes, r["id"]),
        )
        updated += 1
        for c in sorted_codes:
            per_matter[c] = per_matter.get(c, 0) + 1

    print(f"\n  ✓ {updated} resolutions linked")
    for mc, n in sorted(per_matter.items(), key=lambda x: -x[1]):
        print(f"    {mc:<25s} {n}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
