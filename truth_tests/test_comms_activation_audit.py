#!/usr/bin/env python3
"""test_comms_activation_audit.py — A30 mechanical floor: activation is audited, never silent.

ONTOLOGY.md §2.14 / A30: a channel goes externally active only with an auditable
activation record in channel_audit; activation is a governed outward action.

Honest current state: channel_audit is not yet the systematic activation log (activations
to date were recorded in deploys/migrations, and it holds 0 rows), so the STRONG form —
"every externally-active channel has a channel_audit activation row" — is not yet
assertable without producing a false failure. Until that wiring exists, this floor guards
the discipline we DO hold: the "arm but hold the external switch" posture. A channel whose
external switch is held must never have SILENTLY delivered an external message — a delivery
on a held channel is exactly the silent activation A30 forbids. Grounded on live data
2026-07-07 (channel_audit=0 rows; no delivered rows on any held channel).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure

# Channels armed-but-held (token/webhook not provisioned; external send must not fire).
# When a channel is deliberately + auditably opened, remove it here and add its
# channel_audit activation record.
HELD_CHANNELS = ("whatsapp", "viber", "email")
# Statuses meaning an external recipient actually received the message.
DELIVERED = ("sent", "delivered", "read")


def audit_surface_present(cur):
    cur.execute("SELECT to_regclass('public.channel_audit') AS t")
    if not cur.fetchone()["t"]:
        raise TruthFailure(
            "channel_audit is missing — the A30 activation-audit surface must exist "
            "(ONTOLOGY.md §2.14 / A30).")


def held_channels_no_silent_delivery(cur):
    cur.execute("""SELECT c.name AS name, count(*) AS n
                     FROM channel_messages cm
                     JOIN channels c ON c.id = cm.channel_id
                    WHERE c.name = ANY(%s)
                      AND cm.direction = 'outbound'
                      AND cm.status = ANY(%s)
                    GROUP BY c.name""",
                (list(HELD_CHANNELS), list(DELIVERED)))
    rows = cur.fetchall()
    if rows:
        detail = ", ".join(f"{r['name']}={r['n']}" for r in rows)
        raise TruthFailure(
            f"held channel(s) delivered an external message with no activation: {detail}. "
            "The external switch flipped silently (A30 / A26 / no-external-exposure-until-ready). "
            "If this channel was deliberately opened, record its channel_audit activation row and "
            "remove it from HELD_CHANNELS.")


TESTS = [
    ("a30.activation.audit_surface_present", audit_surface_present),
    ("a30.activation.held_channels_no_silent_delivery", held_channels_no_silent_delivery),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
