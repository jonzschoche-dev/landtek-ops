#!/usr/bin/env python3
"""matter_fix.py — one-command data-layer fast path: readiness → safe auto-fixes → re-check → (memo). $0.

Operationalizes the repeatable workflow so a matter's memo takes a few targeted fixes, not dozens of
discovery-by-failure prompts:

  1. readiness pre-flight (matter_readiness)
  2. AUTO-FIX (safe, INSERT-only):
       • link orphan docs that carry the matter's docket (document_matter_links) — incl. the operative pleading
       • targeted source-read of the matter's unread linked docs (verify_worker --matter) so they get grounded
  3. re-run readiness
  4. report READY / NOT + remaining blockers; un-ingested attachments + conflations are SURFACED for the
     operator (they need a Gmail fetch / an authorized unlink — never done blindly)
  5. --generate → case_memo (which self-gates: it will not SEND a NOT-READY memo without --force)

  python3 scripts/matter_fix.py MWK-ARTA-1319
  python3 scripts/matter_fix.py MWK-ARTA-1319 --generate
"""
import os
import subprocess
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matter_readiness import assess, verdict

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
HERE = os.path.dirname(os.path.abspath(__file__))


def _link_docket_orphans(cur, mc, a):
    """Link orphans — docs that carry THIS matter's docket but aren't linked (strong relevance signal).
    document_matter_links INSERT only (allowed); never clears/changes another matter's matter_code."""
    n = 0
    for o in a["orphans"]:
        cur.execute("INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (o["id"], mc))
        n += cur.rowcount
    return n


def main():
    mc = next((x for x in sys.argv[1:] if not x.startswith("-")), None)
    if not mc:
        print("usage: matter_fix.py <MATTER_CODE> [--generate]"); return
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()

    a = assess(cur, mc)
    if not a:
        print(f"no such matter: {mc}"); return
    ready, fixes, advis = verdict(a)
    print(f"[matter_fix] {mc}: {'READY' if ready else 'NOT READY'} — {len(fixes)} blocker(s)")

    if not ready:
        n = _link_docket_orphans(cur, mc, a)
        if n:
            print(f"  ✓ linked {n} docket-carrying orphan doc(s) (incl. operative pleadings)")
        print(f"  → source-reading {mc}'s unread linked docs (verify_worker, local LLM, $0)…", flush=True)
        subprocess.run([sys.executable, f"{HERE}/verify_worker.py", "--matter", mc, "--limit", "15", "--go", "--rpm", "0"])
        a = assess(cur, mc)
        ready, fixes, advis = verdict(a)
        print(f"\n[matter_fix] {mc} after auto-fix: {'✓ READY' if ready else '✗ STILL NOT READY'}")

    for fx in fixes:
        print(f"   BLOCKER: {fx}")
    for ad in advis:
        print(f"   advisory: {ad}")
    if not ready and not fixes:
        print("   (ready)")
    # Surface what auto-fix can't safely do itself
    if a.get("uningested"):
        print(f"   ⤷ {len(a['uningested'])} un-ingested attachment(s) — run blend_emails.py (bytes-only fetch)")
    if a.get("conflations"):
        print(f"   ⤷ {len(a['conflations'])} OFF-PROFILE conflation(s) — review; unlink needs operator auth")

    if "--generate" in sys.argv:
        if not ready:
            print(f"\n[matter_fix] not generating — {mc} still NOT READY (case_memo would block the send anyway).")
            return
        print(f"\n[matter_fix] generating + sending memo for {mc}…")
        subprocess.run([sys.executable, f"{HERE}/case_memo.py", mc, "--send"])


if __name__ == "__main__":
    main()
