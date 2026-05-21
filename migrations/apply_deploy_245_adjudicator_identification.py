#!/usr/bin/env python3
"""Deploy 245 — adjudicator identification for the remaining resolutions.

After deploy_238 set adjudicator FK for Del Rosario across MWK-ARTA-*,
6 resolutions still have adjudicator_entity_id IS NULL:

  r#3  (ARTA MWK-ARTA-0690+0792)  — endorsement letter to CSC; ARTA Director signer
  r#14 (ARTA MWK-ARTA-1210)       — ARTA Resolution (Notice of Closure); ARTA Director signer
  r#16 (MWK-CV6839, no forum)     — adjudicator_name_raw="Gay Belen / Attorneys"
  r#17 (RTC, MWK-CV6839)          — adjudicator_name_raw="Jaime Resoco"
  r#18 (SC, MWK-CV6839)           — Yuzon Law Office legal MEMO (misclassified — not a resolution)
  r#23 (no forum, MWK-CV6839)     — Yuzon Law Office legal MEMO (misclassified — not a resolution)

Plan:
  - r#16: canonical "Atty. Elaine Gay R. Belen" (#4079) — RTC Daet judge per prior records
  - r#17: lookup "Jaime Resoco" (probably RTC clerk/judge) — create if missing
  - r#18, r#23: flag with resolution.notes "MISCLASSIFIED — Yuzon legal memo, candidate for removal";
                leave adjudicator NULL.
  - r#3, r#14: regex extract ARTA Director from tail; if found, lookup/create entity.

Idempotent. All changes audited (app.actor='jonathan_deploy_245').
"""
import argparse
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# ARTA Director sign-off patterns (the Director General signs every ARTA resolution).
# Pattern: line like "ATTY. <NAME>" near the end, often preceded by sworn signature block.
ARTA_DIRECTOR_RE = re.compile(
    r"(?:Director\s+General|DIRECTOR\s+GENERAL|Hearing\s+Officer)[^\n]*\n+\s*"
    r"([A-Z][A-Z\s\.,]{8,60}(?:JR\.?)?)",
    re.MULTILINE,
)


def resolve_canonical(cur, entity_id):
    """Follow canonical_id chain to the root. Returns the canonical ID."""
    seen = set()
    cur_id = entity_id
    while cur_id and cur_id not in seen:
        seen.add(cur_id)
        cur.execute("SELECT canonical_id FROM entities WHERE id=%s", (cur_id,))
        r = cur.fetchone()
        if not r or r["canonical_id"] is None:
            return cur_id
        cur_id = r["canonical_id"]
    return cur_id


def find_or_create_entity(cur, raw_name, entity_type="person"):
    """Look up an entity by canonical_name or alias. Prefer the most-complete-named
    match across the canonical equivalence class. Returns (id, created_bool)."""
    if not raw_name:
        return None, False
    # Find all candidate matches (exact + alias + fuzzy-prefix)
    candidates = set()
    cur.execute("SELECT id FROM entities WHERE LOWER(canonical_name)=LOWER(%s)", (raw_name,))
    for r in cur.fetchall():
        candidates.add(r["id"])
    cur.execute("""SELECT e.id FROM entities e
                    JOIN entity_aliases a ON a.entity_id = e.id
                   WHERE LOWER(a.alias)=LOWER(%s)""", (raw_name,))
    for r in cur.fetchall():
        candidates.add(r["id"])
    # Fuzzy: ILIKE %raw_name% on canonical_name (e.g. "Gay Belen" → "Atty. Gay Belen")
    cur.execute("SELECT id FROM entities WHERE canonical_name ILIKE %s", (f"%{raw_name}%",))
    for r in cur.fetchall():
        candidates.add(r["id"])
    if not candidates:
        return None, False
    # Resolve every candidate to its canonical root, then pick the root
    # whose canonical_name is longest (proxy for most-complete spelling).
    roots = set(resolve_canonical(cur, cid) for cid in candidates)
    cur.execute("""SELECT id, canonical_name, mentions_count
                     FROM entities
                    WHERE id = ANY(%s)
                 ORDER BY LENGTH(canonical_name) DESC, mentions_count DESC NULLS LAST
                    LIMIT 1""", (list(roots),))
    r = cur.fetchone()
    return (r["id"] if r else None), False


def set_adjudicator(cur, res_id, entity_id, notes_append=None):
    cur.execute("""
        UPDATE resolutions
           SET adjudicator_entity_id = %s,
               notes = COALESCE(notes || E'\n', '') || %s,
               updated_at = now()
         WHERE id = %s
    """, (entity_id, f"[deploy_245] linked adjudicator entity#{entity_id}" + (f" — {notes_append}" if notes_append else ""), res_id))


