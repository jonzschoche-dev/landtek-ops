#!/usr/bin/env python3
"""Deploy 253 — text-level fallback for the entity-graph guard.

The deploy_252 guard works on doc_entities. When that table is empty for a
doc (as it is for ~70 MWK 'flag_unrelated' survivors), the guard has nothing
to check against. Found 8+ real misses on audit including:

  - doc#474: Patricia Keesey Zschoche's US passport (the plaintiff!)
  - doc#412: TCT T-50192 registered to Rosalina M. Hansol (a transferee)
  - doc#580, 776, 584: more Torralba/Juntilla CA case docs
  - doc#677: Cesar de la Fuente 2016 petition
  - doc#527, 528: Mercedes Lot 403 (the disputed municipal property)
  - doc#599: Concepcion Garrido death cert (Manuel Garrido lineage)

Three new checks (in addition to deploy_252's entity-graph overlap):

  1. CASE_FILE-PRIORITY RULE — if the document's case_file already equals the
     client's case_file, downgrade flag_unrelated to needs_manual_review.
     A human/process already attached this doc to the client; LLM verdict
     needs strong refutation, not the other way around.

  2. EXTRACTED_TEXT GREP — for each client keystone canonical_name and each
     transferee, search the doc's extracted_text + smart_filename. Plain
     case-insensitive substring with light OCR tolerance (collapse runs of
     whitespace, ignore non-alpha). If any hit, downgrade.

  3. LLM-REASONING TELL — the LLM's own 'reasoning' field often names the
     entity it sees (e.g., 'filed BY Cesar M. de la Fuente'). Search the
     reasoning text for keystone surnames. If hit, downgrade.

The guard runs PER-CLIENT (reads case_theories._clients) and is idempotent.
"""
import argparse
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")
from case_theories._clients import get

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

STOPWORD_SURNAMES = {
    # Honorifics / roles
    "atty", "judge", "hon", "mr", "ms", "mrs", "dr", "engr", "sr", "jr",
    "ii", "iii", "iv", "law", "office", "offices", "court",
    # Geographic
    "norte", "sur", "este", "oeste", "luzon", "visayas", "mindanao",
    "philippines", "manila", "quezon", "city", "province", "municipality",
    "barangay", "brgy", "mercedes", "daet", "camarines", "san", "santa",
    "santo", "poblacion", "vicente", "rural", "urban",
    # Structural
    "deeds", "registry", "republic", "government", "national", "regional",
    "branch", "department", "section", "rule", "act",
    "petition", "respondent", "complainant", "petitioner", "vs", "versus",
    # Client-id artifacts
    "mwk", "par", "arta", "tct", "oct", "rtc", "csc", "dilg", "carp",
    # Generic common given names (less distinctive than surnames)
    "mary", "jose", "juan", "rosa", "ana", "elena",
}


def surname_of(name):
    if not name:
        return None
    parts = re.split(r"[\s,.\-]+", name)
    for p in reversed(parts):
        p = re.sub(r"[^A-Za-z]", "", p).lower()
        if len(p) >= 5 and p not in STOPWORD_SURNAMES:
            return p
    return None


def gather_client_surnames(cur, client_config):
    """Surnames of every keystone + transferee + frequently-doc-attached entity."""
    surnames = set()

    # Keystones
    for k, eid in (client_config.get("keystone_entities") or {}).items():
        if eid is None:
            continue
        cur.execute("SELECT canonical_name FROM entities WHERE id=%s", (eid,))
        r = cur.fetchone()
        if r and r["canonical_name"]:
            sn = surname_of(r["canonical_name"])
            if sn:
                surnames.add(sn)

    # Transferees table
    try:
        cur.execute("SELECT canonical_name FROM transferees WHERE case_file=%s",
                    (client_config["case_file"],))
        for r in cur.fetchall():
            sn = surname_of(r["canonical_name"])
            if sn:
                surnames.add(sn)
    except psycopg2.errors.UndefinedTable:
        pass

    # Named-transferee surnames from registry (handles None entity_id cases —
    # e.g., Rosalina Hansol who's in the registry but not yet linked to entities)
    for key in (client_config.get("keystone_entities") or {}).keys():
        # keys are snake_case like 'rosalina_hansol'; last token is surname
        toks = key.split("_")
        if toks:
            sn = toks[-1].lower()
            if len(sn) >= 5 and sn not in STOPWORD_SURNAMES:
                surnames.add(sn)
        # Also handle compound surnames like 'roscoe_leano' (leano) and
        # 'severino_tenorio_jr' (tenorio — strip 'jr' suffix)
        if len(toks) >= 2 and toks[-1] in {"jr", "sr", "ii", "iii"}:
            sn = toks[-2].lower()
            if len(sn) >= 5 and sn not in STOPWORD_SURNAMES:
                surnames.add(sn)

    return surnames


