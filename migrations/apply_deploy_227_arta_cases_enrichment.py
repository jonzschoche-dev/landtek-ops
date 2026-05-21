#!/usr/bin/env python3
"""Deploy 227 — arta_cases enrichment + adjudicator-side proposed entities.

Two halves:

  (A) DETERMINISTIC arta_cases backfill — pure SQL/regex, no LLM:
      - matter_code: derived from CTN suffix → MWK-ARTA-XXXX (validated against
        the matters table; only assigned if the matter_code exists).
      - subject_summary: derived from "Zschoche v. <RESPONDENT>" pattern in
        linked email subjects.
      - respondents: array from the same parsed v.<X> pattern.
      - last_activity: synced to MAX(gmail.sent_at) for the linked matter.
      - forum: set to 'ARTA Southern Luzon RFO, Batangas City' (the verified
        forum per doc#465; same for all our active ARTA cases).
      - adjudicator_entity_id: column added, NULL until entity promotion (B).

  (B) PROPOSED ENTITIES for the three adjudicator-side actors, inserted into
      proposed_changes (NOT promoted). Per deploy_221B discipline:
        - Atty. Rodolfo B. Del Rosario Jr. — ARTA Southern Luzon RFO adjudicator
        - Atty. Daisy Punzalan Bragais — CSC Regional Office V, Legazpi
        - Undersecretary Genes R. Abot — ARTA Office of the President
      Reviewed + promoted via: python3 scripts/promote_proposals.py review

Idempotent. Re-running is safe.
"""
import json
import re

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# "Zschoche v. <something>" pattern (case-insensitive, stops at common terminators)
ZS_V_RE = re.compile(
    r"Zschoche\s+v\.?\s+(.+?)(?=[,\-\n\|\(]|\s+CTN|\s+SL-|\s+ARTA|\s+Case|\s+Civil|\s*$)",
    re.IGNORECASE,
)


def derive_respondent_from_subject(subject):
    """Extract the X in 'Zschoche v. X' — return cleaned string or None."""
    if not subject:
        return None
    m = ZS_V_RE.search(subject)
    if not m:
        return None
    s = m.group(1).strip()
    # Trim trailing fluff
    s = re.sub(r"\s+(in his|in her|in their|in the matter).*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*[-:|]+\s*$", "", s)
    if len(s) < 3 or len(s) > 200:
        return None
    return s


SCHEMA_SQL = """
ALTER TABLE arta_cases
    ADD COLUMN IF NOT EXISTS adjudicator_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS forum TEXT;

CREATE INDEX IF NOT EXISTS idx_arta_cases_matter_code
    ON arta_cases(matter_code);
CREATE INDEX IF NOT EXISTS idx_arta_cases_adjudicator
    ON arta_cases(adjudicator_entity_id);
"""


def backfill_matter_codes(cur):
    """For each arta_cases row, set matter_code = MWK-ARTA-<suffix> if the
    matter_code exists in matters."""
    cur.execute("SELECT matter_code FROM matters")
    valid = set(r["matter_code"] for r in cur.fetchall())

    cur.execute("SELECT id, ctn_no, matter_code FROM arta_cases")
    rows = cur.fetchall()
    updated = 0
    skipped = []

    for r in rows:
        if r["matter_code"]:
            continue  # already populated
        m = re.search(r"(\d{3,4})\s*$", r["ctn_no"] or "")
        if not m:
            skipped.append((r["ctn_no"], "no-suffix-match"))
            continue
        suffix = m.group(1)
        if len(suffix) == 3:
            suffix = "0" + suffix
        candidate = f"MWK-ARTA-{suffix}"
        if candidate not in valid:
            skipped.append((r["ctn_no"], f"no matter for {candidate}"))
            continue
        cur.execute(
            "UPDATE arta_cases SET matter_code = %s, updated_at = NOW() WHERE id = %s",
            (candidate, r["id"]),
        )
        updated += 1
        print(f"    ✓ {r['ctn_no']} → {candidate}")
    if skipped:
        print(f"    {len(skipped)} skipped: {skipped[:3]}")
    return updated


