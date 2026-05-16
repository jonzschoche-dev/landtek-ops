#!/usr/bin/env python3
"""Conflict detector — deploy_099.

SQL-driven. Catches three high-value contradictions:

  1. Same TCT/property attributed to multiple owner persons across docs
     (the Gloria-Balane-fraud signal — same title, two claimed owners).
  2. Same case docket linked to multiple case_file values.
  3. Same date_event entity_name appearing with different ISO dates
     (eg. "hearing date" Sept 3 in one doc, Sept 5 in another).

Flags via:
  - chat_note insert (topic='evidence', importance=4) for review
  - Telegram DM to Jonathan summarizing the conflict

Idempotent: re-running on already-flagged conflicts won't double-insert
(matches against existing chat_notes by content fingerprint).
"""
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
JONATHAN_TG_ID = "6513067717"


def _token():
    for l in open("/root/landtek/.env"):
        if l.startswith("TELEGRAM_BOT_TOKEN="):
            return l.split("=", 1)[1].strip()


def tg_send(text, parse_mode="HTML"):
    tok = _token()
    if not tok: return False
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data=urllib.parse.urlencode({"chat_id": JONATHAN_TG_ID, "text": text[:4090], "parse_mode": parse_mode}).encode(),
            timeout=10,
        ).read()
        return True
    except Exception as e:
        print(f"tg fail: {e}", file=sys.stderr); return False


def flag_conflict(cur, content, summary, related_case=None, importance=4):
    """Insert chat_note if not already flagged (matches on content prefix)."""
    cur.execute("""
        SELECT id FROM chat_notes
         WHERE topic = 'evidence'
           AND LEFT(content, 100) = LEFT(%s, 100)
         LIMIT 1
    """, (content,))
    if cur.fetchone():
        return False  # already flagged
    cur.execute("""
        INSERT INTO chat_notes (content, summary, topic, importance, related_case, created_at)
        VALUES (%s, %s, 'evidence', %s, %s, now())
        RETURNING id
    """, (content, summary, importance, related_case))
    return cur.fetchone()["id"]


def main():
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    flagged = []

    # ── 1. Same TCT, multiple owners ──────────────────────────────────────
    # Properties (TCTs) and persons co-mentioned in the same docs.
    # If 2+ persons claimed ownership of the same TCT in any single doc, flag.
    cur.execute("""
        WITH tct_person_mentions AS (
          SELECT DISTINCT
                 p.canonical_name AS tct,
                 pe.canonical_name AS person,
                 LEAST(pe.first_seen_doc, pe.last_seen_doc) AS doc_low,
                 GREATEST(pe.first_seen_doc, pe.last_seen_doc) AS doc_high
            FROM entities p
            JOIN entities pe ON pe.type = 'person'
                            AND (
                              pe.first_seen_doc = p.first_seen_doc
                              OR pe.last_seen_doc = p.last_seen_doc
                              OR pe.first_seen_doc = p.last_seen_doc
                              OR pe.last_seen_doc = p.first_seen_doc
                            )
           WHERE p.type = 'property'
             AND p.canonical_name ILIKE 'TCT-%%'
        )
        SELECT tct, array_agg(DISTINCT person) AS persons, count(DISTINCT person) AS n_persons
          FROM tct_person_mentions
         GROUP BY tct
         HAVING count(DISTINCT person) >= 4
         ORDER BY count(DISTINCT person) DESC
         LIMIT 10;
    """)
    for r in cur.fetchall():
        # 4+ persons co-occurring with same TCT is suspicious — flag for review
        content = f"CONFLICT-CANDIDATE: {r['tct']} co-mentioned with {r['n_persons']} distinct persons across docs: {', '.join(r['persons'][:5])}. Review for ownership-claim conflicts."
        nid = flag_conflict(cur, content, f"Possible ownership conflict on {r['tct']}", related_case="MWK-001", importance=4)
        if nid:
            flagged.append(("TCT-multi-owner", r["tct"], r["n_persons"]))

    # ── 2. Same docket → multiple case_files ──────────────────────────────
    cur.execute("""
        SELECT canonical_name, array_agg(DISTINCT d.case_file) AS cases
          FROM entities e
          JOIN documents d ON d.id IN (e.first_seen_doc, e.last_seen_doc)
         WHERE e.type = 'case_or_docket'
           AND d.case_file IS NOT NULL AND d.case_file != ''
         GROUP BY canonical_name
         HAVING count(DISTINCT d.case_file) > 1
         LIMIT 10;
    """)
    for r in cur.fetchall():
        content = f"CONFLICT-CANDIDATE: docket '{r['canonical_name']}' appears in multiple case files: {r['cases']}. Confirm correct case_file assignment."
        nid = flag_conflict(cur, content, f"Docket {r['canonical_name'][:30]} spans cases {r['cases']}", importance=3)
        if nid:
            flagged.append(("docket-multi-case", r["canonical_name"], r["cases"]))

    # ── 3. Same date_event name, different dates (likely typo/inconsistency) ──
    # canonical_name often contains a date string — when same event has
    # multiple date_event entries, that's a flag.
    cur.execute("""
        SELECT
          regexp_replace(canonical_name, '\\d{1,2}\\s*[/,-]\\s*\\d{1,2}\\s*[/,-]\\s*\\d{2,4}|\\d{4}-\\d{2}-\\d{2}', 'XXX', 'g') AS normalized,
          array_agg(canonical_name) AS variants,
          count(*) AS n
          FROM entities
         WHERE type = 'date_event'
           AND mentions_count >= 2
         GROUP BY normalized
         HAVING count(*) >= 2
         ORDER BY count(*) DESC
         LIMIT 10;
    """)
    for r in cur.fetchall():
        if len(set(r["variants"])) < 2:
            continue
        content = f"CONFLICT-CANDIDATE: date_event with multiple variants: {r['variants']}. Likely OCR/typo variations of the same event — verify canonical date."
        nid = flag_conflict(cur, content, f"date variants: {r['variants'][:3]}", importance=2)
        if nid:
            flagged.append(("date-variants", r["normalized"], r["variants"]))

    cur.close(); conn.close()

    if flagged:
        msg_lines = [f"⚠️ <b>Conflict detector — {len(flagged)} new flag(s)</b>", ""]
        for kind, key, val in flagged[:10]:
            msg_lines.append(f"  • [{kind}] {str(key)[:60]}: {str(val)[:80]}")
        msg_lines.append("\nReview in chat_notes (topic=evidence) or run /api/search?q=CONFLICT-CANDIDATE.")
        tg_send("\n".join(msg_lines))
        print(f"  ✓ flagged {len(flagged)} new conflicts (Telegram DM sent)")
    else:
        print(f"  ✓ no new conflicts detected (existing flags untouched)")


if __name__ == "__main__":
    main()
