#!/usr/bin/env python3
"""Deploy 261 — round-2 gmail matter linkage for the 598 still-unlinked.

Deploy_226 hit the easy ones via CTN/CV regex. The 598 stragglers need
softer signals:

  Pass 1 — SENDER ALLOWLIST → MWK-CV26360 (or finer if subject also hits)
    "BONIFACIO, JR. BARANDON" (counsel)            → MWK-CV26360
    "colen ibasco" (Cesar's wife, MWK adversary)   → MWK-CV26360
    "Litigation Division - ARTA" (already linked some → tag remaining as
       MWK-CV26360 fallback if no CTN found)
    "DILG CAMARINES NORTE"                         → MWK-CV26360 (referrals)

  Pass 2 — SENDER DENYLIST → leave alone (clearly not matter material)
    Redfin, NerdWallet, GitHub, Samsung, Hiive, realtor.com, Agoda,
    Pelican Parts. Mark with relevance_reasons += ['deploy_261:noise_sender']
    so the relevance system knows we triaged them.

  Pass 3 — SUBJECT/BODY surname grep on remaining
    Surname matches against MWK keystone+transferee set (same as
    deploy_252/253 audit logic) → MWK-CV26360 if transferee, MWK-ESTATE
    if family.

  Pass 4 — THREAD INHERITANCE
    For any still-unlinked email whose thread_id has at least one other
    email with matter_codes — inherit that matter_codes array.

Idempotent. Audited via app.actor='jonathan_deploy_261'.
"""
import argparse
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")
from case_theories._clients import get

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Sender allowlist → default matter_codes if subject/body has no finer signal
SENDER_TO_DEFAULT_MATTER = {
    "barandon_lawoffice@yahoo.com":   "MWK-CV26360",  # counsel
    "colenacious@yahoo.com":          "MWK-CV26360",  # Cesar's wife
    "dilgcamarinesnorte2020@gmail.com": "MWK-CV26360",
    "litigationdivision@arta.gov.ph": "MWK-CV26360",
    "lourdestotanes@yahoo.com":       "MWK-CV26360",  # ARTA-related correspondence
}

# Noise senders — mark and skip
NOISE_DOMAINS = {
    "redfin.com", "nerdwallet.com", "github.com", "samsung", "hiive.com",
    "realtor.com", "agoda-emails.com", "pelicanparts.com", "noreply@",
    "newsletter", "no-reply",
}

# MWK keystone/transferee surnames (lower-case, distinctive)
MWK_SURNAMES = {
    # Family
    "worrick", "keesey", "kessey", "hoppe", "zschoche",
    # Adversaries / defendants
    "balane", "fuente", "ramirez", "pajarillo", "macale", "barandon",
    "ibasco", "pajarillo", "rosario", "bragais",
    # Transferees
    "victa", "apor", "mabeza", "bernardo", "gaulit", "vela", "santiago",
    "iligan", "illigan", "tychingco", "pascual", "onrubio", "cereza",
    "mariquita", "valledor", "hansol", "leano", "ocan", "tenorio",
}

FAMILY_SURNAMES = {"worrick", "keesey", "kessey", "hoppe", "zschoche"}


def looks_like_noise(addr):
    if not addr:
        return False
    al = addr.lower()
    return any(n in al for n in NOISE_DOMAINS)


def extract_sender_domain(from_addr):
    """Pull the email out of 'Name <user@host>' format."""
    if not from_addr:
        return ""
    m = re.search(r"<([^>]+)>", from_addr)
    return (m.group(1) if m else from_addr).lower()


