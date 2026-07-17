#!/usr/bin/env python3
"""party_name_gate.py — shared NAME-shape gate for matter_parties writers.

Why: the old RE_PARTY in populate_tables_from_docs ran under re.I, so its
[A-Z] name-start matched any letter and 60 chars of prose after every role
keyword became a "party" ("views the receipts submitted by defendants as
beginning…"). harvest_facts trusted documents.parties JSON and entity names,
which carry email-header junk ("On Tue"). Result: 64% of matter_parties was
junk (agent_stack_sim finding, 2026-07-17).

The gate accepts only name-shaped strings:
  * 2–7 tokens, first and last a capitalized name token (initials/ALL-CAPS OK)
  * lowercase tokens allowed only as name connectors (of, the, de, dela, …)
  * sentence-start/function-word first tokens rejected (The, On, Said, …)
  * weekday tokens rejected anywhere (email headers)
Trailing "et al." is stripped before validation, not rejected.

Cleanup mode (quarantine, never hard-delete):
    python3 scripts/party_name_gate.py            # dry run — counts + samples
    python3 scripts/party_name_gate.py --go       # move junk to matter_parties_quarantine
Rows with provenance_level='verified' are never touched.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

# Lowercase connectors that may appear INSIDE a name (never first/last)
CONNECTORS = {
    "of", "the", "de", "del", "dela", "de la", "la", "los", "das", "dos",
    "da", "y", "san", "sta", "sto",
}

# A name never starts with these (sentence starts / function words / headers)
STOP_FIRST = {
    "the", "this", "that", "those", "these", "said", "same", "herein",
    "hereby", "respectfully", "on", "in", "of", "for", "and", "or", "a",
    "an", "all", "any", "his", "her", "their", "its", "our", "your",
    "who", "whom", "which", "when", "where", "what", "why", "how",
    "is", "was", "are", "were", "be", "been", "has", "had", "have",
    "to", "by", "with", "under", "over", "above", "below", "against",
    "received", "dated", "subject", "dear", "re", "fwd", "from", "sent",
    "if", "as", "at", "it", "he", "she", "they", "we", "you", "per",
    "one", "two", "three", "no", "not", "now", "then", "there", "here",
    "did", "does", "do", "will", "shall", "may", "must", "can", "upon",
    # notarial / caption boilerplate verbs ("SIGNED IN THE PRESENCE OF")
    "signed", "witnessed", "sworn", "subscribed", "acknowledged", "notarized",
    "attested", "certified", "entered", "done", "given", "issued", "filed",
}

# Never legitimate inside a party name, any position, any case:
# email-header day tokens + document-type words (doc titles are not parties)
STOP_ANY = {
    "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
    "affidavit", "counter-affidavit", "complaint", "motion", "petition",
    "notice", "certificate", "deed", "contract", "agreement", "resolution",
    "ordinance", "memorandum", "manifestation", "decision", "judgment",
    "summons", "subpoena", "annex", "exhibit", "pleading", "reply",
    "rejoinder", "affidavits",
}

# Accented capitals + ñ are first-class: Leaño, Peña, José (PH names)
_NAME_TOK = re.compile(r"^[A-ZÑÁÉÍÓÚÜ][A-Za-zñáéíóúüÑÁÉÍÓÚÜ'\-]*\.?$")
# OCR word-merge: internal capital after 4+ lowercase ("WorrickKeesey");
# Mc/Mac/Dela prefixes (≤3 lowercase before the capital) stay legal
_OCR_MERGE = re.compile(r"[A-Z][a-z]{4,}[A-Z]")
_POSSESSIVE = re.compile(r"'[sS]$")


def is_party_name(name: str) -> bool:
    """True only for name-shaped strings (person or org). Delicate: when in
    doubt, reject — matter_parties junk poisons briefs and who-is answers."""
    n = re.sub(r"\s+", " ", (name or "").strip(" .,;:*\"'()[]"))
    # Commas and nickname quotes are separators, not name content:
    # 'Barandon, Jr.' / 'Salvador "Von" Osum Dela Fuente'
    n = re.sub(r'[",()]', " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"\bet\.?\s+al\.?$", "", n, flags=re.I).strip(" .,;:")
    if not (5 <= len(n) <= 80):
        return False
    toks = n.split()
    if not (2 <= len(toks) <= 7):
        return False
    low = [t.lower().strip(".") for t in toks]
    if low[0] in STOP_FIRST:
        return False
    if any(t in STOP_ANY for t in low):
        return False
    # possessives ("Balane's") and OCR merges ("WorrickKeesey") aren't names
    if any(_POSSESSIVE.search(t) or _OCR_MERGE.search(t) for t in toks):
        return False
    # first and last must be capitalized name tokens — and never function
    # words, even uppercase ("SIGNED IN THE PRESENCE OF" ends in OF)
    if not _NAME_TOK.match(toks[0]) or not _NAME_TOK.match(toks[-1]):
        return False
    if low[-1] in CONNECTORS or low[-1] in STOP_FIRST:
        return False
    # uppercase function words mid-name are connectors at best; anything
    # else prose ("PRESENCE" passes _NAME_TOK but IN/THE around it don't)
    for tl in low[1:-1]:
        if tl in STOP_FIRST and tl not in CONNECTORS:
            return False
    for t, tl in zip(toks[1:-1], low[1:-1]):
        if _NAME_TOK.match(t):
            continue
        if tl in CONNECTORS:
            continue
        return False
    return True


# ── Cleanup mode ─────────────────────────────────────────────────────────────

def clean(go: bool) -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
    c = psycopg2.connect(dsn)
    c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS matter_parties_quarantine (
            LIKE matter_parties INCLUDING ALL,
            quarantined_at timestamptz NOT NULL DEFAULT now(),
            reason text NOT NULL DEFAULT 'name_gate'
        )
        """
    )

    cur.execute(
        """
        SELECT id, matter_code, party_name, side, provenance_level
        FROM matter_parties ORDER BY id
        """
    )
    rows = cur.fetchall()
    keep, junk, skipped_verified = [], [], 0
    for r in rows:
        if (r["provenance_level"] or "") == "verified":
            skipped_verified += 1
            continue
        (keep if is_party_name(r["party_name"]) else junk).append(r)

    print(f"matter_parties: {len(rows)} rows — keep {len(keep)}, "
          f"quarantine {len(junk)}, verified untouched {skipped_verified}")
    print("\nquarantine sample:")
    for r in junk[:15]:
        print(f"  [{r['side']}] {r['party_name'][:70]}")
    print("\nkeep sample:")
    for r in keep[:15]:
        print(f"  [{r['side']}] {r['party_name'][:70]}")

    if not go:
        print("\nDRY RUN — re-run with --go to quarantine.")
        return

    ids = [r["id"] for r in junk]
    if ids:
        cur.execute(
            """
            WITH moved AS (
                DELETE FROM matter_parties WHERE id = ANY(%s) RETURNING *
            )
            INSERT INTO matter_parties_quarantine
                (id, matter_code, entity_id, party_name, side, role,
                 provenance_level, created_at, source_doc_id, source_excerpt)
            SELECT id, matter_code, entity_id, party_name, side, role,
                   provenance_level, created_at, source_doc_id, source_excerpt
            FROM moved
            """,
            (ids,),
        )
    print(f"\nQUARANTINED {len(ids)} rows → matter_parties_quarantine "
          f"(restorable; nothing hard-deleted).")
    cur.close()
    c.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--go", action="store_true", help="actually quarantine junk rows")
    ap.add_argument("--test", metavar="NAME", help="test one name against the gate")
    a = ap.parse_args()
    if a.test is not None:
        print(f"{'PASS' if is_party_name(a.test) else 'REJECT'}: {a.test}")
        return
    clean(a.go)


if __name__ == "__main__":
    main()
