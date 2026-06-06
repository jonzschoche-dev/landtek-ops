"""holes.c1_provenance_drift — STUB.

Every 6h: outbound messages from comms_log (last 24h) where the body contains
substantive claims but no [V·*] citation tag. Discipline drift — Leo is making
claims without backing them.

TODO:
  1. SELECT id, audience, message_text, created_at FROM comms_log
       WHERE created_at >= now() - INTERVAL '24 hours' AND audience IN ('client','counsel')
  2. For each message, count substantive factual sentences vs citation tags [V·*] present
  3. If substantive claims > 0 AND citation tags == 0 → finding
  4. Severity scales with audience: P0 for client, P1 for counsel
  5. Idempotent: hash by comms_log.id

This is preventative. C1 catches drift even when claims happen to be TRUE —
the issue is the discipline of citing, not just the truth.
"""
from holes.base import Routine, run_cli


class C1_ProvenanceDrift(Routine):
    name = "C1_provenance_drift"
    version = "v0-stub"
    hole_type = "discipline_drift"
    cadence = "every_6h"
    severity_default = "P1"
    description = "Outbound messages without [V·*] citation tags on substantive claims."

    def find_holes(self, cur):
        raise NotImplementedError(
            "C1_provenance_drift not yet implemented — see module docstring."
        )


if __name__ == "__main__":
    run_cli(C1_ProvenanceDrift)