def grep_surnames(text):
    if not text:
        return []
    tl = text.lower()
    return [s for s in MWK_SURNAMES if re.search(rf"(?<![a-z]){s}(?![a-z])", tl)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.apply:
        cur.execute("SET LOCAL app.actor = 'jonathan_deploy_261'")

    print("Deploy 261 — round-2 gmail matter backfill")
    print("=" * 60)

    cur.execute("""
        SELECT COUNT(*) AS unlinked FROM gmail_messages
         WHERE cardinality(COALESCE(matter_codes, '{}'::text[])) = 0
    """)
    pre = cur.fetchone()["unlinked"]
    print(f"  Before: {pre} unlinked emails\n")

    # --- Pass 1+2+3 ---
    cur.execute("""
        SELECT id, from_addr, subject, COALESCE(body_plain, '') AS body, thread_id
          FROM gmail_messages
         WHERE cardinality(COALESCE(matter_codes, '{}'::text[])) = 0
         ORDER BY id
    """)
    rows = cur.fetchall()

    counts = {"sender_allow": 0, "surname": 0, "noise": 0, "skip": 0}
    matter_assigns = {}  # doc -> matter_code

    for r in rows:
        from_addr = r["from_addr"] or ""
        haystack = " ".join([from_addr, r["subject"] or "", r["body"] or ""])

        # Pass 2 — noise sender check FIRST
        if looks_like_noise(extract_sender_domain(from_addr)):
            counts["noise"] += 1
            if args.apply:
                cur.execute("""
                    UPDATE gmail_messages
                       SET relevance_reasons = COALESCE(relevance_reasons, '{}'::text[]) || ARRAY['deploy_261:noise_sender']
                     WHERE id = %s AND NOT ('deploy_261:noise_sender' = ANY(COALESCE(relevance_reasons, '{}'::text[])))
                """, (r["id"],))
            continue

        sender = extract_sender_domain(from_addr)

        # Pass 1 — sender allowlist
        matter = None
        provenance = None
        for k, v in SENDER_TO_DEFAULT_MATTER.items():
            if k in sender:
                matter = v
                provenance = f"sender_allowlist:{k}"
                break

        # Pass 3 — surname grep on subject+body (only if Pass 1 didn't fire)
        if not matter:
            hits = grep_surnames(haystack)
            if hits:
                # Prefer family → MWK-ESTATE, transferee or adversary → MWK-CV26360
                family_hits = [h for h in hits if h in FAMILY_SURNAMES]
                if family_hits and not any(h not in FAMILY_SURNAMES for h in hits):
                    matter = "MWK-ESTATE"
                else:
                    matter = "MWK-CV26360"
                provenance = f"surname_grep:{hits[:3]}"

        if not matter:
            counts["skip"] += 1
            continue

        if "sender_allowlist" in (provenance or ""):
            counts["sender_allow"] += 1
        else:
            counts["surname"] += 1

        matter_assigns[r["id"]] = (matter, provenance)
        if args.apply:
            cur.execute("""
                UPDATE gmail_messages
                   SET matter_codes = ARRAY[%s]::text[],
                       relevance_reasons = COALESCE(relevance_reasons, '{}'::text[]) || ARRAY[%s]
                 WHERE id = %s
            """, (matter, f"deploy_261:{provenance}", r["id"]))

    print(f"  Pass 1+3 assignments (sender allowlist + surname): {len(matter_assigns)}")
    print(f"    Pass 1 sender_allowlist: {counts['sender_allow']}")
    print(f"    Pass 3 surname_grep:     {counts['surname']}")
    print(f"  Pass 2 noise_sender (marked, not assigned): {counts['noise']}")
    print(f"  Skipped (no signal): {counts['skip']}")

    # --- Pass 4 — thread inheritance ---
    cur.execute("""
        WITH thread_matters AS (
            SELECT thread_id,
                   array_agg(DISTINCT unnest_mc) AS thread_mcs
              FROM (
                SELECT thread_id, unnest(matter_codes) AS unnest_mc
                  FROM gmail_messages
                 WHERE thread_id IS NOT NULL
                   AND cardinality(matter_codes) > 0
              ) sub
             GROUP BY thread_id
        )
        SELECT g.id, g.thread_id, tm.thread_mcs
          FROM gmail_messages g
          JOIN thread_matters tm ON tm.thread_id = g.thread_id
         WHERE cardinality(COALESCE(g.matter_codes, '{}'::text[])) = 0
    """)
    inherits = cur.fetchall()
    print(f"\n  Pass 4 thread inheritance: {len(inherits)} emails inherit matter from thread siblings")

    if args.apply:
        for r in inherits:
            cur.execute("""
                UPDATE gmail_messages
                   SET matter_codes = %s,
                       relevance_reasons = COALESCE(relevance_reasons, '{}'::text[]) || ARRAY['deploy_261:thread_inherit']
                 WHERE id = %s
            """, (r["thread_mcs"], r["id"]))

    if args.apply:
        conn.commit()
        print("\n  ✓ COMMITTED")
    else:
        print("\n  (dry-run — pass --apply to commit)")

    # Final
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE cardinality(COALESCE(matter_codes, '{}'::text[])) = 0) AS unlinked,
               COUNT(*) FILTER (WHERE cardinality(matter_codes) > 0) AS linked,
               COUNT(*) AS total
          FROM gmail_messages
    """)
    final = cur.fetchone()
    pct = 100.0 * final["linked"] / max(1, final["total"])
    print(f"\n  Final: {final['linked']}/{final['total']} linked ({pct:.0f}%) | {final['unlinked']} still unlinked")
    print(f"  Net delta from this deploy: {pre - final['unlinked']} newly linked")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