def backfill_respondents_and_subject(cur):
    """Derive respondents + subject_summary from linked email subjects."""
    cur.execute("""
        SELECT a.id, a.ctn_no, a.matter_code
          FROM arta_cases a
         WHERE a.matter_code IS NOT NULL
    """)
    cases = cur.fetchall()
    updated = 0

    for c in cases:
        # Pull linked email subjects for this matter
        cur.execute("""
            SELECT subject FROM gmail_messages
             WHERE %s = ANY(matter_codes) AND subject IS NOT NULL
             ORDER BY sent_at DESC NULLS LAST
        """, (c["matter_code"],))
        subjects = [r["subject"] for r in cur.fetchall()]

        # Tally respondent candidates
        from collections import Counter
        candidates = Counter()
        for s in subjects:
            r = derive_respondent_from_subject(s)
            if r:
                candidates[r] += 1
        if not candidates:
            continue

        # Top respondent name (most-frequent)
        top_respondent, top_count = candidates.most_common(1)[0]
        # Build subject summary
        summary = f"Zschoche v. {top_respondent} ({c['ctn_no']})"

        respondents_array = [top_respondent]
        # Add alternates seen multiple times
        for cand, n in candidates.most_common()[1:]:
            if n >= 2 and cand not in respondents_array:
                respondents_array.append(cand)

        cur.execute("""
            UPDATE arta_cases
               SET respondents = %s,
                   subject_summary = %s,
                   updated_at = NOW()
             WHERE id = %s
        """, (respondents_array, summary, c["id"]))
        updated += 1
        print(f"    ✓ {c['ctn_no']} → respondents={respondents_array} (summary preview: {summary[:80]})")
    return updated


def backfill_last_activity_and_forum(cur):
    """Sync last_activity to MAX of linked gmail sent_at; set default forum."""
    cur.execute("""
        UPDATE arta_cases a
           SET last_activity = sub.maxdate,
               forum = COALESCE(a.forum, 'ARTA Southern Luzon RFO, Batangas City'),
               updated_at = NOW()
          FROM (
              SELECT a2.id, MAX(g.sent_at::date) AS maxdate
                FROM arta_cases a2
                LEFT JOIN gmail_messages g
                       ON a2.matter_code = ANY(g.matter_codes)
               GROUP BY a2.id
          ) sub
         WHERE a.id = sub.id
           AND sub.maxdate IS NOT NULL
           AND (a.last_activity IS NULL OR a.last_activity < sub.maxdate)
    """)
    return cur.rowcount


# ─── Proposed adjudicator entities (LLM-extracted from doc#465 + doc#706) ──
PROPOSED_ENTITIES = [
    {
        "type": "person",
        "canonical_name": "Atty. Rodolfo B. Del Rosario Jr.",
        "aliases": [
            "Rodolfo B. Del Rosario Jr.",
            "Atty. Del Rosario Jr.",
            "Atty. Del Rosario",
            "Del Rosario Jr.",
            "Rodolfo Del Rosario",
        ],
        "role": "ARTA adjudicator / hearing officer for Zschoche ARTA matters in Southern Luzon",
        "affiliation": "Anti-Red Tape Authority (ARTA), Southern Luzon Regional Field Office, Batangas City",
        "provenance_level": "inferred_strong",
        "notes": "Source: doc#465 (April 20 2026 Request to Defer addressed to him). "
                 "Adjudicator on April 7 2026 Resolution covering CTN SL-2025-1008-0690 + "
                 "CTN SL-2025-1104-0792. Also referenced on May 18 2026 NOC Resolution "
                 "for CTN SL-2026-0128-1210.",
        "_rationale": "Three matters (0690, 0792, 1210) have an active correspondence "
                      "chain with him as named adjudicator. Required for "
                      "adjudicator_entity_id population on arta_cases.",
    },
    {
        "type": "person",
        "canonical_name": "Atty. Daisy Punzalan Bragais",
        "aliases": [
            "Daisy Punzalan Bragais",
            "Atty. Bragais",
            "Daisy P. Bragais",
        ],
        "role": "Director IV, Civil Service Commission — Regional Office V (Legazpi). "
                "Receives ARTA endorsements re: alleged misconduct by Mercedes officials.",
        "affiliation": "Civil Service Commission, Regional Office V, Legazpi City",
        "provenance_level": "inferred_strong",
        "notes": "Source: doc#706 (April 30 2026 ARTA Endorsement of April 7 Resolution "
                 "to her office). Receives endorsement for CTN SL-2025-1008-0690 + "
                 "CTN SL-2025-1104-0792.",
        "_rationale": "Second-witness recipient of ARTA's referral to CSC. Relevant to "
                      "the procedural posture of the MEO Mercedes matters.",
    },
    {
        "type": "person",
        "canonical_name": "Undersecretary Genes R. Abot",
        "aliases": [
            "Genes R. Abot",
            "Genes Abot",
            "USec Abot",
            "Undersec. Abot",
        ],
        "role": "Undersecretary, Anti-Red Tape Authority — Office of the President",
        "affiliation": "Anti-Red Tape Authority (ARTA), Office of the President",
        "provenance_level": "inferred_strong",
        "notes": "Source: doc#465 (CC'd on April 20 2026 deferral request). "
                 "Senior official within ARTA's chain of command above the Southern "
                 "Luzon RFO; OP escalation path.",
        "_rationale": "Named cc recipient on Jonathan's deferral request and likely "
                      "recipient of any OP-level escalation (cf. May 6 2026 'Notice of "
                      "Filing at the Office of the President' emails).",
    },
]


