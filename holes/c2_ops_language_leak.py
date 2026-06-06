"""holes.c2_ops_language_leak — STUB (extends existing comms_invariant_scanner.py).

Audit hourly that comms_invariant_scanner is catching ALL internal-vocabulary
that should NEVER appear in client-facing comms. Extend its banlist if gaps.

Banlist seed (per memory/feedback_no_ops_leak_to_client_ever.md):
  meta-agent, gap_alert, invariant, back-test, truth-negotiator, axiom-validator,
  inferred_strong, provenance_level, sentinel, challenger, fact_backer,
  uncitable_draft, fraud_indicator, extraction_chunk, ...

TODO:
  1. Query comms_log WHERE audience='client' AND created_at >= now() - INTERVAL '6h'
  2. For each, regex-scan body for any banlist term
  3. Match → P0 finding with the offending phrase + audience + comms_log.id
  4. ALSO: compare comms_invariant_scanner.py's banlist against our canonical list;
     if drift, emit P2 schema_drift finding telling us to extend the existing scanner
  5. Idempotent: hash by (comms_log.id, banword)
"""
from holes.base import Routine, run_cli


class C2_OpsLanguageLeak(Routine):
    name = "C2_ops_language_leak"
    version = "v0-stub"
    hole_type = "discipline_drift"
    cadence = "every_6h"
    severity_default = "P0"
    description = "Catches internal-vocabulary leaks into client-facing comms (extends existing scanner)."

    def find_holes(self, cur):
        raise NotImplementedError(
            "C2_ops_language_leak not yet implemented — see module docstring."
        )


if __name__ == "__main__":
    run_cli(C2_OpsLanguageLeak)