def grep_text_for_surnames(text, surnames):
    """Return list of surnames found in text. Case-insensitive plain substring."""
    if not text:
        return []
    tl = text.lower()
    found = []
    for s in surnames:
        # Word-ish boundary check: require non-alphanumeric on at least one side
        # to avoid false positives like 'balane' inside 'balanced'.
        pat = re.compile(rf"(?<![a-z]){re.escape(s)}(?![a-z])", re.IGNORECASE)
        if pat.search(tl):
            found.append(s)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default="MWK")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.apply:
        cur.execute("SET LOCAL app.actor = 'entity_graph_guard_text'")

    print(f"Deploy 253 — text-level fallback guard ({args.client})")
    print("=" * 60)

    client_config = get(args.client)
    client_case_file = client_config["case_file"]
    surnames = gather_client_surnames(cur, client_config)
    print(f"  client surnames ({len(surnames)}): {sorted(list(surnames))[:30]}")

    # Pull surviving flag_unrelated proposals
    cur.execute("""
        SELECT p.id AS pid, p.doc_id, p.confidence, p.reasoning,
               d.case_file, d.smart_filename, d.extracted_text
          FROM doc_classification_proposals p
          JOIN documents d ON d.id = p.doc_id
         WHERE p.client_id = %s
           AND p.proposed_action = 'flag_unrelated'
           AND p.status = 'proposed'
         ORDER BY p.confidence DESC, p.id
    """, (args.client,))
    targets = cur.fetchall()
    print(f"\n  {len(targets)} flag_unrelated survivors to re-audit\n")

    downgrades = []  # list of (proposal, reason_list)

    for p in targets:
        reasons = []

        # Check 1: case_file priority
        if p["case_file"] == client_case_file:
            reasons.append(f"case_file already = {client_case_file}")

        # Check 2: extracted_text + smart_filename grep
        haystack = " ".join([p["extracted_text"] or "", p["smart_filename"] or ""])
        hits = grep_text_for_surnames(haystack, surnames)
        if hits:
            reasons.append(f"text-grep hit: {sorted(hits)[:5]}")

        # Check 3: LLM reasoning tells on itself
        if p["reasoning"]:
            tell_hits = grep_text_for_surnames(p["reasoning"], surnames)
            if tell_hits:
                reasons.append(f"LLM-reasoning surfaces: {sorted(tell_hits)[:5]}")

        if reasons:
            downgrades.append((p, reasons))

    print(f"  → {len(downgrades)} additional proposals would downgrade\n")

    for p, reasons in downgrades[:25]:
        print(f"    proposal#{p['pid']:>4d}  doc#{p['doc_id']:>4d}  conf={float(p['confidence']):.2f}")
        for r in reasons:
            print(f"        ↳ {r}")
    if len(downgrades) > 25:
        print(f"    …+{len(downgrades)-25} more")

    if not args.apply:
        print("\n  (dry-run — pass --apply to commit)")
        return

    print("\n  Applying...")
    for p, reasons in downgrades:
        note = ("[entity_graph_guard_text 2026-05-21] downgraded — " +
                "; ".join(reasons[:3]))[:1000]
        cur.execute("""
            UPDATE doc_classification_proposals
               SET status = 'needs_manual_review',
                   reviewed_at = now(),
                   reviewed_by = 'entity_graph_guard_text',
                   review_notes = %s
             WHERE id = %s
        """, (note, p["pid"]))

    conn.commit()
    print(f"  ✓ {len(downgrades)} additional downgrades")

    cur.execute("""
        SELECT status, COUNT(*) FROM doc_classification_proposals
         WHERE client_id=%s GROUP BY 1 ORDER BY 2 DESC
    """, (args.client,))
    print(f"\n  {args.client} proposal status distribution:")
    for r in cur.fetchall():
        print(f"    {r['status']:<25s} {r['count']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
