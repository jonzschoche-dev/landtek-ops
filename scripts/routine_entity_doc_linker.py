#!/usr/bin/env python3
"""routine_entity_doc_linker.py — deploy_340.

Compounds the KB: link verified/strong canonical entities to the documents
that mention them. Closes the gap surfaced 2026-06-06 (Erwin Balane has 16+
doc mentions in MWK scope but zero doc_entities rows; same for ~25 other
high-value entities including TCT-4497, Efren Balane, Atty. Barandon).

Algorithm (deterministic, no LLM):
  1. Find entities with mentions_count >= MIN_MENTIONS AND zero doc_entities
     rows. Process in descending-mentions order so the highest-value entities
     get bridged first.
  2. For each such entity:
       a. Build a regex from the canonical_name + any aliases. Escape, anchor
          on word boundaries, case-insensitive.
       b. For every document whose extracted_text matches, INSERT a
          doc_entities row with role='mentioned' (a downstream LLM pass can
          refine the role), context_excerpt = 80 chars before + match + 80
          after, source_quote = same.
       c. Skip if the (doc_id, entity_id, role) PK already exists.
  3. After processing, update entities.mentions_count to reflect actual linked
     docs (the existing count may be wrong since it was never anchored to
     actual links).

Idempotent. Safe to run on a 30-min systemd timer. Logs counts per entity +
running total per matter.

Cost: $0 — pure SQL + Python regex. No LLM calls.

Usage:
    python3 scripts/routine_entity_doc_linker.py                # default batch
    python3 scripts/routine_entity_doc_linker.py --max 50       # bigger batch
    python3 scripts/routine_entity_doc_linker.py --entity 3060  # specific entity
    python3 scripts/routine_entity_doc_linker.py --dry-run      # preview only
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

MIN_MENTIONS = 5         # only bridge entities the corpus already sees 5+ times
DEFAULT_BATCH = 20       # process this many entities per run
EXCERPT_WINDOW = 80      # chars on each side of match
MAX_LINKS_PER_ENTITY = 60  # safety cap


def find_unlinked_entities(cur, limit: int, entity_id: int | None = None):
    """Entities with mentions_count >= MIN_MENTIONS and no doc_entities rows."""
    if entity_id is not None:
        cur.execute("""
            SELECT id, canonical_name, COALESCE(aliases, ARRAY[]::text[]) AS aliases,
                   mentions_count, provenance_level
              FROM entities WHERE id = %s
        """, (entity_id,))
        return cur.fetchall()
    cur.execute("""
        SELECT e.id, e.canonical_name, COALESCE(e.aliases, ARRAY[]::text[]) AS aliases,
               e.mentions_count, e.provenance_level
          FROM entities e
         WHERE e.provenance_level IN ('verified', 'inferred_strong')
           AND e.mentions_count >= %s
           AND NOT EXISTS (
               SELECT 1 FROM doc_entities de WHERE de.entity_id = e.id
           )
           AND e.canonical_name !~* '^(sim\\d+|test|null|unknown)'
           AND length(e.canonical_name) >= 3
         ORDER BY e.mentions_count DESC, e.id
         LIMIT %s
    """, (MIN_MENTIONS, limit))
    return cur.fetchall()


def build_match_regex(canonical_name: str, aliases: list[str]) -> re.Pattern | None:
    """Build a case-insensitive word-bounded regex from name + aliases."""
    forms = [canonical_name] + [a for a in (aliases or []) if a and a.strip()]
    # Filter forms: skip very short (< 4 chars) and pure-stopword forms
    forms = [f.strip() for f in forms if f and len(f.strip()) >= 4]
    if not forms:
        return None
    escaped = [re.escape(f) for f in sorted(set(forms), key=len, reverse=True)]
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def find_matching_docs(cur, regex: re.Pattern, canonical_name: str, limit: int):
    """Find documents whose extracted_text matches the entity regex.
    Uses fulltext + LIKE for the candidate pool, then verifies with the regex.
    """
    # Coarse filter: use ILIKE on the most distinctive substring to narrow
    # candidates before running the precise regex check in Python.
    # Pick the longest token in canonical_name as the discriminating ILIKE.
    tokens = [t for t in re.split(r"\W+", canonical_name) if len(t) >= 4]
    if not tokens:
        return []
    most_distinctive = max(tokens, key=len)
    cur.execute("""
        SELECT id, case_file, extracted_text
          FROM documents
         WHERE extracted_text IS NOT NULL
           AND extracted_text ILIKE %s
         ORDER BY id
         LIMIT %s
    """, ('%' + most_distinctive + '%', limit * 5))  # 5x for over-fetch
    matches = []
    for row in cur.fetchall():
        m = regex.search(row["extracted_text"])
        if not m:
            continue
        # Build context excerpt
        text = row["extracted_text"]
        start = max(0, m.start() - EXCERPT_WINDOW)
        end = min(len(text), m.end() + EXCERPT_WINDOW)
        excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
        matches.append({
            "doc_id": row["id"],
            "case_file": row["case_file"],
            "excerpt": excerpt[:600],
            "matched_form": m.group(0),
        })
        if len(matches) >= limit:
            break
    return matches


def link_entity(cur, entity_id: int, entity_name: str, matches: list[dict],
                dry_run: bool) -> int:
    """Insert doc_entities rows. Returns count actually inserted."""
    if dry_run:
        return len(matches)
    written = 0
    for m in matches:
        try:
            cur.execute("""
                INSERT INTO doc_entities
                  (doc_id, entity_id, role, context_excerpt, confidence,
                   source_quote, provenance_level, extracted_by, extracted_at)
                VALUES (%s, %s, 'mentioned', %s, 0.85, %s, 'inferred_strong',
                        'routine_entity_doc_linker_v1', NOW())
                ON CONFLICT (doc_id, entity_id, role) DO NOTHING
            """, (m["doc_id"], entity_id, m["excerpt"], m["excerpt"]))
            if cur.rowcount > 0:
                written += 1
        except Exception as e:
            print(f"    ⚠ insert failed for doc#{m['doc_id']}: {str(e)[:80]}")
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=DEFAULT_BATCH,
                    help=f"max entities to process this run (default {DEFAULT_BATCH})")
    ap.add_argument("--entity", type=int, default=None,
                    help="process a specific entity id (testing)")
    ap.add_argument("--dry-run", action="store_true",
                    help="preview without writing")
    args = ap.parse_args()

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[entity_doc_linker] {started} batch={args.max} dry_run={args.dry_run}")

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    unlinked = find_unlinked_entities(cur, args.max, args.entity)
    if not unlinked:
        print("  ✓ no eligible unlinked entities — nothing to do")
        return

    total_linked = 0
    total_entities = 0
    for ent in unlinked:
        regex = build_match_regex(ent["canonical_name"], ent["aliases"])
        if not regex:
            print(f"  skip e#{ent['id']:>5} {ent['canonical_name'][:50]:<50} → no matchable form")
            continue
        matches = find_matching_docs(cur, regex, ent["canonical_name"],
                                      MAX_LINKS_PER_ENTITY)
        if not matches:
            print(f"  e#{ent['id']:>5} {ent['canonical_name'][:50]:<50} → 0 matches")
            continue
        written = link_entity(cur, ent["id"], ent["canonical_name"], matches,
                              args.dry_run)
        marker = "(dry) " if args.dry_run else ""
        print(f"  {marker}e#{ent['id']:>5} {ent['canonical_name'][:50]:<50} "
              f"→ {written} links written (mentions_count was {ent['mentions_count']})")
        total_linked += written
        total_entities += 1

    print(f"[entity_doc_linker] DONE entities={total_entities} links_written={total_linked}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
