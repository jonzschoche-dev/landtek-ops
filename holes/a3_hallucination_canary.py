"""holes.a3_hallucination_canary — STUB.

Every 4h: random-sample 3 outbound client messages from comms_log (last 24h).
For each, extract substantive factual claims and run them through truth_negotiator.
Any claim that returns verdict != verified → P0 finding (the "zero hallucinations
in client-facing output" guarantee from LEO_MASTER_PLAN.md is broken).

TODO:
  1. Query comms_log WHERE audience='client' AND created_at >= now() - INTERVAL '24h'
  2. Random sample 3 (or fewer)
  3. For each message, Haiku-extract list of factual claims (vs. greetings, questions)
  4. For each claim, call truth_negotiator.negotiate(); if verdict != verified, emit P0
  5. Idempotent: hash by (comms_log.id, claim_idx)
"""
from holes.base import Routine, run_cli


class A3_HallucinationCanary(Routine):
    name = "A3_hallucination_canary"
    version = "v0-stub"
    hole_type = "discipline_drift"
    cadence = "every_4h"
    severity_default = "P0"
    description = "Random-sample client comms, verify every claim. Any unsupported claim is a P0."

    def find_holes(self, cur):
        raise NotImplementedError(
            "A3_hallucination_canary not yet implemented — see module docstring."
        )


if __name__ == "__main__":
    run_cli(A3_HallucinationCanary)
