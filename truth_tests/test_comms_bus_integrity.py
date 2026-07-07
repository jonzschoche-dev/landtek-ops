#!/usr/bin/env python3
"""test_comms_bus_integrity.py — A27 mechanical floor: one bus, one guard.

ONTOLOGY.md §2.14 / A27: every comms event normalizes onto the unified bus
(channels/channel_messages) in a well-formed, governed state; no adapter writes an
orphan or an ungoverned message. The S14 human-readability + pacing HALF of A27 is
already guarded by test_n8n_execution_health::safe_reply_sanitizes_both_fields (the
Safe Reply sanitizer) — this file guards the BUS-NORMALIZATION half.

Structural invariants (not runtime health): they hold regardless of traffic and bite
when a writer regresses — a bad channel_id, a malformed direction, or an ungoverned
(status-less) outbound message. Grounded on live data 2026-07-07 (20 rows, 0 orphans).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure


def no_orphan_channel_messages(cur):
    cur.execute("""SELECT count(*) AS n FROM channel_messages cm
                   LEFT JOIN channels c ON c.id = cm.channel_id
                   WHERE c.id IS NULL""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(
            f"{n} channel_messages row(s) reference a channel_id with no channels row — "
            "the comms bus is not normalized (ONTOLOGY.md A27). A writer inserted off-bus.")


def direction_domain(cur):
    cur.execute("""SELECT count(*) AS n FROM channel_messages
                   WHERE direction IS NULL OR direction NOT IN ('inbound','outbound')""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(
            f"{n} channel_messages row(s) have a direction outside {{inbound,outbound}} (A27).")


def outbound_has_tracked_status(cur):
    cur.execute("""SELECT count(*) AS n FROM channel_messages
                   WHERE direction='outbound' AND coalesce(status,'') = ''""")
    n = cur.fetchone()["n"]
    if n:
        raise TruthFailure(
            f"{n} outbound channel_messages row(s) carry no status — an ungoverned message in "
            "limbo (A27: every message on the bus holds a tracked state).")


TESTS = [
    ("a27.bus.no_orphan_channel_messages", no_orphan_channel_messages),
    ("a27.bus.direction_domain", direction_domain),
    ("a27.bus.outbound_has_tracked_status", outbound_has_tracked_status),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