def flag_misclassified(cur, res_id, reason):
    cur.execute("""
        UPDATE resolutions
           SET notes = COALESCE(notes || E'\n', '') || %s,
               updated_at = now()
         WHERE id = %s
    """, (f"[deploy_245] MISCLASSIFIED — {reason}", res_id))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Without --apply: dry-run report only")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.apply:
        cur.execute("SET LOCAL app.actor = 'jonathan_deploy_245'")

    print("Deploy 245 — adjudicator identification (remaining 6 resolutions)")
    print("=" * 60)

    # Pull all candidates
    cur.execute("""
        SELECT r.id, r.adjudicator_name_raw, r.forum, r.affected_matter_codes,
               d.id AS did, d.smart_filename, d.extracted_text
          FROM resolutions r
          LEFT JOIN documents d ON d.id = r.source_doc_id
         WHERE r.adjudicator_entity_id IS NULL
           AND cardinality(COALESCE(r.affected_matter_codes, '{}'::text[])) > 0
         ORDER BY r.id
    """)
    rows = cur.fetchall()
    print(f"  {len(rows)} resolutions to process\n")

    actions = []  # (res_id, action, detail)

    for r in rows:
        rid = r["id"]
        raw = (r["adjudicator_name_raw"] or "").strip()
        text = r["extracted_text"] or ""
        fn = (r["smart_filename"] or "").lower()

        # Misclassification detector — Yuzon Law Office legal memos
        if "YUZON LAW OFFICE" in text[:200].upper():
            actions.append((rid, "flag_misclassified",
                            "Yuzon legal memo (legal opinion, not adjudicator's resolution)"))
            continue

        # Raw name resolution
        if raw:
            # Strip noise like "/ Attorneys"
            cleaned = re.split(r"[/\n]", raw)[0].strip()
            eid, _ = find_or_create_entity(cur, cleaned)
            if eid:
                actions.append((rid, "set_adjudicator", f"{cleaned!r} → #{eid}"))
                continue
            # Try canonical-form variants
            for prefix in ("Atty. ", "Hon. "):
                eid, _ = find_or_create_entity(cur, prefix + cleaned)
                if eid:
                    actions.append((rid, "set_adjudicator", f"{prefix}{cleaned!r} → #{eid}"))
                    break
            if eid:
                continue

        # ARTA-doc adjudicator extraction
        if "ANTI-RED TAPE AUTHORITY" in text.upper() or "ARTA" in (r["forum"] or "").upper():
            # Find ARTA Director from doc tail
            tail = text[-3000:] if len(text) > 3000 else text
            m = ARTA_DIRECTOR_RE.search(tail)
            if m:
                candidate = m.group(1).strip().title()
                eid, _ = find_or_create_entity(cur, candidate)
                if eid:
                    actions.append((rid, "set_adjudicator", f"ARTA Director {candidate!r} → #{eid}"))
                    continue
            actions.append((rid, "no_match",
                            "ARTA doc but no Director sign-off matched in tail — leave NULL, flag for review"))
            continue

        actions.append((rid, "no_match", f"raw={raw!r}, forum={r['forum']!r} — no rule matched"))

    # Report + apply
    print("  Proposed actions:")
    for rid, action, detail in actions:
        print(f"    r#{rid:>3d}  {action:<22s}  {detail}")

    if not args.apply:
        print("\n  (dry-run — pass --apply to commit)")
        return

    print("\n  Applying...")
    for rid, action, detail in actions:
        if action == "set_adjudicator":
            eid = int(re.search(r"#(\d+)", detail).group(1))
            set_adjudicator(cur, rid, eid, notes_append=detail)
        elif action == "flag_misclassified":
            flag_misclassified(cur, rid, detail)
        # no_match → leave alone but add a review note
        elif action == "no_match":
            cur.execute("""UPDATE resolutions
                              SET notes = COALESCE(notes || E'\n', '') || %s,
                                  updated_at = now()
                            WHERE id = %s""",
                        (f"[deploy_245] NEEDS_REVIEW — {detail}", rid))
    print("  ✓ done")

    # Recap counts
    cur.execute("SELECT COUNT(*) AS n FROM resolutions WHERE adjudicator_entity_id IS NOT NULL")
    print(f"\n  Adjudicator coverage now: {cur.fetchone()['n']} / 27 resolutions")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