def insert_proposed_entities(cur):
    """Insert each proposed entity into proposed_changes for human review."""
    inserted = 0
    skipped = 0
    for e in PROPOSED_ENTITIES:
        canonical = e["canonical_name"]
        # Skip if already proposed or already exists as a verified entity
        cur.execute(
            "SELECT 1 FROM entities WHERE canonical_name = %s LIMIT 1", (canonical,)
        )
        if cur.fetchone():
            print(f"    – entity already exists: {canonical}")
            skipped += 1
            continue
        cur.execute(
            """SELECT 1 FROM proposed_changes
                WHERE target_table = 'entities' AND review_status = 'pending'
                  AND proposed_state->>'canonical_name' = %s LIMIT 1""",
            (canonical,),
        )
        if cur.fetchone():
            print(f"    – already in proposed_changes: {canonical}")
            skipped += 1
            continue

        # Strip the _rationale before storing as proposed_state
        state = {k: v for k, v in e.items() if not k.startswith("_")}
        cur.execute(
            """INSERT INTO proposed_changes
                   (target_table, target_row_id, operation, proposed_state,
                    proposed_by, rationale, review_status)
                VALUES ('entities', NULL, 'INSERT', %s::jsonb,
                        'deploy_227_arta_adjudicators',
                        %s, 'pending')""",
            (json.dumps(state), e["_rationale"]),
        )
        inserted += 1
        print(f"    ✓ proposed: {canonical}")
    return inserted, skipped


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 227 — arta_cases enrichment + proposed adjudicator entities")
    print("=" * 70)

    print("\n[1/5] Schema additions on arta_cases")
    cur.execute(SCHEMA_SQL)
    print("  ✓ adjudicator_entity_id + forum columns + indexes")

    print("\n[2/5] Backfill arta_cases.matter_code from CTN suffix")
    n = backfill_matter_codes(cur)
    print(f"  → {n} cases linked to a matter")

    print("\n[3/5] Backfill respondents + subject_summary from email subjects")
    n = backfill_respondents_and_subject(cur)
    print(f"  → {n} cases enriched")

    print("\n[4/5] Sync last_activity + default forum")
    n = backfill_last_activity_and_forum(cur)
    print(f"  → {n} cases updated")

    print("\n[5/5] Propose 3 adjudicator-side entities for human review")
    n, s = insert_proposed_entities(cur)
    print(f"  → {n} proposed, {s} skipped (already exist)")

    # Final snapshot
    print("\n" + "=" * 70)
    print("Final arta_cases state:")
    cur.execute("""
        SELECT ctn_no, matter_code, last_activity,
               array_to_string(respondents, ', ') AS resp,
               LEFT(COALESCE(subject_summary, ''), 60) AS subj
          FROM arta_cases
         ORDER BY last_activity DESC NULLS LAST
    """)
    for r in cur.fetchall():
        print(f"  {r['ctn_no']:<24s} {r['matter_code'] or '-':<18s} {r['last_activity']}")
        print(f"    resp: {r['resp'] or '(none)'}")
        print(f"    subj: {r['subj'] or '(none)'}")

    print()
    print("Next: review + promote the 3 proposed entities with:")
    print("    python3 scripts/promote_proposals.py review --table entities")
    print()
    print("After promotion, deploy_228 will link arta_cases.adjudicator_entity_id.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
