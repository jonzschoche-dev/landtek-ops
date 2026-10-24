#!/usr/bin/env python3
"""test_email_bridge_routing.py — Leo's e-mail channel only answers real clients and prospects.

What went wrong (found 24 Oct 2026): email_channel_bridge.py compared the full From header ("Name <addr>") against bare
addresses, so nothing was ever excluded. Every new gmail_messages row went to Leo onboarding, and 203 bot replies were
queued since July: 94 to Jonathan himself, 24 to government offices, others to a law firm, PSA and the client's family.
Outbound was switched off, so none was sent; they were held (status held_backfill_misroute).

These assertions keep it fixed: the sender rule rejects us, offices, law firms and automated senders, and no reply may sit
queued for such an address. Deterministic, read-only, creditless.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from _harness import run, TruthFailure
import email_channel_bridge as bridge  # noqa: E402

CASES = [  # (From header, should route?)
    ("Jonathan Zschoche <jonzschoche@gmail.com>", False),
    ("Jj Moreno <jonathan@hayuma.org>", False),
    ("Litigation Division - ARTA <litigationdivision@arta.gov.ph>", False),
    ("R5 Surveys and Mapping Division <smd.r5@denr.gov.ph>", False),
    ("RTC OCC Daet Camarines Norte <rtc1daeocc@judiciary.gov.ph>", False),
    ("DILG CAMARINES NORTE <dilgcamarinesnorte2020@gmail.com>", False),
    ("Pamela Bianca Cruz <pbcruz@avaslaw.com>", False),
    ("<info@psaserbilis.com.ph>", False),
    ("vms-no-reply@op.gov.ph", False),
    ("Maria Santos <maria.santos1988@gmail.com>", True),
]


def sender_rule_holds(cur):
    """The bridge's sender rule routes a private sender and rejects us, offices, law firms and automated mail."""
    bad = [(h, exp) for h, exp in CASES if bridge.route_decision(h)[0] != exp]
    if bad:
        raise TruthFailure("route_decision wrong for: " + "; ".join(f"{h} (expected route={e})" for h, e in bad))
    print(f"      [email bridge] {len(CASES)} sender cases classified correctly")


def ladder_offices_never_route(cur):
    """Every address the drip has written to or heard from is rejected by the bridge."""
    offices = bridge.office_addresses(cur)
    leak = [a for a in offices if bridge.route_decision(a, offices)[0]]
    if leak:
        raise TruthFailure(f"{len(leak)} drip-ladder office address(es) would route to Leo: {leak[:5]}")
    print(f"      [email bridge] {len(offices)} drip-ladder addresses all rejected")


def no_reply_queued_to_non_client(cur):
    """No outbound reply waits in pending_gmail_send for an address the sender rule rejects."""
    offices = bridge.office_addresses(cur)
    cur.execute("SELECT id, channel_user_id FROM channel_messages WHERE direction='outbound' AND status='pending_gmail_send'")
    bad = [(r["id"], r["channel_user_id"]) for r in cur.fetchall() if not bridge.route_decision(r["channel_user_id"], offices)[0]]
    if bad:
        raise TruthFailure(f"{len(bad)} queued Gmail repl(ies) to non-client addresses: {bad[:5]} — hold them, never send")
    print("      [email bridge] no queued reply to us, an office, a law firm or an automated sender")


TESTS = [
    ("email_bridge.sender_rule_holds", sender_rule_holds),
    ("email_bridge.ladder_offices_never_route", ladder_offices_never_route),
    ("email_bridge.no_reply_queued_to_non_client", no_reply_queued_to_non_client),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
